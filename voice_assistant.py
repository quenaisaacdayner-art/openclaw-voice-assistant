"""
OpenClaw Voice Assistant
Talk to your OpenClaw agent using your voice — 100% free, runs locally.

Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway API (LLM)
"""

import os
import sys
import json
import wave
import threading
import asyncio
import subprocess
import numpy as np
import sounddevice as sd
import requests
from faster_whisper import WhisperModel
import edge_tts

# ─── Configuration ────────────────────────────────────────────────────────────

GATEWAY_URL = os.environ.get(
    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions"
)
MODEL = os.environ.get("OPENCLAW_MODEL", "openclaw:main")
TTS_VOICE = os.environ.get("TTS_VOICE", "pt-BR-AntonioNeural")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resposta.mp3")

# ─── Microphone ───────────────────────────────────────────────────────────────

def find_microphone():
    """Auto-detect the best microphone. Prefers Intel Smart Sound, falls back to default."""
    devices = sd.query_devices()

    # Priority 1: Intel Smart Sound (built-in laptop mic, best quality)
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0 and "Intel" in dev.get("name", "") and "Smart Sound" in dev.get("name", ""):
            return i, dev["name"]

    # Priority 2: Any non-virtual mic with "Micrófono" or "Microphone" in name
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            name = dev.get("name", "")
            if any(kw in name for kw in ["Micrófono", "Microphone", "Microfone"]):
                if "Iriun" not in name and "Virtual" not in name:
                    return i, name

    # Priority 3: System default
    default = sd.query_devices(kind="input")
    return None, default["name"]


# ─── Token ────────────────────────────────────────────────────────────────────

def load_token():
    """Load OpenClaw gateway token from config or environment."""
    # Try openclaw.json
    config_path = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        token = config["gateway"]["auth"]["token"]
        if token:
            return token
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass

    # Try environment variable
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if token:
        return token

    print("❌ Token não encontrado.")
    print("   Coloque em ~/.openclaw/openclaw.json ou exporte OPENCLAW_GATEWAY_TOKEN")
    sys.exit(1)


# ─── Recording ────────────────────────────────────────────────────────────────

def record_audio(mic_device):
    """Record audio from microphone until user presses ENTER."""
    frames = []
    stop_event = threading.Event()

    def callback(indata, frame_count, time_info, status):
        if status:
            print(f"  ⚠️ Audio status: {status}")
        frames.append(indata.copy())

    try:
        stream = sd.InputStream(
            device=mic_device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=callback,
        )
    except sd.PortAudioError as e:
        print(f"❌ Erro no microfone: {e}")
        return None

    print("  🔴 Gravando... (ENTER para parar)")
    stream.start()

    def wait_enter():
        input()
        stop_event.set()

    t = threading.Thread(target=wait_enter, daemon=True)
    t.start()
    stop_event.wait()

    stream.stop()
    stream.close()

    if not frames:
        return None

    audio_data = np.concatenate(frames, axis=0)

    # Check if audio has actual content (not just silence)
    peak = np.max(np.abs(audio_data))
    if peak < 100:
        print("  ⚠️ Áudio muito baixo — fala mais perto do microfone")
        return None

    # Save to temp WAV
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())

    return tmp.name


# ─── Transcription ────────────────────────────────────────────────────────────

def transcribe(audio_path, model):
    """Transcribe audio with Faster-Whisper. VAD filter enabled to avoid hallucinations."""
    try:
        segments, info = model.transcribe(
            audio_path,
            language="pt",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text
    except Exception as e:
        print(f"  ❌ Erro na transcrição: {e}")
        return ""


# ─── OpenClaw API ─────────────────────────────────────────────────────────────

def ask_openclaw(text, token, history):
    """Send text to OpenClaw gateway and return response."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    messages = list(history) + [{"role": "user", "content": text}]

    body = {
        "model": MODEL,
        "messages": messages,
    }

    try:
        resp = requests.post(GATEWAY_URL, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.ConnectionError:
        print("  ❌ OpenClaw não respondeu. Gateway tá rodando?")
        print(f"     URL: {GATEWAY_URL}")
        return None
    except requests.Timeout:
        print("  ❌ Timeout — OpenClaw demorou demais.")
        return None
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"  ❌ Erro: {e}")
        return None


# ─── TTS ──────────────────────────────────────────────────────────────────────

def speak(text):
    """Convert text to speech with edge-tts and play it."""
    # Truncate very long responses for TTS
    if len(text) > 1500:
        text = text[:1500] + "..."

    async def generate():
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        await communicate.save(AUDIO_FILE)

    asyncio.run(generate())

    if not os.path.exists(AUDIO_FILE) or os.path.getsize(AUDIO_FILE) < 100:
        print("  ⚠️ Erro ao gerar áudio")
        return

    # Play on Windows
    if sys.platform == "win32":
        subprocess.Popen(["start", "", AUDIO_FILE], shell=True)
    # Play on macOS
    elif sys.platform == "darwin":
        subprocess.Popen(["afplay", AUDIO_FILE])
    # Play on Linux
    else:
        for player in ["mpv", "ffplay", "aplay"]:
            if os.system(f"which {player} > /dev/null 2>&1") == 0:
                subprocess.Popen([player, "-nodisp", "-autoexit", AUDIO_FILE] if player == "ffplay" else [player, AUDIO_FILE])
                break


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  🎤 OpenClaw Voice Assistant")
    print("  Talk to your AI agent using your voice")
    print("=" * 55)
    print()

    # Load token
    token = load_token()
    print("✅ Token carregado")

    # Find microphone
    mic_device, mic_name = find_microphone()
    print(f"✅ Microfone: {mic_name}")

    # Load Whisper
    print(f"⏳ Carregando Whisper ({WHISPER_MODEL})...")
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    print(f"✅ Whisper pronto")
    print()

    # Conversation history (keeps last 10 exchanges for context)
    history = []
    MAX_HISTORY = 20  # 10 user + 10 assistant messages

    print("Comandos: ENTER = gravar | 'sair' = encerrar | 'limpar' = reset conversa")
    print("-" * 55)

    while True:
        print()
        cmd = input("🎤 ENTER para falar (ou digite comando): ").strip().lower()

        if cmd in ("sair", "exit", "quit"):
            print("👋 Até mais")
            break

        if cmd in ("limpar", "clear", "reset"):
            history.clear()
            print("🗑️ Histórico limpo")
            continue

        if cmd and cmd not in ("", " "):
            # User typed text instead of recording
            texto = cmd
            print(f"  📝 Texto: {texto}")
        else:
            # Record audio
            audio_path = record_audio(mic_device)
            if audio_path is None:
                print("  ⚠️ Sem áudio capturado")
                continue

            # Transcribe
            print("  📝 Transcrevendo...")
            texto = transcribe(audio_path, whisper)

            # Clean up temp file
            try:
                os.unlink(audio_path)
            except OSError:
                pass

            if not texto:
                print("  ⚠️ Não entendi — tenta de novo")
                continue

            print(f"  Tu: {texto}")

        # Send to OpenClaw
        print("  🧠 Pensando...")
        resposta = ask_openclaw(texto, token, history)

        if resposta is None:
            continue

        # Update history
        history.append({"role": "user", "content": texto})
        history.append({"role": "assistant", "content": resposta})
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        print(f"  🤖 {resposta}")

        # Speak response
        print("  🔊 Falando...")
        speak(resposta)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Até mais")
        sys.exit(0)
