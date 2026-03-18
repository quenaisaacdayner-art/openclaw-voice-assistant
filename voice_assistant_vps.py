"""
OpenClaw Voice Assistant — VPS Version (Gradio)
Runs on VPS, accessed via SSH tunnel from laptop browser.
Mic captured in browser → audio sent to VPS → Whisper STT + OpenClaw LLM + Edge TTS → response.

Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway (LLM) + Gradio (UI)
"""

import os
import json
import re
import asyncio
import tempfile
import threading
import queue
import numpy as np
import requests
import gradio as gr
from faster_whisper import WhisperModel
import edge_tts
import scipy.io.wavfile as wavfile

# ─── Configuration ────────────────────────────────────────────────────────────

# VPS gateway runs on port 19789
GATEWAY_URL = os.environ.get(
    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:19789/v1/chat/completions"
)
MODEL = os.environ.get("OPENCLAW_MODEL", "openclaw:main")
TTS_VOICE = os.environ.get("TTS_VOICE", "pt-BR-AntonioNeural")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")

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

# ─── Globals ──────────────────────────────────────────────────────────────────

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

# ─── Transcription ────────────────────────────────────────────────────────────

def transcribe_audio(audio_input):
    """Transcribe audio from Gradio's gr.Audio component (browser mic)."""
    if audio_input is None:
        return ""

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

    try:
        segments, _ = _get_whisper().transcribe(
            tmp.name,
            language="pt",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text for seg in segments).strip()
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

    resp = requests.post(GATEWAY_URL, headers=headers, json=body, timeout=120, stream=True)
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


# ─── TTS (Edge TTS — online, free) ───────────────────────────────────────────

_previous_tts_file = None

def generate_tts(text):
    """Generate TTS audio with Edge TTS (Microsoft, online)."""
    global _previous_tts_file

    if not text or text.startswith("❌"):
        return None

    if _previous_tts_file:
        try:
            os.unlink(_previous_tts_file)
        except OSError:
            pass

    tts_text = text[:1500] + "..." if len(text) > 1500 else text

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()

    try:
        async def _gen():
            communicate = edge_tts.Communicate(tts_text, TTS_VOICE)
            await communicate.save(tmp.name)

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _gen()).result(timeout=30)

        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 100:
            _previous_tts_file = tmp.name
            return tmp.name
    except Exception as e:
        print(f"⚠️ TTS error: {e}")
    return None


# ─── Chat Logic ───────────────────────────────────────────────────────────────

MAX_HISTORY = 10

def build_api_history(chat_history):
    """Convert Gradio chat history to OpenClaw API messages."""
    messages = []
    for msg in chat_history:
        if msg["role"] in ("user", "assistant"):
            content = msg.get("content", "")
            if content and not content.startswith("[🎤"):
                messages.append({"role": msg["role"], "content": content})
    return messages[-(MAX_HISTORY * 2):]


