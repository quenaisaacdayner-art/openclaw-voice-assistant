"""
OpenClaw Voice Assistant — Web Interface (Gradio)
Talk to your OpenClaw agent via browser: type or record voice.

Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway (LLM) + Gradio (UI)
"""

import os
import json
import re
import asyncio
import tempfile
import time
import threading
import queue
import numpy as np
import requests
import gradio as gr
from faster_whisper import WhisperModel
import edge_tts
import scipy.io.wavfile as wavfile
import torch
import torchaudio


def log_latency(stage, t0, extra=''):
    elapsed = time.time() - t0
    print(f'⏱️ [{stage}] {elapsed:.2f}s {extra}')

# Piper TTS (local, higher quality voice)
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

# ─── Configuration ────────────────────────────────────────────────────────────

GATEWAY_URL = os.environ.get(
    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions"
)
MODEL = os.environ.get("OPENCLAW_MODEL", "openclaw:main")
TTS_VOICE = os.environ.get("TTS_VOICE", "pt-BR-AntonioNeural")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper")  # "piper" (local) or "edge" (Microsoft)
PIPER_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "pt_BR-faber-medium.onnx")

# ─── Load Token ───────────────────────────────────────────────────────────────

def load_token():
    config_path = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        token = config["gateway"]["auth"]["token"]
        if token:
            return token
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if token:
        return token
    raise RuntimeError("Token não encontrado. Configure em ~/.openclaw/openclaw.json ou OPENCLAW_GATEWAY_TOKEN")

# ─── Globals (loaded once at startup) ────────────────────────────────────────

# Whisper loaded lazily on first manual transcription to avoid
# duplicating the ~460MB model when RealtimeSTT is used instead.
whisper_model = None
_whisper_lock = threading.Lock()

def _get_whisper():
    global whisper_model
    if whisper_model is None:
        with _whisper_lock:
            if whisper_model is None:
                print(f"⏳ Carregando Whisper ({WHISPER_MODEL_SIZE})...")
                whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
                print("✅ Whisper pronto")
    return whisper_model

TOKEN = load_token()
print("✅ Token carregado")

# Load Piper voice model
piper_voice = None
if TTS_ENGINE == "piper" and PIPER_AVAILABLE and os.path.exists(PIPER_MODEL):
    print(f"⏳ Carregando Piper TTS ({os.path.basename(PIPER_MODEL)})...")
    piper_voice = PiperVoice.load(PIPER_MODEL)
    print("✅ Piper TTS pronto")
elif TTS_ENGINE == "piper":
    print("⚠️ Piper indisponível — usando Edge TTS como fallback")
    TTS_ENGINE = "edge"

# ─── Browser VAD Listener (Silero VAD) ───────────────────────────────────────

