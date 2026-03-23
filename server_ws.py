"""
OpenClaw Voice Assistant — WebSocket S2S Server
Protocolo: binary (audio PCM/WAV) + JSON (controle)
"""
import os
import json
import time
import asyncio
import traceback

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.config import load_token, GATEWAY_URL, MODEL, WHISPER_MODEL_SIZE
from core.stt import transcribe_audio, init_stt, get_current_model
from core.tts import (init_tts, warmup_tts, generate_tts,
                      get_engine, get_tts_info,
                      get_available_voices, get_current_voice, get_speed)
from core.llm import ask_openclaw_stream, ask_openclaw, _find_sentence_end, _session as llm_session
from core.history import build_api_history, MAX_HISTORY

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

TOKEN = load_token()
init_tts()

# — Warmup —
_warmup_t0 = time.time()

init_stt()
warmup_tts()

# TTS engine banner
print(f"🔊 TTS Engine: {get_tts_info()}")

# Gateway ping (via session keep-alive)
_gw_t0 = time.time()
try:
    _gw_base = GATEWAY_URL.rsplit("/chat/completions", 1)[0]
    _gw_resp = llm_session.get(_gw_base, timeout=10, headers={"Authorization": f"Bearer {TOKEN}"})
    _gw_elapsed = time.time() - _gw_t0
    print(f"[WARMUP] Gateway OK em {_gw_elapsed:.1f}s (keep-alive)")
except Exception:
    _gw_elapsed = time.time() - _gw_t0
    print(f"[WARMUP] ⚠️ Gateway não respondeu — conecta na 1ª mensagem")

print(f"[WARMUP] Tudo pronto em {time.time() - _warmup_t0:.1f}s")


