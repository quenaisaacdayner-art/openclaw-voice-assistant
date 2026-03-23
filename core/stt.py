"""Speech-to-Text — Whisper com lazy loading thread-safe."""

import os
import tempfile
import threading

import numpy as np
from faster_whisper import WhisperModel
import scipy.io.wavfile as wavfile

from core.config import WHISPER_MODEL_SIZE

_whisper_model = None
_whisper_lock = threading.Lock()
_current_model_size = WHISPER_MODEL_SIZE


def _get_whisper():
    """Retorna modelo Whisper com double-check locking."""
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                print(f"⏳ Carregando Whisper ({_current_model_size})...")
                _whisper_model = WhisperModel(
                    _current_model_size, device="cpu", compute_type="int8"
                )
                print("✅ Whisper pronto")
    return _whisper_model


def set_whisper_model(model_name):
    """Muda o modelo Whisper em runtime. O próximo transcribe_audio() usará o novo modelo."""
    global _whisper_model, _current_model_size
    if model_name != _current_model_size:
        _current_model_size = model_name
        _whisper_model = None
        print(f"[STT] Modelo Whisper será alterado para '{model_name}' na próxima transcrição")


def get_current_model():
    """Retorna o nome do modelo Whisper atual."""
    return _current_model_size


def init_stt():
    """Pre-warm: carrega modelo Whisper no startup."""
    import time
    t0 = time.time()
    _get_whisper()
    elapsed = time.time() - t0
    print(f"[WARMUP] Whisper ({_current_model_size}) carregado em {elapsed:.1f}s")


def transcribe_audio(audio_input):
    """Transcreve áudio de componente gr.Audio. Recebe tuple (sample_rate, numpy_array)."""
    if audio_input is None:
        return ""

    sr, audio_data = audio_input

    # Converter pra mono se estéreo
    if len(audio_data.shape) > 1:
        audio_data = audio_data.mean(axis=1)

    # Normalizar pra int16 se float
    if audio_data.dtype in (np.float32, np.float64):
        audio_data = (audio_data * 32767).astype(np.int16)

    # Salvar em WAV temporário
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    wavfile.write(tmp.name, sr, audio_data)

    try:
        segments, _ = _get_whisper().transcribe(
            tmp.name,
            language="pt",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,      # era 500 — reduzir pra pular silêncios internos mais rápido
                speech_pad_ms=100,                 # padding em torno de fala detectada (default 400 — reduzir)
            ),
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
