"""Tests for voice_assistant_app.py — LOCAL mode specifics.

Tests ContinuousListener, respond_text, respond_audio.
Adapted for unified core/ architecture.
"""
import os
import sys
import json
import tempfile
import wave
import queue
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.config as config
import core.tts
import core.stt


def _import_app():
    """Import app module with mocked startup side effects."""
    with patch("core.config.load_token", return_value="test-token"):
        with patch("core.tts.init_tts"):
            import voice_assistant_app as mod
            return mod


# ─── Configuration (via core.config) ────────────────────────────────────────

class TestWebConfig:
    def test_gateway_port_18789(self):
        assert "18789" in config.GATEWAY_URL

    def test_default_tts_engine_piper(self):
        assert config.TTS_ENGINE in ("piper", "edge", "kokoro")

    def test_piper_model_path(self):
        assert "pt_BR-faber-medium" in config.PIPER_MODEL


# ─── PyAudio Mic Detection ──────────────────────────────────────────────────

class TestFindMicPyAudio:
    def _make_mock_pa(self, devices):
        mock_pa = MagicMock()
        mock_pa.get_device_count.return_value = len(devices)
        mock_pa.get_device_info_by_index.side_effect = devices
        mock_pa.terminate = MagicMock()
        return mock_pa

    def test_prefers_intel_smart_sound(self):
        mod = _import_app()
        if not hasattr(mod, "find_mic_pyaudio"):
            pytest.skip("find_mic_pyaudio not available (BROWSER mode)")

        mock_pa = self._make_mock_pa([
            {"name": "Iriun Webcam", "maxInputChannels": 2},
            {"name": "Intel Smart Sound Mic", "maxInputChannels": 2},
            {"name": "Realtek Mic", "maxInputChannels": 1},
        ])
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_pa

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx == 1
            assert "Intel" in name

    def test_skips_virtual_and_iriun(self):
        mod = _import_app()
        if not hasattr(mod, "find_mic_pyaudio"):
            pytest.skip("find_mic_pyaudio not available (BROWSER mode)")

        mock_pa = self._make_mock_pa([
            {"name": "Iriun Webcam #4", "maxInputChannels": 2},
            {"name": "Virtual Cable", "maxInputChannels": 2},
            {"name": "Realtek Mic Array", "maxInputChannels": 2},
        ])
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_pa

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert "Iriun" not in name
            assert "Virtual" not in name

    def test_skips_mezcla_stereo_mix(self):
        mod = _import_app()
        if not hasattr(mod, "find_mic_pyaudio"):
            pytest.skip("find_mic_pyaudio not available (BROWSER mode)")

        mock_pa = self._make_mock_pa([
            {"name": "Mezcla estéreo", "maxInputChannels": 2},
            {"name": "Stereo Mix", "maxInputChannels": 2},
        ])
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_pa

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx is None

    def test_truncated_intel_name(self):
        mod = _import_app()
        if not hasattr(mod, "find_mic_pyaudio"):
            pytest.skip("find_mic_pyaudio not available (BROWSER mode)")

        mock_pa = self._make_mock_pa([
            {"name": "Intel Sma", "maxInputChannels": 2},
        ])
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_pa

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx == 0

    def test_output_only_devices_skipped(self):
        mod = _import_app()
        if not hasattr(mod, "find_mic_pyaudio"):
            pytest.skip("find_mic_pyaudio not available (BROWSER mode)")

        mock_pa = self._make_mock_pa([
            {"name": "Speakers", "maxInputChannels": 0},
            {"name": "Microphone", "maxInputChannels": 1},
        ])
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_pa

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx == 1

    def test_pyaudio_exception_returns_default(self):
        mod = _import_app()
        if not hasattr(mod, "find_mic_pyaudio"):
            pytest.skip("find_mic_pyaudio not available (BROWSER mode)")

        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.side_effect = Exception("no pyaudio")

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx is None
            assert name == "default"


# ─── Piper TTS (via core.tts) ──────────────────────────────────────────────