async def _tts_to_bytes(text, loop):
    """Gera TTS e retorna bytes do audio (limpa arquivo temporario)."""
    tts_path = await loop.run_in_executor(None, generate_tts, text)
    if not tts_path:
        return None
    try:
        with open(tts_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tts_path)
        except OSError:
            pass


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    # Enviar info do servidor ao conectar
    server_info = {
        "type": "server_info",
        "tts_engine": get_engine(),
        "tts_voice": get_current_voice(),
        "tts_voices": get_available_voices(),
        "tts_speed": get_speed(),
        "whisper_model": get_current_model(),
    }
    await ws.send_json(server_info)

    chat_history = []  # [{"role": "user/assistant", "content": "..."}]
    audio_buffer = bytearray()  # PCM 16-bit, 16kHz, mono
    processing = False
    cancel_event = asyncio.Event()

    async def send_json_msg(data):
        try:
            await ws.send_json(data)
        except Exception:
            pass

    async def send_status(status):
        await send_json_msg({"type": "status", "status": status})

    async def _llm_and_tts(user_text, t_start=None):
        """LLM streaming + TTS por frase. Retorna dict com métricas."""
        nonlocal chat_history

        api_history = build_api_history(chat_history[:-1])
        await send_status("speaking")

        loop = asyncio.get_event_loop()
        text_queue = asyncio.Queue()
        t_llm_start = time.time()
        t_ttft = None

        def _stream_worker():
            try:
                for partial in ask_openclaw_stream(user_text, TOKEN, api_history):
                    asyncio.run_coroutine_threadsafe(
                        text_queue.put(partial), loop
                    )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    text_queue.put(("__error__", str(e))), loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(
                    text_queue.put(None), loop
                )

        loop.run_in_executor(None, _stream_worker)

        full_response = ""
        last_tts_end = 0
        stream_error = False
        tts_count = 0
        t_tts_first = None

        while True:
            if cancel_event.is_set():
                break
            try:
                partial = await asyncio.wait_for(text_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            if partial is None:
                break
            if isinstance(partial, tuple) and partial[0] == "__error__":
                stream_error = True
                break

            if t_ttft is None:
                t_ttft = time.time()
                print(f"[LLM] TTFT: {t_ttft - t_llm_start:.1f}s")

            full_response = partial
            await send_json_msg({"type": "text", "text": partial, "done": False})

            remaining = partial[last_tts_end:]
            end = _find_sentence_end(remaining)
            if end > 0:
                sentence = remaining[:end].strip()
                if sentence and not cancel_event.is_set():
                    t_tts_s = time.time()
                    audio_bytes = await _tts_to_bytes(sentence, loop)
                    if audio_bytes and not cancel_event.is_set():
                        await ws.send_bytes(audio_bytes)
                        tts_count += 1
                        if t_tts_first is None:
                            t_tts_first = time.time()
                            print(f"[TTS] 1ª frase: \"{sentence[:40]}{'...' if len(sentence) > 40 else ''}\" ({t_tts_first - t_tts_s:.1f}s)")
                    last_tts_end += end

        t_llm_end = time.time()
        if full_response:
            print(f"[LLM] Resposta completa: {len(full_response)} chars em {t_llm_end - t_llm_start:.1f}s")

        # Fallback sincrono se streaming falhou
        if stream_error and not full_response and not cancel_event.is_set():
            try:
                full_response = await loop.run_in_executor(
                    None, ask_openclaw, user_text, TOKEN, api_history
                )
            except Exception:
                await send_json_msg({
                    "type": "error",
                    "message": "Erro ao processar resposta. Tente novamente."
                })
                return

        # TTS do texto restante
        if full_response and not cancel_event.is_set():
            remaining_text = full_response[last_tts_end:].strip()
            if remaining_text:
                t_tts_s = time.time()
                audio_bytes = await _tts_to_bytes(remaining_text, loop)
                if audio_bytes and not cancel_event.is_set():
                    await ws.send_bytes(audio_bytes)
                    tts_count += 1
                    if t_tts_first is None:
                        t_tts_first = time.time()
                        print(f"[TTS] 1ª frase: \"{remaining_text[:40]}{'...' if len(remaining_text) > 40 else ''}\" ({t_tts_first - t_tts_s:.1f}s)")

            await send_json_msg({"type": "text", "text": full_response, "done": True})
            chat_history.append({"role": "assistant", "content": full_response})
        elif full_response:
            await send_json_msg({"type": "text", "text": full_response, "done": True})
            chat_history.append({"role": "assistant", "content": full_response + " [interrompido]"})

        if tts_count > 0:
            print(f"[TTS] Total: {tts_count} frases")

        metrics = {
            "ttft": t_ttft - t_llm_start if t_ttft else None,
            "tts_first": t_tts_first,
            "tts_count": tts_count,
            "response_len": len(full_response),
        }

        if t_start and t_tts_first:
            ttfa = t_tts_first - t_start
            print(f"[PERF] ⚡ Time-to-First-Audio: {ttfa:.1f}s")

        return metrics

    async def process_speech():
        """Processa audio acumulado: STT -> LLM -> TTS"""
        nonlocal processing, chat_history
        processing = True
        cancel_event.clear()

        try:
            t0 = time.time()
            print(f"\n[REQ] Nova mensagem recebida")

            await send_status("thinking")

            # Converter buffer PCM -> numpy pra Whisper
            pcm_data = np.frombuffer(bytes(audio_buffer), dtype=np.int16)
            audio_buffer.clear()

            # 1. STT
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(
                None, transcribe_audio, (16000, pcm_data)
            )
            t_stt = time.time()

            if not transcript or cancel_event.is_set():
                await send_json_msg({"type": "transcript", "text": ""})
                return

            if transcript.startswith("[Erro"):
                await send_json_msg({"type": "transcript", "text": ""})
                await send_json_msg({
                    "type": "error",
                    "message": "Nao captei o audio. Tente novamente."
                })
                return

            print(f"[STT] Transcrição: \"{transcript[:50]}{'...' if len(transcript) > 50 else ''}\" ({t_stt - t0:.1f}s)")

            await send_json_msg({"type": "transcript", "text": transcript})

            # 2. Adicionar ao historico
            chat_history.append({"role": "user", "content": transcript})
            if len(chat_history) > MAX_HISTORY * 2:
                chat_history = chat_history[-(MAX_HISTORY * 2):]

            # 3. LLM streaming + TTS por frase
            metrics = await _llm_and_tts(transcript, t_start=t0)

            t_total = time.time() - t0
            print(f"[TOTAL] Fala→Resposta: {t_total:.1f}s")

            if metrics:
                perf_msg = {"type": "perf"}
                if metrics.get("ttft"):
                    perf_msg["ttft"] = round(metrics["ttft"], 1)
                if metrics.get("tts_first"):
                    perf_msg["ttfa"] = round(metrics["tts_first"] - t0, 1)
                await send_json_msg(perf_msg)

        except Exception as e:
            traceback.print_exc()
            await send_json_msg({
                "type": "error",
                "message": f"Erro interno: {e}"
            })

        finally:
            processing = False
            if not cancel_event.is_set():
                await send_status("listening")

    async def process_text(user_text):
        """Processa texto digitado: LLM -> TTS (sem STT)."""
        nonlocal processing, chat_history
        processing = True
        cancel_event.clear()

        try:
            t0 = time.time()
            print(f"\n[REQ] Texto digitado: \"{user_text[:50]}{'...' if len(user_text) > 50 else ''}\"")

            await send_json_msg({"type": "transcript", "text": user_text})
            await send_status("thinking")

            chat_history.append({"role": "user", "content": user_text})
            if len(chat_history) > MAX_HISTORY * 2:
                chat_history = chat_history[-(MAX_HISTORY * 2):]

            metrics = await _llm_and_tts(user_text, t_start=t0)

            t_total = time.time() - t0
            print(f"[TOTAL] Texto→Resposta: {t_total:.1f}s")

            if metrics:
                perf_msg = {"type": "perf"}
                if metrics.get("ttft"):
                    perf_msg["ttft"] = round(metrics["ttft"], 1)
                if metrics.get("tts_first"):
                    perf_msg["ttfa"] = round(metrics["tts_first"] - t0, 1)
                await send_json_msg(perf_msg)

        except Exception as e:
            traceback.print_exc()
            await send_json_msg({
                "type": "error",
                "message": f"Erro interno: {e}"
            })

        finally:
            processing = False
            if not cancel_event.is_set():
                await send_status("listening")

    # --- Main receive loop ---
    process_task = None

    try:
        await send_status("listening")

        while True:
            message = await ws.receive()

            if "bytes" in message:
                if not processing:
                    audio_buffer.extend(message["bytes"])
                elif cancel_event.is_set():
                    # Acumula pra possivel novo turno apos interrupt
                    audio_buffer.extend(message["bytes"])

            elif "text" in message:
                data = json.loads(message["text"])

                if data["type"] == "ping":
                    await ws.send_json({"type": "pong", "t": data.get("t")})
                    continue

                elif data["type"] == "restore_history":
                    restored = data.get("messages", [])
                    if isinstance(restored, list):
                        valid = []
                        for msg in restored[-20:]:
                            if (isinstance(msg, dict)
                                and msg.get("role") in ("user", "assistant")
                                and isinstance(msg.get("content"), str)
                                and msg["content"].strip()):
                                valid.append({
                                    "role": msg["role"],
                                    "content": msg["content"][:5000]
                                })
                        chat_history.clear()
                        chat_history.extend(valid)
                        print(f"[SESSION] Histórico restaurado: {len(valid)} mensagens")
                        await send_json_msg({
                            "type": "session_restored",
                            "count": len(valid)
                        })
                    continue

                if data["type"] == "vad_event" and data["event"] == "speech_end":
                    if processing:
                        continue
                    if len(audio_buffer) < 1600:  # <50ms = ruido
                        audio_buffer.clear()
                        continue

                    process_task = asyncio.create_task(process_speech())

                elif data["type"] == "interrupt":
                    if processing:
                        cancel_event.set()
                        # process_speech vai parar no proximo check
                        if process_task:
                            try:
                                await asyncio.wait_for(process_task, timeout=5.0)
                            except asyncio.TimeoutError:
                                pass
                        await send_status("listening")

                elif data["type"] == "text_input":
                    user_text = data.get("text", "").strip()
                    if user_text and not processing:
                        process_task = asyncio.create_task(process_text(user_text))

                elif data["type"] == "config":
                    whisper_model = data.get("whisper_model")
                    if whisper_model and whisper_model in ("tiny", "small", "medium"):
                        from core.stt import set_whisper_model
                        set_whisper_model(whisper_model)
                        print(f"[CONFIG] Whisper model → {whisper_model}")

                    voice = data.get("tts_voice")
                    if voice:
                        from core.tts import set_voice
                        set_voice(voice)

                    speed = data.get("tts_speed")
                    if speed is not None:
                        from core.tts import set_speed
                        set_speed(float(speed))

    except WebSocketDisconnect:
        if process_task and not process_task.done():
            cancel_event.set()
            process_task.cancel()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "7860"))
    print(f"\n{'='*50}")
    print(f"  OpenClaw Voice Assistant — WebSocket S2S")
    print(f"  http://{host}:{port}")
    print(f"  Modelo: {MODEL}")
    print(f"  Whisper: {WHISPER_MODEL_SIZE}")
    print(f"{'='*50}\n")
    uvicorn.run(app, host=host, port=port)
