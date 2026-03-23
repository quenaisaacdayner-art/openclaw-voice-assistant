"""Text-to-Speech — Kokoro (local) + Piper (local) + Edge TTS (online) com fallback automático."""

import os
import sys
import wave
import asyncio
import tempfile
import concurrent.futures

import requests
import edge_tts

from core.config import TTS_ENGINE, TTS_VOICE, PIPER_MODEL, PROJECT_DIR

PIPER_MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
PIPER_MODEL_JSON_URL = PIPER_MODEL_URL + ".json"

KOKORO_MODEL_DIR = os.path.join(PROJECT_DIR, "models")
KOKORO_MODEL_PATH = os.path.join(KOKORO_MODEL_DIR, "kokoro-v1.0.onnx")
KOKORO_VOICES_PATH = os.path.join(KOKORO_MODEL_DIR, "voices-v1.0.bin")
KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "pm_alex")  # voz PT-BR masculina
KOKORO_LANG = "pt-br"

# Piper TTS (local, importado condicionalmente)
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

# Kokoro TTS (local, importado condicionalmente)
try:
    from kokoro_onnx import Kokoro
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

AVAILABLE_VOICES = {
    "kokoro": [
        {"id": "pm_alex", "name": "Alex (Masculino)", "gender": "M"},
        {"id": "pf_dora", "name": "Dora (Feminino)", "gender": "F"},
    ],
    "edge": [
        {"id": "pt-BR-AntonioNeural", "name": "Antonio (Masculino)", "gender": "M"},
        {"id": "pt-BR-FranciscaNeural", "name": "Francisca (Feminino)", "gender": "F"},
        {"id": "pt-BR-ThalitaNeural", "name": "Thalita (Feminino)", "gender": "F"},
        {"id": "pt-BR-BrendaNeural", "name": "Brenda (Feminino)", "gender": "F"},
        {"id": "pt-BR-DonatoNeural", "name": "Donato (Masculino)", "gender": "M"},
        {"id": "pt-BR-ElzaNeural", "name": "Elza (Feminino)", "gender": "F"},
    ],
    "piper": [
        {"id": "pt_BR-faber-medium", "name": "Faber (Masculino)", "gender": "M"},
    ],
}

# Globais do módulo
piper_voice = None
kokoro_instance = None
_old_tts_files = []  # lista de arquivos pra limpar (com delay)
_previous_tts_file = None
_tts_engine = TTS_ENGINE  # cópia mutável (pode mudar se engine indisponível)
_kokoro_voice = KOKORO_VOICE   # default: "pm_alex"
_edge_voice = TTS_VOICE        # default: "pt-BR-AntonioNeural"
_tts_speed = 1.0               # 0.5 a 2.0


def _download_file(url, path):
    """Baixa arquivo de URL para path com progresso."""
    filename = os.path.basename(path)
    print(f"⬇️  Baixando {filename}...")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                print(f"\r   {pct}% ({downloaded}/{total} bytes)", end="", flush=True)
    print(f"\n✅ {filename} baixado")


def download_piper_model():
    """Baixa modelo Piper se não existe localmente. Mostra progresso."""
    model_dir = os.path.dirname(PIPER_MODEL)
    os.makedirs(model_dir, exist_ok=True)

    for url, path in [(PIPER_MODEL_URL, PIPER_MODEL),
                      (PIPER_MODEL_JSON_URL, PIPER_MODEL + ".json")]:
        if os.path.exists(path):
            continue
        _download_file(url, path)


def download_kokoro_model():
    """Baixa modelos Kokoro se não existem localmente."""
    os.makedirs(KOKORO_MODEL_DIR, exist_ok=True)

    for url, path in [(KOKORO_MODEL_URL, KOKORO_MODEL_PATH),
                      (KOKORO_VOICES_URL, KOKORO_VOICES_PATH)]:
        if os.path.exists(path):
            continue
        _download_file(url, path)


def init_kokoro():
    """Carrega Kokoro TTS se disponível. Retorna True se carregou."""
    global kokoro_instance, _tts_engine

    if not KOKORO_AVAILABLE:
        print("⚠️ Kokoro indisponível (kokoro-onnx não instalado) — tentando Piper")
        _tts_engine = "piper"
        return False

    try:
        download_kokoro_model()
    except Exception as e:
        print(f"⚠️ Erro ao baixar modelo Kokoro: {e} — tentando Piper")
        _tts_engine = "piper"
        return False

    if os.path.exists(KOKORO_MODEL_PATH) and os.path.exists(KOKORO_VOICES_PATH):
        print("⏳ Carregando Kokoro TTS...")
        kokoro_instance = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
        print(f"✅ Kokoro TTS pronto (voz: {KOKORO_VOICE}, lang: {KOKORO_LANG})")
        return True

    print("⚠️ Modelos Kokoro não encontrados — tentando Piper")
    _tts_engine = "piper"
    return False


