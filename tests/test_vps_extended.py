"""Extended tests for voice_assistant_vps.py — covers gaps in test_vps.py.

Captures current behavior — does NOT fix bugs.
"""
import os
import sys
import json
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _import_vps():
    with patch("voice_assistant_vps.load_token", return_value="test-token"):
        import voice_assistant_vps as mod
        return mod


# ─── handle_stop_recording (manual mode) ────────────────────────────────────

class TestHandleStopRecordingManual:
    def test_empty_buffer_returns_unchanged(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.audio_buffer = []
        listener.sample_rate = None

        history = [{"role": "user", "content": "existing"}]
        result_history, result_audio = mod.handle_stop_recording(history)
        assert result_history == history
        assert result_audio is None

    def test_none_sample_rate_returns_unchanged(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.audio_buffer = [np.ones(1000, dtype=np.float32)]
        listener.sample_rate = None

        result_history, result_audio = mod.handle_stop_recording([])
        assert result_audio is None

        # cleanup
        listener.audio_buffer = []

    def test_transcribes_accumulated_buffer(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.sample_rate = 48000
        listener.audio_buffer = [np.ones(1000, dtype=np.float32) * 0.5]

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.iter_lines.return_value = iter([
                'data: {"choices":[{"delta":{"content":"resposta"}}]}',
                "data: [DONE]",
            ])
            with patch.object(mod.requests, "post", return_value=mock_resp):
                with patch.object(mod, "generate_tts", return_value=None):
                    result_history, _ = mod.handle_stop_recording([])

        assert any("[🎤 Voz]" in m.get("content", "") for m in result_history)
        assert any(m["role"] == "assistant" for m in result_history)

    def test_empty_transcription_shows_warning(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.sample_rate = 48000
        listener.audio_buffer = [np.zeros(1000, dtype=np.float32)]

        with patch.object(mod, "transcribe_audio", return_value=""):
            result_history, result_audio = mod.handle_stop_recording([])

        assert any("Não captei" in m.get("content", "") for m in result_history)
        assert result_audio is None

    def test_clears_buffer_after_processing(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.sample_rate = 48000
        listener.audio_buffer = [np.ones(1000, dtype=np.float32)]

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod, "ask_openclaw", return_value="resp"):
                with patch.object(mod, "generate_tts", return_value=None):
                    with patch.object(mod, "ask_openclaw_stream", side_effect=Exception("fail")):
                        mod.handle_stop_recording([])

        assert listener.audio_buffer == [] or listener.sample_rate is None

    def test_streaming_fallback_on_exception(self):
        """If streaming fails, falls back to non-streaming ask_openclaw."""
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.sample_rate = 48000
        listener.audio_buffer = [np.ones(1000, dtype=np.float32) * 0.5]

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod, "ask_openclaw_stream", side_effect=Exception("fail")):
                with patch.object(mod, "ask_openclaw", return_value="fallback") as mock_ask:
                    with patch.object(mod, "generate_tts", return_value=None):
                        result_history, _ = mod.handle_stop_recording([])
                        mock_ask.assert_called_once()


# ─── handle_stop_recording (continuous mode) ─────────────────────────────────

class TestHandleStopRecordingContinuous:
    def test_transcribes_remaining_buffer(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = True
        listener.speech_detected = True
        listener.sample_rate = 48000
        listener.audio_buffer = [np.ones(1000, dtype=np.float32) * 0.5]

        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "frase final"
        mock_model.transcribe.return_value = ([seg], None)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            with patch.object(mod, "ask_openclaw", return_value="resp"):
                with patch.object(mod, "generate_tts", return_value=None):
                    result_history, _ = mod.handle_stop_recording([])

        assert any("frase final" in m.get("content", "") for m in result_history)

        # cleanup
        listener.active = False
        listener.reset()

    def test_no_speech_detected_resets(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = True
        listener.speech_detected = False
        listener.audio_buffer = []

        result_history, result_audio = mod.handle_stop_recording([])
        assert result_history == []
        assert result_audio is None

        listener.active = False

    def test_empty_transcription_resets(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = True
        listener.speech_detected = True
        listener.sample_rate = 48000
        listener.audio_buffer = [np.zeros(1000, dtype=np.float32)]  # silence

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            result_history, result_audio = mod.handle_stop_recording([])

        # No text transcribed → just reset, return unchanged
        assert result_audio is None

        listener.active = False
        listener.reset()


# ─── respond_text (VPS) ─────────────────────────────────────────────────────

class TestRespondTextVPS:
    def test_empty_message(self):
        mod = _import_vps()
        results = list(mod.respond_text("", []))
        last = results[-1]
        assert last[0] == ""  # text_input cleared
        assert last[2] is None  # no audio

    def test_whitespace_message(self):
        mod = _import_vps()
        results = list(mod.respond_text("   ", []))
        last = results[-1]
        assert last[2] is None

    def test_successful_streaming(self):
        mod = _import_vps()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter([
            'data: {"choices":[{"delta":{"content":"olá"}}]}',
            "data: [DONE]",
        ])

        with patch.object(mod.requests, "post", return_value=mock_resp):
            with patch.object(mod, "generate_tts", return_value=None):
                results = list(mod.respond_text("pergunta", []))
                last = results[-1]
                history = last[1]
                assert any(m.get("content") == "pergunta" for m in history)
                assert any(m.get("content") == "olá" for m in history)

    def test_exception_fallback(self):
        mod = _import_vps()
        with patch.object(mod, "ask_openclaw_stream", side_effect=Exception("err")):
            with patch.object(mod, "ask_openclaw", return_value="fallback"):
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_text("pergunta", []))
                    last = results[-1]
                    assert any(m.get("content") == "fallback" for m in last[1])

    def test_empty_stream_fallback(self):
        mod = _import_vps()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(["data: [DONE]"])

        with patch.object(mod.requests, "post", return_value=mock_resp):
            with patch.object(mod, "ask_openclaw", return_value="non-stream") as mock_ask:
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_text("pergunta", []))
                    mock_ask.assert_called_once()


# ─── respond_audio (VPS) ────────────────────────────────────────────────────

class TestRespondAudioVPS:
    def test_none_input(self):
        mod = _import_vps()
        results = list(mod.respond_audio(None, []))
        assert results[-1] == ([], None) or results[-1][1] is None

    def test_empty_transcription(self):
        mod = _import_vps()
        with patch.object(mod, "transcribe_audio", return_value=""):
            audio_input = (48000, np.zeros(1000, dtype=np.int16))
            results = list(mod.respond_audio(audio_input, []))
            last = results[-1]
            assert any("Não captei" in m.get("content", "") for m in last[0])

    def test_adds_voice_prefix(self):
        mod = _import_vps()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter([
            'data: {"choices":[{"delta":{"content":"resp"}}]}',
            "data: [DONE]",
        ])

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod.requests, "post", return_value=mock_resp):
                with patch.object(mod, "generate_tts", return_value=None):
                    audio_input = (48000, np.ones(1000, dtype=np.int16))
                    results = list(mod.respond_audio(audio_input, []))
                    last = results[-1]
                    user_msgs = [m for m in last[0] if m["role"] == "user"]
                    assert any("[🎤 Voz]" in m["content"] for m in user_msgs)

    def test_exception_fallback(self):
        mod = _import_vps()
        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod, "ask_openclaw_stream", side_effect=Exception("err")):
                with patch.object(mod, "ask_openclaw", return_value="fallback"):
                    with patch.object(mod, "generate_tts", return_value=None):
                        audio_input = (48000, np.ones(1000, dtype=np.int16))
                        results = list(mod.respond_audio(audio_input, []))
                        last = results[-1]
                        assert any(m.get("content") == "fallback" for m in last[0])


# ─── BrowserContinuousListener._transcribe_buffer edge cases ────────────────

class TestTranscribeBufferEdgeCases:
    def test_empty_buffer_returns_none(self):
        mod = _import_vps()
        listener = mod.BrowserContinuousListener()
        listener.audio_buffer = []
        result = listener._transcribe_buffer()
        assert result is None

    def test_none_sample_rate_returns_none(self):
        mod = _import_vps()
        listener = mod.BrowserContinuousListener()
        listener.audio_buffer = [np.ones(100, dtype=np.float32)]
        listener.sample_rate = None
        result = listener._transcribe_buffer()
        assert result is None

    def test_exception_returns_none(self):
        mod = _import_vps()
        listener = mod.BrowserContinuousListener()
        listener.active = True
        listener.sample_rate = 48000
        listener.audio_buffer = [np.ones(100, dtype=np.float32)]

        with patch.object(mod, "_get_whisper", side_effect=RuntimeError("no model")):
            result = listener._transcribe_buffer()
            assert result is None

        # Should be reset after error
        assert listener.audio_buffer == []
        assert listener.processing is False

    def test_empty_transcription_returns_none(self):
        mod = _import_vps()
        listener = mod.BrowserContinuousListener()
        listener.active = True
        listener.sample_rate = 48000
        listener.audio_buffer = [np.ones(100, dtype=np.float32)]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            result = listener._transcribe_buffer()
            assert result is None


# ─── handle_stream_chunk extended ────────────────────────────────────────────

class TestHandleStreamChunkExtended:
    def test_manual_mode_converts_stereo(self):
        """Manual mode accumulates chunks, converting stereo to mono."""
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.audio_buffer = []

        stereo = np.column_stack([
            np.ones(1000, dtype=np.float32),
            np.ones(1000, dtype=np.float32),
        ])
        mod.handle_stream_chunk((48000, stereo), [])

        assert len(listener.audio_buffer) == 1
        # Buffer should be mono (1D)
        assert len(listener.audio_buffer[0].shape) == 1

        listener.audio_buffer = []
        listener.sample_rate = None

    def test_manual_mode_converts_int16_to_float(self):
        """Manual mode converts int16 to float32."""
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.audio_buffer = []

        data = np.ones(1000, dtype=np.int16) * 1000
        mod.handle_stream_chunk((48000, data), [])

        assert listener.audio_buffer[0].dtype == np.float32

        listener.audio_buffer = []
        listener.sample_rate = None

    def test_continuous_mode_with_transcription(self):
        """When VAD detects speech end, processes the full flow."""
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = True
        listener.reset()

        with patch.object(listener, "feed_chunk", return_value="frase detectada"):
            with patch.object(mod, "ask_openclaw", return_value="resposta"):
                with patch.object(mod, "generate_tts", return_value="/tmp/audio.mp3"):
                    data = np.ones(1000, dtype=np.float32)
                    result_history, result_audio = mod.handle_stream_chunk((48000, data), [])

        assert any("frase detectada" in m.get("content", "") for m in result_history)
        assert result_audio == "/tmp/audio.mp3"

        listener.active = False
        listener.reset()


# ─── VPS ask_openclaw (non-streaming) ───────────────────────────────────────

class TestAskOpenClawVPS:
    def test_connection_error_returns_error_string(self):
        """VPS version returns error string (not None like CLI)."""
        mod = _import_vps()
        import requests as req
        with patch.object(mod.requests, "post", side_effect=req.ConnectionError()):
            result = mod.ask_openclaw("olá", [])
            assert "❌" in result
            assert "Gateway" in result

    def test_timeout_returns_error_string(self):
        mod = _import_vps()
        import requests as req
        with patch.object(mod.requests, "post", side_effect=req.Timeout()):
            result = mod.ask_openclaw("olá", [])
            assert "❌" in result
            assert "Timeout" in result

    def test_malformed_response(self):
        mod = _import_vps()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(mod.requests, "post", return_value=mock_resp):
            result = mod.ask_openclaw("olá", [])
            assert "❌" in result or "Erro" in result


# ─── VPS load_token ──────────────────────────────────────────────────────────

class TestLoadTokenVPS:
    def test_raises_runtime_error(self, tmp_path):
        """VPS version raises RuntimeError (not sys.exit like CLI)."""
        mod = _import_vps()
        with patch("os.path.expanduser", return_value=str(tmp_path)):
            env = os.environ.copy()
            env.pop("OPENCLAW_GATEWAY_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError, match="Token"):
                    mod.load_token()
