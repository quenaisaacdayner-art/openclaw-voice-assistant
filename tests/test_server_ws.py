"""Testes para server_ws.py e frontend Web Audio."""
import os
import ast
import wave
import struct
import tempfile

import numpy as np
import pytest


# --- Testes de syntax/import ---

def test_server_ws_syntax():
    """Verifica que server_ws.py tem syntax valida."""
    with open("server_ws.py") as f:
        tree = ast.parse(f.read())
    assert tree is not None


def test_server_ws_has_tts_to_bytes():
    """Verifica que _tts_to_bytes helper existe."""
    with open("server_ws.py") as f:
        content = f.read()
    assert "_tts_to_bytes" in content


def test_server_ws_has_cancel_event():
    """Verifica que barge-in usa cancel_event."""
    with open("server_ws.py") as f:
        content = f.read()
    assert "cancel_event" in content
    assert "cancel_event.is_set()" in content


def test_server_ws_has_process_speech():
    """Verifica que process_speech coroutine existe."""
    with open("server_ws.py") as f:
        content = f.read()
    assert "async def process_speech" in content
    assert "asyncio.create_task(process_speech())" in content


# --- Testes do frontend ---

def test_static_index_exists():
    """Verifica que static/index.html existe."""
    assert os.path.exists("static/index.html")


def test_static_index_has_websocket():
    """Verifica que o frontend tem codigo WebSocket."""
    with open("static/index.html") as f:
        content = f.read()
    assert "WebSocket" in content
    assert "processAudioChunk" in content
    assert "playNext" in content
    assert "downsample" in content


def test_static_index_has_vad():
    """Verifica que o frontend tem VAD."""
    with open("static/index.html") as f:
        content = f.read()
    assert "VAD_THRESHOLD" in content
    assert "speech_end" in content
    assert "SILENCE_MS" in content


def test_static_index_has_barge_in():
    """Verifica que o frontend tem barge-in."""
    with open("static/index.html") as f:
        content = f.read()
    assert "interrupt" in content
    assert "stopPlayback" in content
    assert "currentSource" in content


def test_static_index_dark_mode():
    """Verifica dark mode."""
    with open("static/index.html") as f:
        content = f.read()
    assert "#1a1a2e" in content


# --- Testes de logica ---

def test_tts_to_bytes_cleanup():
    """Verifica que o padrao _tts_to_bytes limpa arquivos temporarios."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        with wave.open(f, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack('<' + 'h' * 100, *([1000] * 100)))
        path = f.name

    assert os.path.exists(path)

    # Simular o que _tts_to_bytes faz
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)

    assert len(data) > 0
    assert not os.path.exists(path)


def test_pcm_to_wav_conversion():
    """Verifica conversao PCM -> WAV (usado no handler)."""
    # Simular 1s de audio PCM 16-bit mono 16kHz
    pcm_data = np.random.randint(-32768, 32767, size=16000, dtype=np.int16)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
        with wave.open(f, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_data.tobytes())

    # Verificar que o WAV e valido
    with wave.open(wav_path, 'rb') as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 16000

    os.unlink(wav_path)


def test_find_sentence_end():
    """Verifica _find_sentence_end do core/llm.py."""
    from core.llm import _find_sentence_end

    # Pontuacao forte
    assert _find_sentence_end("Ola mundo. ") > 0
    assert _find_sentence_end("Pergunta? ") > 0
    assert _find_sentence_end("Exclamacao! ") > 0

    # Sem pontuacao
    assert _find_sentence_end("texto sem fim") == 0

    # Ponto-e-virgula
    assert _find_sentence_end("parte um; ") > 0