class BrowserVADListener:
    '''Escuta contínua via browser usando Silero VAD. Funciona em VPS sem mic local.'''

    SILENCE_DURATION = 0.8  # segundos de silêncio após fala = fim de utterance
    MIN_SPEECH_DURATION = 0.3  # segundos mínimo de fala pra considerar
    SPEECH_THRESHOLD = 0.5  # probabilidade mínima de fala do Silero

    def __init__(self):
        self.available = False
        self.enabled = False
        self._audio_buffer = []
        self._buffer_duration = 0.0
        self._is_speaking = False
        self._silence_duration = 0.0
        self._lock = threading.Lock()
        self._processing = False

        try:
            print('⏳ Carregando Silero VAD...')
            self._model, self._utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                trust_repo=True
            )
            self.available = True
            print('✅ Silero VAD pronto')
        except Exception as e:
            print(f'⚠️ Silero VAD falhou ao carregar: {e}')

    def reset(self):
        with self._lock:
            self._audio_buffer = []
            self._buffer_duration = 0.0
            self._is_speaking = False
            self._silence_duration = 0.0
            self._processing = False
            if self.available:
                self._model.reset_states()

    def process_chunk(self, audio_input):
        '''Processa chunk de áudio do Gradio streaming. Retorna texto transcrito ou None.'''
        if not self.available or not self.enabled or audio_input is None:
            return None

        with self._lock:
            if self._processing:
                return None

        sr, audio_data = audio_input

        # Converter pra float32
        if audio_data.dtype == np.int16:
            audio_data = audio_data.astype(np.float32) / 32768.0
        elif audio_data.dtype == np.int32:
            audio_data = audio_data.astype(np.float32) / 2147483648.0
        elif audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        # Mono
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)

        # Resample pra 16kHz se necessário
        tensor = torch.from_numpy(audio_data)
        if sr != 16000:
            tensor = torchaudio.functional.resample(tensor, sr, 16000)

        chunk_duration = len(tensor) / 16000.0

        # Rodar VAD
        speech_prob = self._model(tensor, 16000).item()

        if speech_prob > self.SPEECH_THRESHOLD:
            self._is_speaking = True
            self._silence_duration = 0.0
            self._audio_buffer.append(tensor)
            self._buffer_duration += chunk_duration
        elif self._is_speaking:
            # Ainda acumula áudio durante silêncio curto (pode ser pausa natural)
            self._audio_buffer.append(tensor)
            self._buffer_duration += chunk_duration
            self._silence_duration += chunk_duration

            if self._silence_duration >= self.SILENCE_DURATION:
                # Fim de utterance detectado
                if self._buffer_duration - self._silence_duration >= self.MIN_SPEECH_DURATION:
                    with self._lock:
                        self._processing = True

                    try:
                        t0 = time.time()
                        # Juntar buffer e transcrever
                        full_audio = torch.cat(self._audio_buffer)

                        # Salvar como WAV temporário pra Whisper
                        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                        tmp.close()
                        audio_np = (full_audio.numpy() * 32767).astype(np.int16)
                        wavfile.write(tmp.name, 16000, audio_np)

                        # Transcrever
                        segments, _ = _get_whisper().transcribe(
                            tmp.name, language='pt', beam_size=5,
                            vad_filter=True,
                            vad_parameters=dict(min_silence_duration_ms=500)
                        )
                        text = ' '.join(seg.text for seg in segments).strip()

                        # Cleanup
                        try:
                            os.unlink(tmp.name)
                        except OSError:
                            pass

                        log_latency('VAD-STT', t0, f'({self._buffer_duration:.1f}s audio, {len(text)} chars)')

                        # Reset
                        self._audio_buffer = []
                        self._buffer_duration = 0.0
                        self._is_speaking = False
                        self._silence_duration = 0.0
                        self._model.reset_states()

                        if text:
                            print(f'📝 VAD transcreveu: {text}')
                            return text
                    finally:
                        with self._lock:
                            self._processing = False
                else:
                    # Áudio muito curto — descartar (ruído)
                    self._audio_buffer = []
                    self._buffer_duration = 0.0
                    self._is_speaking = False
                    self._silence_duration = 0.0
                    self._model.reset_states()

        return None


vad_listener = BrowserVADListener()

# ─── Transcription ────────────────────────────────────────────────────────────

def transcribe_audio(audio_input):
    """Transcribe audio from Gradio's gr.Audio component."""
    if audio_input is None:
        return ""

    # Gradio returns (sample_rate, numpy_array) for microphone input
    sr, audio_data = audio_input

    # Convert to mono if stereo
    if len(audio_data.shape) > 1:
        audio_data = audio_data.mean(axis=1)

    # Normalize to int16 if float
    if audio_data.dtype in (np.float32, np.float64):
        audio_data = (audio_data * 32767).astype(np.int16)

    # Save to temp WAV
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    wavfile.write(tmp.name, sr, audio_data)

    audio_duration = len(audio_data) / sr if sr > 0 else 0

    try:
        t0_stt = time.time()
        segments, _ = _get_whisper().transcribe(
            tmp.name,
            language="pt",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text for seg in segments).strip()
        log_latency('STT', t0_stt, f'(audio: {audio_duration:.1f}s, {sr}Hz)')
        return text
    except Exception as e:
        return f"[Erro na transcrição: {e}]"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

# ─── OpenClaw API ─────────────────────────────────────────────────────────────