def respond_text(user_message, chat_history):
    """Handle text input with streaming response and sentence-based TTS."""
    if not user_message or not user_message.strip():
        yield "", chat_history, None
        return

    text = user_message.strip()
    chat_history = chat_history + [{"role": "user", "content": text}]
    api_history = build_api_history(chat_history[:-1])

    full_response = ""
    first_tts_done = False
    first_tts_end = 0
    audio = None

    try:
        for partial in ask_openclaw_stream(text, api_history):
            full_response = partial
            updated = chat_history + [{"role": "assistant", "content": partial}]

            if not first_tts_done:
                end = _find_sentence_end(partial)
                if end > 0:
                    audio = generate_tts(partial[:end].strip())
                    if audio:
                        first_tts_done = True
                        first_tts_end = end
                        yield "", updated, audio
                        continue

            yield "", updated, audio

        if full_response:
            final = chat_history + [{"role": "assistant", "content": full_response}]
            remaining = full_response[first_tts_end:].strip() if first_tts_done else full_response
            if remaining:
                final_audio = generate_tts(remaining)
                if final_audio:
                    audio = final_audio
            yield "", final, audio
        else:
            response = ask_openclaw(text, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield "", final, audio

    except Exception:
        response = ask_openclaw(text, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield "", final, audio


def respond_audio(audio_input, chat_history):
    """Handle audio input (browser mic) with streaming response and TTS."""
    if audio_input is None:
        yield chat_history, None
        return

    text = transcribe_audio(audio_input)
    if not text:
        yield chat_history + [
            {"role": "assistant", "content": "⚠️ Não captei áudio — tenta de novo"}
        ], None
        return

    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
    api_history = build_api_history(chat_history[:-1])

    full_response = ""
    first_tts_done = False
    first_tts_end = 0
    audio = None

    try:
        for partial in ask_openclaw_stream(text, api_history):
            full_response = partial
            updated = chat_history + [{"role": "assistant", "content": partial}]

            if not first_tts_done:
                end = _find_sentence_end(partial)
                if end > 0:
                    audio = generate_tts(partial[:end].strip())
                    if audio:
                        first_tts_done = True
                        first_tts_end = end
                        yield updated, audio
                        continue

            yield updated, audio

        if full_response:
            final = chat_history + [{"role": "assistant", "content": full_response}]
            remaining = full_response[first_tts_end:].strip() if first_tts_done else full_response
            if remaining:
                final_audio = generate_tts(remaining)
                if final_audio:
                    audio = final_audio
            yield final, audio
        else:
            response = ask_openclaw(text, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield final, audio

    except Exception:
        response = ask_openclaw(text, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield final, audio


# ─── Continuous Listening (browser-based VAD) ────────────────────────────────

# Accumulates audio chunks from Gradio streaming mic.
# When silence is detected (VAD), transcribes and processes.

class BrowserContinuousListener:
    """Accumulates streaming audio from browser mic, detects speech end, transcribes."""

    def __init__(self):
        self.active = False
        self.audio_buffer = []
        self.sample_rate = None
        self.silence_count = 0
        self.speech_detected = False
        self.processing = False
        self.text_queue = queue.Queue()
        # Thresholds
        self.SILENCE_THRESHOLD = 0.01  # RMS below this = silence
        self.SILENCE_CHUNKS_NEEDED = 8  # ~0.8s of silence to trigger transcription
        self.MIN_SPEECH_CHUNKS = 3  # minimum speech chunks before accepting

    def reset(self):
        self.audio_buffer = []
        self.silence_count = 0
        self.speech_detected = False
        self.sample_rate = None

    def feed_chunk(self, sr, audio_data):
        """Feed an audio chunk from Gradio streaming. Returns transcribed text or None."""
        if not self.active or self.processing:
            return None

        self.sample_rate = sr

        # Convert to float mono
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)
        if audio_data.dtype in (np.int16, np.int32):
            audio_data = audio_data.astype(np.float32) / 32768.0

        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio_data ** 2))

        if rms > self.SILENCE_THRESHOLD:
            # Speech detected
            self.speech_detected = True
            self.silence_count = 0
            self.audio_buffer.append(audio_data)
        else:
            # Silence
            if self.speech_detected:
                self.audio_buffer.append(audio_data)  # keep trailing silence
                self.silence_count += 1

                if self.silence_count >= self.SILENCE_CHUNKS_NEEDED and len(self.audio_buffer) >= self.MIN_SPEECH_CHUNKS:
                    # Speech ended — transcribe
                    return self._transcribe_buffer()

        return None

    def _transcribe_buffer(self):
        """Transcribe accumulated audio buffer."""
        if not self.audio_buffer or self.sample_rate is None:
            self.reset()
            return None

        self.processing = True
        try:
            full_audio = np.concatenate(self.audio_buffer)
            audio_int16 = (full_audio * 32767).astype(np.int16)

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            wavfile.write(tmp.name, self.sample_rate, audio_int16)

            try:
                segments, _ = _get_whisper().transcribe(
                    tmp.name,
                    language="pt",
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                )
                text = " ".join(seg.text for seg in segments).strip()
                return text if text else None
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
        except Exception as e:
            print(f"⚠️ Transcription error: {e}")
            return None
        finally:
            self.reset()
            self.processing = False


continuous_listener = BrowserContinuousListener()


# ─── Gradio Interface ────────────────────────────────────────────────────────

CUSTOM_CSS = """
#chatbot { min-height: 500px; }
.contain { max-width: 900px; margin: auto; }
footer { display: none !important; }
"""

with gr.Blocks(
    title="OpenClaw Voice Assistant (VPS)",
) as app:

    gr.Markdown(
        """
        # 🎤 OpenClaw Voice Assistant (VPS)
        **Fale ou digite** — processamento na VPS, mic no browser.

        *Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway (LLM) + Gradio (UI)*
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

    # Continuous listening section
    with gr.Row():
        listen_btn = gr.Button(
            "🎤 Ativar Escuta Contínua",
            variant="secondary",
            size="sm",
        )
        listen_status = gr.Textbox(
            value="Escuta contínua: DESLIGADA",
            label="Status",
            interactive=False,
            max_lines=1,
        )

    # Streaming audio input (hidden — used by continuous listening)
    stream_audio = gr.Audio(
        sources=["microphone"],
        type="numpy",
        label="🎤 Escuta Contínua (fale normalmente)",
        streaming=True,
        visible=False,
    )

    audio_output = gr.Audio(
        label="🔊 Resposta em voz",
        type="filepath",
        autoplay=True,
        visible=True,
    )

    with gr.Row():
        clear_btn = gr.Button("🗑️ Limpar conversa", size="sm")

    # ── State ──
    listening_state = gr.State(value=False)

    # ── Continuous listening handlers ──

    def toggle_listening(is_on):
        if is_on:
            continuous_listener.active = False
            continuous_listener.reset()
            return (
                False,
                "🎤 Ativar Escuta Contínua",
                "Escuta contínua: DESLIGADA",
                gr.update(interactive=True, visible=True),   # audio_input
                gr.update(visible=False),                     # stream_audio
            )
        else:
            continuous_listener.active = True
            continuous_listener.reset()
            return (
                True,
                "⏹️ Parar Escuta Contínua",
                "Escuta contínua: LIGADA — fale normalmente",
                gr.update(interactive=False, visible=False),  # audio_input
                gr.update(visible=True),                      # stream_audio
            )

    listen_btn.click(
        toggle_listening,
        inputs=[listening_state],
        outputs=[listening_state, listen_btn, listen_status, audio_input, stream_audio],
    )

    def handle_stream_chunk(audio_chunk, chat_history):
        """Process streaming audio chunk — detect speech end → transcribe → respond."""
        if audio_chunk is None or not continuous_listener.active:
            return chat_history, None

        sr, data = audio_chunk
        text = continuous_listener.feed_chunk(sr, data)

        if not text:
            return chat_history, None

        # Got transcription — process like voice input
        print(f"📝 Escuta contínua transcreveu: '{text}'")
        chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
        api_history = build_api_history(chat_history[:-1])

        response = ask_openclaw(text, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        return final, audio

    stream_audio.stream(
        handle_stream_chunk,
        inputs=[stream_audio, chatbot],
        outputs=[chatbot, audio_output],
    )

    # ── Standard events ──
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


# ─── Launch ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"\n🚀 Servidor VPS iniciando na porta {port}...")
    print(f"   Gateway: {GATEWAY_URL}")
    print(f"   TTS: Edge ({TTS_VOICE})")
    print(f"   Whisper: {WHISPER_MODEL_SIZE}")
    print(f"\n📡 Acesse via SSH tunnel: ssh -N -L {port}:127.0.0.1:{port} root@<VPS_IP>")
    print(f"   Depois abra: http://127.0.0.1:{port}\n")

    app.launch(
        server_name="127.0.0.1",
        server_port=port,
        share=False,
        inbrowser=False,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css=CUSTOM_CSS,
    )
