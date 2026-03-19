"""Text-to-Speech — Piper (local) + Edge TTS (online) com fallback automático."""

import os
import wave
import asyncio
import tempfile
import concurrent.futures

import edge_tts

from core.config import TTS_ENGINE, TTS_VOICE, PIPER_MODEL

# Piper TTS (local, importado condicionalmente)
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

# Globais do módulo
piper_voice = None
_previous_tts_file = None
_tts_engine = TTS_ENGINE  # cópia mutável (pode mudar se Piper indisponível)


def init_piper():
    """Carrega modelo Piper se disponível. Retorna True se carregou."""
    global piper_voice, _tts_engine

    if _tts_engine == "piper" and PIPER_AVAILABLE and os.path.exists(PIPER_MODEL):
        print(f"⏳ Carregando Piper TTS ({os.path.basename(PIPER_MODEL)})...")
        piper_voice = PiperVoice.load(PIPER_MODEL)
        print("✅ Piper TTS pronto")
        return True
    elif _tts_engine == "piper":
        print("⚠️ Piper indisponível — usando Edge TTS como fallback")
        _tts_engine = "edge"
        return False

    # TTS_ENGINE != "piper" (ex: "edge")
    print(f"✅ Edge TTS ({TTS_VOICE})")
    return False


def generate_tts_piper(text):
    """Gera TTS com Piper (local). Retorna path do WAV ou None."""
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
    """Gera TTS com Edge TTS (Microsoft, online). Retorna path do MP3 ou None."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()

    try:
        async def _gen():
            communicate = edge_tts.Communicate(text, TTS_VOICE)
            await communicate.save(tmp.name)

        # Gradio 6.x roda seu próprio event loop — asyncio.run() crasharia.
        # Roda em thread separada com seu próprio loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _gen()).result(timeout=30)

        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 100:
            return tmp.name
    except Exception:
        pass
    return None


def generate_tts(text):
    """Gera áudio TTS. Usa Piper (local) ou Edge (online) conforme config."""
    global _previous_tts_file

    if not text or text.startswith("❌"):
        return None

    # Limpar arquivo TTS anterior (Gradio já serviu)
    if _previous_tts_file:
        try:
            os.unlink(_previous_tts_file)
        except OSError:
            pass

    # Truncar pra TTS
    tts_text = text[:1500] + "..." if len(text) > 1500 else text

    result = None
    if _tts_engine == "piper" and piper_voice is not None:
        result = generate_tts_piper(tts_text)
        if not result:
            # Fallback pra Edge se Piper falhar
            result = generate_tts_edge(tts_text)
    else:
        result = generate_tts_edge(tts_text)

    _previous_tts_file = result
    return result
