"""
OpenClaw Voice Assistant — WebSocket S2S Server
Protocolo: binary (audio PCM/WAV) + JSON (controle)
"""
import os
import json
import asyncio
import traceback

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.config import load_token, MODEL, WHISPER_MODEL_SIZE
from core.stt import transcribe_audio
from core.tts import init_tts, generate_tts
from core.llm import ask_openclaw_stream, ask_openclaw, _find_sentence_end
from core.history import build_api_history, MAX_HISTORY

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

TOKEN = load_token()
init_tts()


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    chat_history = []  # [{"role": "user/assistant", "content": "..."}]
    audio_buffer = bytearray()  # PCM 16-bit, 16kHz, mono
    is_speaking = False  # servidor esta gerando resposta?

    async def send_json_msg(data):
        try:
            await ws.send_json(data)
        except Exception:
            pass

    async def send_status(status):
        await send_json_msg({"type": "status", "status": status})

    try:
        await send_status("listening")

        while True:
            message = await ws.receive()

            if "bytes" in message:
                if is_speaking:
                    continue
                audio_buffer.extend(message["bytes"])

            elif "text" in message:
                data = json.loads(message["text"])

                if data["type"] == "vad_event" and data["event"] == "speech_end":
                    if len(audio_buffer) < 1600:  # <50ms = ruido
                        audio_buffer.clear()
                        continue

                    is_speaking = True
                    await send_status("thinking")

                    # Converter buffer PCM -> numpy pra Whisper
                    pcm_data = np.frombuffer(bytes(audio_buffer), dtype=np.int16)
                    audio_buffer.clear()

                    try:
                        # 1. STT — transcribe_audio espera (sample_rate, numpy_array)
                        loop = asyncio.get_event_loop()
                        transcript = await loop.run_in_executor(
                            None, transcribe_audio, (16000, pcm_data)
                        )

                        if not transcript or transcript.startswith("[Erro"):
                            await send_json_msg({"type": "transcript", "text": ""})
                            if transcript and transcript.startswith("[Erro"):
                                await send_json_msg({
                                    "type": "error",
                                    "message": "Nao captei o audio. Tente novamente."
                                })
                            await send_status("listening")
                            is_speaking = False
                            continue

                        await send_json_msg({"type": "transcript", "text": transcript})

                        # 2. Adicionar ao historico
                        chat_history.append({"role": "user", "content": transcript})
                        if len(chat_history) > MAX_HISTORY * 2:
                            chat_history = chat_history[-(MAX_HISTORY * 2):]

                        # 3. LLM streaming + TTS por frase
                        api_history = build_api_history(chat_history[:-1])
                        full_response = ""
                        last_tts_end = 0

                        await send_status("speaking")

                        # Bridge sincrona -> async via Queue
                        text_queue = asyncio.Queue()

                        def _stream_worker():
                            """Roda em thread — coloca textos parciais na queue."""
                            try:
                                for partial in ask_openclaw_stream(transcript, TOKEN, api_history):
                                    asyncio.run_coroutine_threadsafe(
                                        text_queue.put(partial), loop
                                    )
                            except Exception as e:
                                # Sinalizar erro
                                asyncio.run_coroutine_threadsafe(
                                    text_queue.put(("__error__", str(e))), loop
                                )
                            finally:
                                asyncio.run_coroutine_threadsafe(
                                    text_queue.put(None), loop  # Sentinel
                                )

                        loop.run_in_executor(None, _stream_worker)

                        stream_error = False

                        while True:
                            partial = await text_queue.get()
                            if partial is None:
                                break
                            if isinstance(partial, tuple) and partial[0] == "__error__":
                                stream_error = True
                                break

                            full_response = partial
                            await send_json_msg({"type": "text", "text": partial, "done": False})

                            # Checar frase completa pra TTS
                            remaining = partial[last_tts_end:]
                            end = _find_sentence_end(remaining)
                            if end > 0:
                                sentence = remaining[:end].strip()
                                if sentence:
                                    tts_path = await loop.run_in_executor(
                                        None, generate_tts, sentence
                                    )
                                    if tts_path:
                                        try:
                                            with open(tts_path, "rb") as af:
                                                await ws.send_bytes(af.read())
                                        finally:
                                            try:
                                                os.unlink(tts_path)
                                            except OSError:
                                                pass
                                    last_tts_end += end

                        # Fallback sincrono se streaming falhou
                        if stream_error and not full_response:
                            try:
                                full_response = await loop.run_in_executor(
                                    None, ask_openclaw, transcript, TOKEN, api_history
                                )
                            except Exception:
                                await send_json_msg({
                                    "type": "error",
                                    "message": "Erro ao processar resposta. Tente novamente."
                                })
                                is_speaking = False
                                await send_status("listening")
                                continue

                        # TTS do texto restante
                        if full_response:
                            remaining = full_response[last_tts_end:].strip()
                            if remaining:
                                tts_path = await loop.run_in_executor(
                                    None, generate_tts, remaining
                                )
                                if tts_path:
                                    try:
                                        with open(tts_path, "rb") as af:
                                            await ws.send_bytes(af.read())
                                    finally:
                                        try:
                                            os.unlink(tts_path)
                                        except OSError:
                                            pass

                            await send_json_msg({"type": "text", "text": full_response, "done": True})
                            chat_history.append({"role": "assistant", "content": full_response})

                    except Exception as e:
                        traceback.print_exc()
                        await send_json_msg({
                            "type": "error",
                            "message": f"Erro interno: {e}"
                        })
                    finally:
                        is_speaking = False
                        await send_status("listening")

                elif data["type"] == "interrupt":
                    # TODO Fase 3: cancelar LLM + TTS em andamento
                    pass

                elif data["type"] == "config":
                    # TODO: permitir mudar modelo/whisper/tts via WS
                    pass

    except WebSocketDisconnect:
        pass
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