def init_piper():
    """Carrega modelo Piper se disponível. Retorna True se carregou."""
    global piper_voice, _tts_engine

    if _tts_engine == "piper" and PIPER_AVAILABLE:
        download_piper_model()

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


def init_tts():
    """Inicializa o engine TTS configurado, com fallback automático: kokoro → piper → edge."""
    global _tts_engine

    if _tts_engine == "kokoro":
        if init_kokoro():
            return
        # fallback: tenta piper
        _tts_engine = "piper"

    if _tts_engine == "piper":
        if init_piper():
            return
        # init_piper já faz fallback pra edge

    if _tts_engine == "edge":
        print(f"✅ Edge TTS ({TTS_VOICE})")


def get_available_voices():
    return AVAILABLE_VOICES.get(_tts_engine, [])


def get_current_voice():
    if _tts_engine == "kokoro": return _kokoro_voice
    elif _tts_engine == "edge": return _edge_voice
    elif _tts_engine == "piper": return "pt_BR-faber-medium"
    return ""


def set_voice(voice_id):
    global _kokoro_voice, _edge_voice
    available = AVAILABLE_VOICES.get(_tts_engine, [])
    valid_ids = [v["id"] for v in available]
    if voice_id not in valid_ids:
        print(f"[TTS] Voz '{voice_id}' inválida. Disponíveis: {valid_ids}")
        return False
    if _tts_engine == "kokoro":
        old = _kokoro_voice; _kokoro_voice = voice_id
        print(f"[TTS] Voz: {old} → {voice_id}")
    elif _tts_engine == "edge":
        old = _edge_voice; _edge_voice = voice_id
        print(f"[TTS] Voz: {old} → {voice_id}")
    else:
        return False
    return True


def get_speed():
    return _tts_speed


def set_speed(speed):
    global _tts_speed
    speed = max(0.5, min(2.0, float(speed)))
    old = _tts_speed
    _tts_speed = speed
    if old != speed: print(f"[TTS] Velocidade: {old}x → {speed}x")
    return True


def warmup_tts():
    """Pre-warm: gera TTS dummy pra abrir conexões."""
    import time
    t0 = time.time()
    if _tts_engine == "edge":
        # Edge TTS: gerar dummy pra abrir WebSocket com Microsoft
        try:
            generate_tts_edge("ok")
        except Exception:
            pass
    elif _tts_engine == "kokoro" and kokoro_instance is not None:
        try:
            generate_tts_kokoro("ok")
        except Exception:
            pass
    elif _tts_engine == "piper" and piper_voice is not None:
        try:
            generate_tts_piper("ok")
        except Exception:
            pass
    elapsed = time.time() - t0
    print(f"[WARMUP] TTS ({_tts_engine}) pronto em {elapsed:.1f}s")


def generate_tts_kokoro(text):
    """Gera TTS com Kokoro (local). Retorna path do WAV ou None."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    try:
        import soundfile as sf
        samples, sample_rate = kokoro_instance.create(
            text, voice=_kokoro_voice, speed=_tts_speed, lang=KOKORO_LANG
        )
        sf.write(tmp.name, samples, sample_rate)

        if os.path.getsize(tmp.name) > 100:
            return tmp.name
    except Exception:
        pass
    return None


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
            kwargs = {"voice": _edge_voice}
            if _tts_speed != 1.0:
                pct = round((_tts_speed - 1.0) * 100)
                kwargs["rate"] = f"+{pct}%" if pct > 0 else f"{pct}%"
            communicate = edge_tts.Communicate(text, **kwargs)
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
    """Gera áudio TTS. Usa Kokoro, Piper ou Edge conforme config, com fallback."""
    global _previous_tts_file

    # Intencional: só filtra ❌ no início. Na prática, erros sempre começam com ❌.
    if not text or text.startswith("❌"):
        return None

    # Limpar arquivos TTS antigos (mantém os 2 mais recentes pro Gradio servir)
    if _previous_tts_file:
        _old_tts_files.append(_previous_tts_file)
    while len(_old_tts_files) > 2:
        old = _old_tts_files.pop(0)
        try:
            os.unlink(old)
        except OSError:
            pass

    # Truncar pra TTS
    tts_text = text[:1500] + "..." if len(text) > 1500 else text

    result = None

    # Kokoro → Piper → Edge (fallback chain)
    if _tts_engine == "kokoro" and kokoro_instance is not None:
        result = generate_tts_kokoro(tts_text)
        if not result:
            # Fallback pra Piper
            if piper_voice is not None:
                result = generate_tts_piper(tts_text)
            if not result:
                result = generate_tts_edge(tts_text)
    elif _tts_engine == "piper" and piper_voice is not None:
        result = generate_tts_piper(tts_text)
        if not result:
            # Fallback pra Edge se Piper falhar
            result = generate_tts_edge(tts_text)
    else:
        result = generate_tts_edge(tts_text)

    _previous_tts_file = result
    return result