class TestPiperTTS:
    def test_generate_piper_returns_wav_path(self):
        mock_voice = MagicMock()

        class FakeChunk:
            audio_int16_bytes = b"\x00\x01" * 8000
            sample_channels = 1
            sample_width = 2
            sample_rate = 22050

        mock_voice.synthesize.return_value = [FakeChunk()]
        original_voice = core.tts.piper_voice
        core.tts.piper_voice = mock_voice

        result = core.tts.generate_tts_piper("teste")
        assert result is not None
        assert result.endswith(".wav")
        assert os.path.exists(result)
        os.unlink(result)

        core.tts.piper_voice = original_voice

    def test_generate_piper_returns_none_on_empty_audio(self):
        mock_voice = MagicMock()
        mock_voice.synthesize.return_value = []
        original_voice = core.tts.piper_voice
        core.tts.piper_voice = mock_voice

        result = core.tts.generate_tts_piper("teste")
        assert result is None

        core.tts.piper_voice = original_voice


# ─── Edge TTS (via core.tts) ──────────────────────────────────────────────

class TestEdgeTTS:
    def test_generate_edge_returns_mp3_path(self):
        import edge_tts as edge_tts_mod
        with patch("core.tts.edge_tts.Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                with open(path, "wb") as f:
                    f.write(b"fake mp3 data " * 20)

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            result = core.tts.generate_tts_edge("teste de voz")
            assert result is not None
            assert result.endswith(".mp3")
            assert os.path.exists(result)
            os.unlink(result)

    def test_generate_edge_returns_none_on_failure(self):
        with patch("core.tts.edge_tts.Communicate", side_effect=Exception("network error")):
            result = core.tts.generate_tts_edge("teste")
            assert result is None


# ─── ContinuousListener (RealtimeSTT) ───────────────────────────────────────

class TestContinuousListenerRealtimeSTT:
    def test_initial_state(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        assert listener.running is False
        assert listener.recorder is None
        assert listener.processing is False
        assert listener._stop_event is not None

    def test_get_text_empty_queue(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        assert listener.get_text() is None

    def test_get_text_returns_queued_text(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        listener.text_queue.put("olá mundo")
        assert listener.get_text() == "olá mundo"
        assert listener.get_text() is None

    def test_on_text_strips_whitespace(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        listener._on_text("  texto com espaços  ")
        result = listener.get_text()
        assert result == "texto com espaços"

    def test_on_text_ignores_empty(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        listener._on_text("")
        listener._on_text("   ")
        assert listener.get_text() is None

    def test_start_without_local_mode(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        if mod.MODE == "LOCAL":
            pytest.skip("Already in LOCAL mode")
        # In BROWSER mode, start should return False
        result = listener.start()
        assert result is False

    def test_stop_when_not_running(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        listener.stop()
        assert listener.running is False


# ─── Respond Text (streaming + TTS) ──────────────────────────────────────────

class TestRespondText:
    def test_empty_message_yields_none_audio(self):
        mod = _import_app()
        results = list(mod.respond_text("", []))
        assert len(results) >= 1
        last = results[-1]
        assert last[2] is None

    def test_whitespace_only_yields_none(self):
        mod = _import_app()
        results = list(mod.respond_text("   ", []))
        last = results[-1]
        assert last[2] is None

    def test_adds_user_message_to_history(self, mock_openai_response):
        mod = _import_app()

        with patch.object(mod, "ask_openclaw_stream") as mock_stream:
            mock_stream.return_value = iter(["resposta"])
            with patch.object(mod, "generate_tts", return_value=None):
                results = list(mod.respond_text("pergunta", []))
                last = results[-1]
                assert last[0] == ""
                history = last[1]
                assert any(m["role"] == "user" and m["content"] == "pergunta" for m in history)
                assert any(m["role"] == "assistant" for m in history)


# ─── Respond Audio ────────────────────────────────────────────────────────────

class TestRespondAudio:
    def test_none_input(self):
        mod = _import_app()
        results = list(mod.respond_audio(None, []))
        assert len(results) >= 1
        last = results[-1]
        assert last[1] is None

    def test_empty_transcription(self):
        mod = _import_app()
        with patch.object(mod, "transcribe_audio", return_value=""):
            results = list(mod.respond_audio((48000, np.zeros(1000, dtype=np.int16)), []))
            last = results[-1]
            history = last[0]
            assert any("Não captei" in m.get("content", "") for m in history)

    def test_voice_prefix_in_history(self, mock_openai_response):
        mod = _import_app()

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod, "ask_openclaw_stream") as mock_stream:
                mock_stream.return_value = iter(["oi"])
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_audio(
                        (48000, np.ones(1000, dtype=np.int16)),
                        [],
                    ))
                    last = results[-1]
                    history = last[0]
                    user_msgs = [m for m in history if m["role"] == "user"]
                    assert any("[🎤 Voz]" in m["content"] for m in user_msgs)
