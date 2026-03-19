"""
OpenClaw Voice Assistant — CLI (Terminal)
Fale com seu agente OpenClaw usando a voz — 100% grátis, roda localmente.

Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway API (LLM)
"""

import os
import sys
import wave
import threading
import subprocess
import numpy as np
import sounddevice as sd

from core.config import (
    WHISPER_MODEL_SIZE,
    load_token,
)
from core.stt import _get_whisper
from core.llm import ask_openclaw
from core.tts import generate_tts, init_piper

# ─── Constantes ───────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
CHANNELS = 1


# ─── Microphone ───────────────────────────────────────────────────────────────

def find_microphone():
    """Auto-detect the best microphone. Prefers Intel Smart Sound, falls back to default."""
    devices = sd.query_devices()

    # Prioridade 1: Intel Smart Sound (mic array do laptop)
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0 and "Intel" in dev.get("name", "") and "Smart Sound" in dev.get("name", ""):
            return i, dev["name"]

    # Prioridade 2: Qualquer mic real (não virtual)
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            name = dev.get("name", "")
            if any(kw in name for kw in ["Micrófono", "Microphone", "Microfone"]):
                if "Iriun" not in name and "Virtual" not in name:
                    return i, name

    # Prioridade 3: Default do sistema
    default = sd.query_devices(kind="input")
    return None, default["name"]


# ─── Recording ────────────────────────────────────────────────────────────────

def record_audio(mic_device):
    """Grava áudio do microfone até o usuário pressionar ENTER."""
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
        print(f"❌ Erro no microfone: {str(e)}")
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

    # Checar se áudio tem conteúdo (não só silêncio)
    peak = np.max(np.abs(audio_data))
    if peak < 100:
        print("  ⚠️ Áudio muito baixo — fala mais perto do microfone")
        return None

    # Salvar em WAV temporário
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

def transcribe(audio_path):
    """Transcreve áudio com Faster-Whisper. VAD filter habilitado."""
    try:
        segments, info = _get_whisper().transcribe(
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


# ─── Audio Playback ──────────────────────────────────────────────────────────

def play_audio(filepath):
    """Toca arquivo de áudio na plataforma atual."""
    if sys.platform == "win32":
        subprocess.Popen(["start", "", filepath], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["afplay", filepath])
    else:
        for player in ["mpv", "ffplay", "aplay"]:
            if os.system(f"which {player} > /dev/null 2>&1") == 0:
                subprocess.Popen(
                    [player, "-nodisp", "-autoexit", filepath]
                    if player == "ffplay"
                    else [player, filepath]
                )
                break


def speak(text):
    """Converte texto em voz e toca usando generate_tts do core."""
    if len(text) > 1500:
        text = text[:1500] + "..."

    audio_file = generate_tts(text)
    if audio_file:
        play_audio(audio_file)
    else:
        print("  ⚠️ Erro ao gerar áudio")


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  🎤 OpenClaw Voice Assistant")
    print("  Talk to your AI agent using your voice")
    print("=" * 55)
    print()

    # Carregar token
    try:
        token = load_token()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    print("✅ Token carregado")

    # Encontrar microfone
    mic_device, mic_name = find_microphone()
    print(f"✅ Microfone: {mic_name}")

    # Inicializar Piper TTS
    init_piper()

    # Carregar Whisper
    _get_whisper()
    print()

    # Histórico de conversa (mantém últimas 10 trocas)
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
            # Usuário digitou texto em vez de gravar
            texto = cmd
            print(f"  📝 Texto: {texto}")
        else:
            # Gravar áudio
            audio_path = record_audio(mic_device)
            if audio_path is None:
                print("  ⚠️ Sem áudio capturado")
                continue

            # Transcrever
            print("  📝 Transcrevendo...")
            texto = transcribe(audio_path)

            # Limpar arquivo temporário
            try:
                os.unlink(audio_path)
            except OSError:
                pass

            if not texto:
                print("  ⚠️ Não entendi — tenta de novo")
                continue

            print(f"  Tu: {texto}")

        # Enviar pro OpenClaw
        print("  🧠 Pensando...")
        resposta = ask_openclaw(texto, token, history)

        if resposta.startswith("❌"):
            print(f"  {resposta}")
            continue

        # Atualizar histórico
        history.append({"role": "user", "content": texto})
        history.append({"role": "assistant", "content": resposta})
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        print(f"  🤖 {resposta}")

        # Falar resposta
        print("  🔊 Falando...")
        speak(resposta)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Até mais")
        sys.exit(0)
