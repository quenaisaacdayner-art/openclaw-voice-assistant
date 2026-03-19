"""Shared fixtures for voice assistant tests."""
import os
import sys
import json
import tempfile
import numpy as np
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def fake_openclaw_config(tmp_path):
    """Create a fake ~/.openclaw/openclaw.json with a test token."""
    config_dir = tmp_path / ".openclaw"
    config_dir.mkdir()
    config_file = config_dir / "openclaw.json"
    config_file.write_text(json.dumps({
        "gateway": {
            "auth": {
                "token": "test-token-abc123"
            }
        }
    }))
    return str(config_file)


@pytest.fixture
def fake_openclaw_config_no_token(tmp_path):
    """Config file exists but token is missing."""
    config_dir = tmp_path / ".openclaw"
    config_dir.mkdir()
    config_file = config_dir / "openclaw.json"
    config_file.write_text(json.dumps({"gateway": {}}))
    return str(config_file)


@pytest.fixture
def fake_wav_file(tmp_path):
    """Create a real WAV file with 1 second of sine wave at 440Hz."""
    import wave
    filepath = str(tmp_path / "test_audio.wav")
    sr = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio.tobytes())
    return filepath


@pytest.fixture
def silent_wav_file(tmp_path):
    """WAV file with only silence (peak < 100)."""
    import wave
    filepath = str(tmp_path / "silent.wav")
    sr = 16000
    audio = np.zeros(16000, dtype=np.int16)  # 1 second of silence

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio.tobytes())
    return filepath


@pytest.fixture
def gradio_audio_int16():
    """Simulate Gradio audio input as (sample_rate, numpy_int16_array)."""
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    audio = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
    return (sr, audio)


@pytest.fixture
def gradio_audio_float32():
    """Simulate Gradio audio input as (sample_rate, numpy_float32_array)."""
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    return (sr, audio)


@pytest.fixture
def gradio_audio_stereo():
    """Simulate stereo Gradio audio input."""
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    left = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    right = (np.sin(2 * np.pi * 880 * t) * 0.3).astype(np.float32)
    stereo = np.column_stack([left, right])
    return (sr, stereo)


@pytest.fixture
def mock_openai_response():
    """Standard OpenClaw/OpenAI chat completion response."""
    return {
        "choices": [{
            "message": {
                "content": "Resposta do agente OpenClaw."
            }
        }]
    }


@pytest.fixture
def mock_openai_stream_lines():
    """SSE lines simulating a streaming response."""
    return [
        'data: {"choices":[{"delta":{"content":"Olá"}}]}',
        'data: {"choices":[{"delta":{"content":" Dayner"}}]}',
        'data: {"choices":[{"delta":{"content":"."}}]}',
        'data: {"choices":[{"delta":{"content":" Tudo"}}]}',
        'data: {"choices":[{"delta":{"content":" bem?"}}]}',
        'data: [DONE]',
    ]
