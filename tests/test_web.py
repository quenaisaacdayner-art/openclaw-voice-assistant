"""Tests for voice_assistant_web.py — Local web version specifics.

Captures current behavior — does NOT fix bugs.
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


def _import_web():
    """Import web module with mocked startup side effects."""
    with patch("voice_assistant_web.load_token", return_value="test-token"):
        with patch("voice_assistant_web.find_mic_pyaudio", return_value=(0, "Test Mic")):
            import voice_assistant_web as mod
            return mod


# ─── Web Configuration ───────────────────────────────────────────────────────

class TestWebConfig:
    def test_gateway_port_18789(self):
        mod = _import_web()
        assert "18789" in mod.GATEWAY_URL

    def test_default_tts_engine_piper(self):
        mod = _import_web()
        # Web version defaults to piper (local)
        assert mod.TTS_ENGINE in ("piper", "edge")

    def test_piper_model_path(self):
        mod = _import_web()
        assert "pt_BR-faber-medium" in mod.PIPER_MODEL


# ─── PyAudio Mic Detection ──────────────────────────────────────────────────

class TestFindMicPyAudio:
    """PyAudio is imported INSIDE find_mic_pyaudio() — need to patch the import."""

    def _make_mock_pa(self, devices):
        mock_pa = MagicMock()
        mock_pa.get_device_count.return_value = len(devices)
        mock_pa.get_device_info_by_index.side_effect = devices
        mock_pa.terminate = MagicMock()
        return mock_pa

    def test_prefers_intel_smart_sound(self):
        mod = _import_web()
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
        mod = _import_web()
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
        mod = _import_web()
        mock_pa = self._make_mock_pa([
            {"name": "Mezcla estéreo", "maxInputChannels": 2},
            {"name": "Stereo Mix", "maxInputChannels": 2},
        ])
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_pa

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx is None  # no real mic found

    def test_truncated_intel_name(self):
        """Intel Smart Sound name may be truncated in PyAudio."""
        mod = _import_web()
        mock_pa = self._make_mock_pa([
            {"name": "Intel Sma", "maxInputChannels": 2},
        ])
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_pa

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx == 0

    def test_output_only_devices_skipped(self):
        mod = _import_web()
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
        mod = _import_web()
        mock_pyaudio = MagicMock()
        mock_pyaudio.PyAudio.side_effect = Exception("no pyaudio")

        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            idx, name = mod.find_mic_pyaudio()
            assert idx is None
            assert name == "default"


# ─── Piper TTS (web only) ────────────────────────────────────────────────────

class TestPiperTTS:
    def test_generate_piper_returns_wav_path(self):
        mod = _import_web()
        if not hasattr(mod, "generate_tts_piper"):
            pytest.skip("generate_tts_piper not available")

        mock_voice = MagicMock()

        class FakeChunk:
            audio_int16_bytes = b"\x00\x01" * 8000
            sample_channels = 1
            sample_width = 2
            sample_rate = 22050

        mock_voice.synthesize.return_value = [FakeChunk()]
        mod.piper_voice = mock_voice

        result = mod.generate_tts_piper("teste")
        assert result is not None
        assert result.endswith(".wav")
        assert os.path.exists(result)

        # Cleanup
        os.unlink(result)

    def test_generate_piper_returns_none_on_empty_audio(self):
        mod = _import_web()
        if not hasattr(mod, "generate_tts_piper"):
            pytest.skip("generate_tts_piper not available")

        mock_voice = MagicMock()
        mock_voice.synthesize.return_value = []  # no chunks
        mod.piper_voice = mock_voice

        result = mod.generate_tts_piper("teste")
        assert result is None


# ─── Edge TTS (shared) ──────────────────────────────────────────────────────

class TestEdgeTTS:
    def test_generate_edge_returns_mp3_path(self):
        mod = _import_web()
        if not hasattr(mod, "generate_tts_edge"):
            pytest.skip("generate_tts_edge not available")

        with patch.object(mod.edge_tts, "Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                with open(path, "wb") as f:
                    f.write(b"fake mp3 data " * 20)

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            result = mod.generate_tts_edge("teste de voz")
            assert result is not None
            assert result.endswith(".mp3")
            assert os.path.exists(result)

            # Cleanup
            os.unlink(result)

    def test_generate_edge_returns_none_on_failure(self):
        mod = _import_web()
        if not hasattr(mod, "generate_tts_edge"):
            pytest.skip("generate_tts_edge not available")

        with patch.object(mod.edge_tts, "Communicate", side_effect=Exception("network error")):
            result = mod.generate_tts_edge("teste")
            assert result is None


# ─── ContinuousListener (RealtimeSTT — web only) ─────────────────────────────

class TestContinuousListenerRealtimeSTT:
    def test_initial_state(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        assert listener.running is False
        assert listener.recorder is None
        assert listener.processing is False
        assert listener._stop_event is not None

    def test_get_text_empty_queue(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        assert listener.get_text() is None

    def test_get_text_returns_queued_text(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        listener.text_queue.put("olá mundo")
        assert listener.get_text() == "olá mundo"
        assert listener.get_text() is None  # queue now empty

    def test_on_text_strips_whitespace(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        listener._on_text("  texto com espaços  ")
        result = listener.get_text()
        assert result == "texto com espaços"

    def test_on_text_ignores_empty(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        listener._on_text("")
        listener._on_text("   ")
        assert listener.get_text() is None

    def test_start_without_realtime_stt(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        original = mod.REALTIME_STT_AVAILABLE

        mod.REALTIME_STT_AVAILABLE = False
        result = listener.start()
        assert result is False

        mod.REALTIME_STT_AVAILABLE = original

    def test_stop_when_not_running(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        # Should not crash
        listener.stop()
        assert listener.running is False


# ─── Respond Text (streaming + TTS) ──────────────────────────────────────────

class TestRespondText:
    def test_empty_message_yields_none_audio(self):
        mod = _import_web()
        results = list(mod.respond_text("", []))
        assert len(results) >= 1
        # Should yield ("", history, None)
        last = results[-1]
        assert last[2] is None  # no audio

    def test_whitespace_only_yields_none(self):
        mod = _import_web()
        results = list(mod.respond_text("   ", []))
        last = results[-1]
        assert last[2] is None

    def test_adds_user_message_to_history(self, mock_openai_response):
        mod = _import_web()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter([
            'data: {"choices":[{"delta":{"content":"resposta"}}]}',
            "data: [DONE]",
        ])

        with patch.object(mod.requests, "post", return_value=mock_resp):
            with patch.object(mod, "generate_tts", return_value=None):
                results = list(mod.respond_text("pergunta", []))
                last = results[-1]
                # text_input should be cleared
                assert last[0] == ""
                # History should have user + assistant
                history = last[1]
                assert any(m["role"] == "user" and m["content"] == "pergunta" for m in history)
                assert any(m["role"] == "assistant" for m in history)


# ─── Respond Audio ────────────────────────────────────────────────────────────

class TestRespondAudio:
    def test_none_input(self):
        mod = _import_web()
        results = list(mod.respond_audio(None, []))
        assert len(results) >= 1
        last = results[-1]
        assert last[1] is None  # no audio

    def test_empty_transcription(self):
        mod = _import_web()
        with patch.object(mod, "transcribe_audio", return_value=""):
            results = list(mod.respond_audio((48000, np.zeros(1000, dtype=np.int16)), []))
            last = results[-1]
            history = last[0]
            assert any("Não captei" in m.get("content", "") for m in history)

    def test_voice_prefix_in_history(self, mock_openai_response):
        mod = _import_web()

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.iter_lines.return_value = iter([
                'data: {"choices":[{"delta":{"content":"oi"}}]}',
                "data: [DONE]",
            ])
            with patch.object(mod.requests, "post", return_value=mock_resp):
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_audio(
                        (48000, np.ones(1000, dtype=np.int16)),
                        [],
                    ))
                    last = results[-1]
                    history = last[0]
                    # Voice input gets [🎤 Voz] prefix
                    user_msgs = [m for m in history if m["role"] == "user"]
                    assert any("[🎤 Voz]" in m["content"] for m in user_msgs)
