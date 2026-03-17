"""
OpenClaw Voice Assistant — Web Interface (Gradio)
Talk to your OpenClaw agent via browser: type or record voice.

Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway (LLM) + Gradio (UI)
"""

import os
import json
import asyncio
import tempfile
import wave
import numpy as np
import requests
import gradio as gr
from faster_whisper import WhisperModel
import edge_tts
import scipy.io.wavfile as wavfile

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

print(f"⏳ Carregando Whisper ({WHISPER_MODEL_SIZE})...")
whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
print("✅ Whisper pronto")

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

    try:
        segments, _ = whisper_model.transcribe(
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

# ─── TTS ──────────────────────────────────────────────────────────────────────

def generate_tts_piper(text):
    """Generate TTS with Piper (local, higher quality). Returns path to WAV."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    try:
        audio_bytes = b""
        last_chunk = None
        for chunk in piper_voice.synthesize(text):
            audio_bytes += chunk.audio_int16_bytes
            last_chunk = chunk

        if not audio_bytes or last_chunk is None:
            return None

        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(last_chunk.sample_channels)
            wf.setsampwidth(last_chunk.sample_width)
            wf.setframerate(last_chunk.sample_rate)
            wf.writeframes(audio_bytes)

        if os.path.getsize(tmp.name) > 100:
            return tmp.name
    except Exception:
        pass
    return None


def generate_tts_edge(text):
    """Generate TTS with Edge TTS (Microsoft, online). Returns path to MP3."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()

    try:
        async def _gen():
            communicate = edge_tts.Communicate(text, TTS_VOICE)
            await communicate.save(tmp.name)
        asyncio.run(_gen())

        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 100:
            return tmp.name
    except Exception:
        pass
    return None


def generate_tts(text):
    """Generate TTS audio. Uses Piper (local) or Edge (online) based on config."""
    if not text or text.startswith("❌"):
        return None

    # Truncate for TTS
    tts_text = text[:1500] + "..." if len(text) > 1500 else text

    if TTS_ENGINE == "piper" and piper_voice is not None:
        result = generate_tts_piper(tts_text)
        if result:
            return result
        # Fallback to Edge if Piper fails
        return generate_tts_edge(tts_text)
    else:
        return generate_tts_edge(tts_text)

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

def respond_text(user_message, chat_history):
    """Handle text input."""
    if not user_message or not user_message.strip():
        return "", chat_history, None

    text = user_message.strip()

    # Add user message to chat
    chat_history = chat_history + [{"role": "user", "content": text}]

    # Get response
    api_history = build_api_history(chat_history[:-1])
    response = ask_openclaw(text, api_history)

    # Add assistant message
    chat_history = chat_history + [{"role": "assistant", "content": response}]

    # Generate TTS
    audio_path = generate_tts(response)

    return "", chat_history, audio_path

def respond_audio(audio_input, chat_history):
    """Handle audio input."""
    if audio_input is None:
        return chat_history, None

    # Transcribe
    text = transcribe_audio(audio_input)
    if not text:
        chat_history = chat_history + [
            {"role": "assistant", "content": "⚠️ Não captei áudio — tenta de novo"}
        ]
        return chat_history, None

    # Show what was transcribed
    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]

    # Get response
    api_history = build_api_history(chat_history[:-1])
    response = ask_openclaw(text, api_history)

    # Add assistant message
    chat_history = chat_history + [{"role": "assistant", "content": response}]

    # Generate TTS
    audio_path = generate_tts(response)

    return chat_history, audio_path

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