def ask_openclaw(text, history_messages):
    """Send text to OpenClaw gateway."""
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    messages = list(history_messages) + [{"role": "user", "content": text}]
    body = {"model": MODEL, "messages": messages}

    try:
        resp = requests.post(GATEWAY_URL, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.ConnectionError:
        return "❌ OpenClaw não respondeu. Gateway tá rodando?"
    except requests.Timeout:
        return "❌ Timeout — OpenClaw demorou demais."
    except (requests.RequestException, KeyError, IndexError) as e:
        return f"❌ Erro: {e}"


def ask_openclaw_stream(text, history_messages):
    """Send text to OpenClaw gateway with streaming (SSE). Yields accumulated text."""
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    messages = list(history_messages) + [{"role": "user", "content": text}]
    body = {"model": MODEL, "messages": messages, "stream": True}

    with requests.post(GATEWAY_URL, headers=headers, json=body, timeout=120, stream=True) as resp:
        resp.raise_for_status()

        full_text = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[len("data: "):]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                content = chunk["choices"][0].get("delta", {}).get("content", "")
                if content:
                    full_text += content
                    yield full_text
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def _find_sentence_end(text):
    """Position after the first sentence-ending punctuation followed by whitespace."""
    m = re.search(r'[.!?…]\s', text)
    return m.end() if m else 0


# ─── TTS ──────────────────────────────────────────────────────────────────────

def generate_tts_piper(text):
    """Generate TTS with Piper (local, higher quality). Returns path to WAV."""
    t0_tts = time.time()
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    try:
        audio_bytes = b""
        last_chunk = None
        for chunk in piper_voice.synthesize(text):
            audio_bytes += chunk.audio_int16_bytes
            last_chunk = chunk

        if not audio_bytes or last_chunk is None:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            return None

        import wave
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(last_chunk.sample_channels)
            wf.setsampwidth(last_chunk.sample_width)
            wf.setframerate(last_chunk.sample_rate)
            wf.writeframes(audio_bytes)

        if os.path.getsize(tmp.name) > 100:
            log_latency('TTS-PIPER', t0_tts, f'({len(text)} chars)')
            return tmp.name
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    except Exception as e:
        print(f"⚠️ Piper TTS error: {e}")
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return None


def generate_tts_edge(text):
    """Generate TTS with Edge TTS (Microsoft, online). Returns path to MP3."""
    t0_tts = time.time()
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()

    try:
        async def _gen():
            communicate = edge_tts.Communicate(text, TTS_VOICE)
            await communicate.save(tmp.name)

        # Gradio 6.x runs its own event loop — asyncio.run() would crash.
        # Run in a fresh thread with its own loop to be safe everywhere.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _gen()).result(timeout=30)

        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 100:
            log_latency('TTS-EDGE', t0_tts, f'({len(text)} chars)')
            return tmp.name
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    except Exception as e:
        print(f"⚠️ Edge TTS error: {e}")
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return None


_previous_tts_file = None
_tts_file_lock = threading.Lock()

def generate_tts(text):
    """Generate TTS audio. Uses Piper (local) or Edge (online) based on config."""
    global _previous_tts_file

    if not text or text.startswith("❌"):
        return None

    # Clean up previous TTS file (Gradio already served it by now)
    with _tts_file_lock:
        old_file = _previous_tts_file
        _previous_tts_file = None
    if old_file:
        try:
            os.unlink(old_file)
        except OSError:
            pass

    # Truncate for TTS
    tts_text = text[:1500] + "..." if len(text) > 1500 else text

    result = None
    if TTS_ENGINE == "piper" and piper_voice is not None:
        result = generate_tts_piper(tts_text)
        if not result:
            # Fallback to Edge if Piper fails
            result = generate_tts_edge(tts_text)
    else:
        result = generate_tts_edge(tts_text)

    with _tts_file_lock:
        _previous_tts_file = result
    return result

# ─── Chat Logic ───────────────────────────────────────────────────────────────

MAX_HISTORY = 10  # exchanges (20 messages)

def build_api_history(chat_history):
    """Convert Gradio chat history to OpenClaw API messages."""
    messages = []
    for msg in chat_history:
        if msg["role"] in ("user", "assistant"):
            content = msg.get("content", "")
            if content and not content.startswith("[🎤"):
                messages.append({"role": msg["role"], "content": content})
    # Keep last N
    return messages[-(MAX_HISTORY * 2):]

def _process_streaming_response(text, chat_history, api_history):
    """Stream LLM response with sentence-based TTS. Yields (chat_history, audio).

    Shared logic for text input, audio input, and continuous listening.
    """
    t0_stream = time.time()
    full_response = ""
    first_tts_done = False
    first_tts_end = 0
    first_token_logged = False
    audio = None

    try:
        for partial in ask_openclaw_stream(text, api_history):
            full_response = partial

            if not first_token_logged:
                log_latency('API-TTFT', t0_stream, '(first token)')
                first_token_logged = True

            updated = chat_history + [{"role": "assistant", "content": partial}]

            # Generate TTS for first complete sentence (early voice)
            if not first_tts_done:
                end = _find_sentence_end(partial)
                if end > 0:
                    audio = generate_tts(partial[:end].strip())
                    if audio:
                        first_tts_done = True
                        first_tts_end = end
                        log_latency('API-FIRST-SENTENCE', t0_stream, f'({end} chars)')
                        yield updated, audio
                        continue

            yield updated, audio

        # Streaming done
        if full_response:
            log_latency('API-COMPLETE', t0_stream, f'({len(full_response)} chars total)')
            final = chat_history + [{"role": "assistant", "content": full_response}]
            # TTS for remaining unspoken text
            remaining = full_response[first_tts_end:].strip() if first_tts_done else full_response
            if remaining:
                t0_tts_final = time.time()
                final_audio = generate_tts(remaining)
                if final_audio:
                    log_latency('TTS-FINAL', t0_tts_final, f'({len(remaining)} chars remaining)')
                    audio = final_audio
            yield final, audio
        else:
            # Streaming yielded nothing — fallback to non-streaming
            response = ask_openclaw(text, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield final, audio

    except Exception as e:
        print(f"⚠️ Streaming failed, falling back to non-streaming: {e}")
        response = ask_openclaw(text, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield final, audio


def respond_text(user_message, chat_history):
    """Handle text input with streaming response and sentence-based TTS."""
    if not user_message or not user_message.strip():
        yield "", chat_history, None
        return

    t0_e2e = time.time()
    text = user_message.strip()
    chat_history = chat_history + [{"role": "user", "content": text}]
    api_history = build_api_history(chat_history[:-1])

    for updated, audio in _process_streaming_response(text, chat_history, api_history):
        yield "", updated, audio

    log_latency('END-TO-END', t0_e2e, '(text input)')


def respond_audio(audio_input, chat_history):
    """Handle audio input with streaming response and sentence-based TTS."""
    if audio_input is None:
        yield chat_history, None
        return

    t0_e2e = time.time()

    # Transcribe
    t0_stt = time.time()
    text = transcribe_audio(audio_input)
    stt_elapsed = time.time() - t0_stt
    if not text:
        yield chat_history + [
            {"role": "assistant", "content": "⚠️ Não captei áudio — tenta de novo"}
        ], None
        return

    # Show what was transcribed
    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
    api_history = build_api_history(chat_history[:-1])

    for updated, audio in _process_streaming_response(text, chat_history, api_history):
        yield updated, audio

    log_latency('END-TO-END', t0_e2e, f'(voice input, STT: {stt_elapsed:.2f}s)')

# ─── Gradio Interface ────────────────────────────────────────────────────────

CUSTOM_CSS = """
#chatbot { min-height: 500px; }
.contain { max-width: 900px; margin: auto; }
footer { display: none !important; }
"""

with gr.Blocks(
    title="OpenClaw Voice Assistant",
) as app:

    gr.Markdown(
        """
        # 🎤 OpenClaw Voice Assistant
        **Fale ou digite** — conectado ao seu agente OpenClaw com memória e skills.

        *Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway (LLM) + Gradio (UI) — 100% grátis*
        """
    )

    chatbot = gr.Chatbot(
        elem_id="chatbot",
        label="Conversa",
        height=500,
    )

    with gr.Row():
        with gr.Column(scale=4):
            text_input = gr.Textbox(
                placeholder="Digite sua mensagem...",
                show_label=False,
                container=False,
                scale=4,
            )
        with gr.Column(scale=1, min_width=100):
            send_btn = gr.Button("Enviar", variant="primary")

    with gr.Row():
        audio_input = gr.Audio(
            sources=["microphone"],
            type="numpy",
            label="🎤 Gravar voz (clique no microfone)",
        )

    # Escuta contínua via browser
    with gr.Row():
        listen_btn = gr.Button(
            '🎤 Ativar Escuta Contínua' if vad_listener.available else '🎤 Escuta Contínua (indisponível)',
            variant='secondary',
            size='sm',
            interactive=vad_listener.available,
        )
        listen_status = gr.Textbox(
            value='Escuta contínua: DESLIGADA' if vad_listener.available else 'Silero VAD não disponível',
            label='Status',
            interactive=False,
            max_lines=1,
        )

    streaming_mic = gr.Audio(
        sources=['microphone'],
        streaming=True,
        visible=False,
        label='Escuta Contínua',
    )

    listening_state = gr.State(value=False)

    audio_output = gr.Audio(
        label="🔊 Resposta em voz",
        type="filepath",
        autoplay=True,
        visible=True,
    )

    with gr.Row():
        clear_btn = gr.Button("🗑️ Limpar conversa", size="sm")

    # Events
    text_input.submit(
        respond_text,
        inputs=[text_input, chatbot],
        outputs=[text_input, chatbot, audio_output],
    )
    send_btn.click(
        respond_text,
        inputs=[text_input, chatbot],
        outputs=[text_input, chatbot, audio_output],
    )
    audio_input.stop_recording(
        respond_audio,
        inputs=[audio_input, chatbot],
        outputs=[chatbot, audio_output],
    )
    clear_btn.click(lambda: ([], None), outputs=[chatbot, audio_output])

    # ── Continuous Listening events (Browser VAD) ──

    def toggle_vad(is_on):
        if is_on:
            # Desligar escuta contínua
            vad_listener.enabled = False
            vad_listener.reset()
            return (
                False,
                '🎤 Ativar Escuta Contínua',
                'Escuta contínua: DESLIGADA',
                gr.update(visible=False),   # streaming_mic: esconder
                gr.update(visible=True),    # audio_input: mostrar de volta
            )
        else:
            # Ligar escuta contínua
            vad_listener.enabled = True
            vad_listener.reset()
            return (
                True,
                '⏹️ Parar Escuta Contínua',
                'Escuta contínua: LIGADA — fale normalmente',
                gr.update(visible=True),    # streaming_mic: mostrar
                gr.update(visible=False),   # audio_input: esconder (evita conflito encoder)
            )

    def handle_stream(audio_chunk, chat_history):
        if audio_chunk is None:
            yield gr.skip(), gr.skip()
            return

        text = vad_listener.process_chunk(audio_chunk)
        if text is None:
            # Sem utterance completa — NÃO atualizar UI (evita tic-tic-tic)
            yield gr.skip(), gr.skip()
            return

        t0 = time.time()
        chat_history = chat_history + [{'role': 'user', 'content': f'[🎤 Voz]: {text}'}]
        api_history = build_api_history(chat_history[:-1])

        for updated, audio in _process_streaming_response(text, chat_history, api_history):
            yield updated, audio

        log_latency('END-TO-END', t0, '(continuous voice)')

    listen_btn.click(
        toggle_vad,
        inputs=[listening_state],
        outputs=[listening_state, listen_btn, listen_status, streaming_mic, audio_input],
    )
    streaming_mic.stream(
        handle_stream,
        inputs=[streaming_mic, chatbot],
        outputs=[chatbot, audio_output],
    )

# ─── Launch ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🚀 Abrindo no browser...")
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css=CUSTOM_CSS,
    )
