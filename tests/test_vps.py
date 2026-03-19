"""Tests for voice_assistant_app.py — BROWSER mode specifics.

Tests BrowserContinuousListener, toggle_listening, handle_stream_chunk.
Adapted for unified core/ architecture.
"""
import os
import sys
import json
import tempfile
import queue
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.config as config
import core.tts
import core.llm


def _import_app():
    with patch("core.config.load_token", return_value="test-token"):
        with patch("core.tts.init_piper"):
            import voice_assistant_app as mod
            return mod


# ─── Configuration (via core.config) ────────────────────────────────────────

class TestVPSConfig:
    def test_gateway_url_is_configurable(self):
        """Gateway URL comes from core.config, configurable via env var."""
        assert config.GATEWAY_URL.endswith("/v1/chat/completions")

    def test_tts_uses_core(self):
        """TTS functions come from core.tts."""
        assert hasattr(core.tts, "generate_tts")
        assert hasattr(core.tts, "generate_tts_edge")


# ─── BrowserContinuousListener ───────────────────────────────────────────────

class TestBrowserContinuousListener:
    def _make_listener(self):
        mod = _import_app()
        return mod.BrowserContinuousListener()

    def test_initial_state(self):
        listener = self._make_listener()
        assert listener.active is False
        assert listener.speech_detected is False
        assert listener.processing is False
        assert listener.audio_buffer == []
        assert listener.sample_rate is None
        assert listener.silence_count == 0

    def test_reset_clears_state(self):
        listener = self._make_listener()
        listener.audio_buffer = [np.array([1, 2, 3])]
        listener.silence_count = 5
        listener.speech_detected = True
        listener.sample_rate = 48000
        listener.reset()

        assert listener.audio_buffer == []
        assert listener.silence_count == 0
        assert listener.speech_detected is False
        assert listener.sample_rate is None

    def test_feed_chunk_returns_none_when_inactive(self):
        listener = self._make_listener()
        listener.active = False
        result = listener.feed_chunk(48000, np.ones(1000, dtype=np.float32))
        assert result is None

    def test_feed_chunk_returns_none_when_processing(self):
        listener = self._make_listener()
        listener.active = True
        listener.processing = True
        result = listener.feed_chunk(48000, np.ones(1000, dtype=np.float32))
        assert result is None

    def test_silence_threshold_default(self):
        listener = self._make_listener()
        assert listener.SILENCE_THRESHOLD == 0.01

    def test_silence_chunks_needed(self):
        listener = self._make_listener()
        assert listener.SILENCE_CHUNKS_NEEDED == 8

    def test_min_speech_chunks(self):
        listener = self._make_listener()
        assert listener.MIN_SPEECH_CHUNKS == 3

    def test_loud_audio_sets_speech_detected(self):
        listener = self._make_listener()
        listener.active = True
        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.speech_detected is True
        assert len(listener.audio_buffer) == 1

    def test_silence_after_speech_increments_counter(self):
        listener = self._make_listener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.silence_count == 0

        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        assert listener.silence_count == 1
        assert len(listener.audio_buffer) == 2

    def test_silence_without_speech_does_nothing(self):
        listener = self._make_listener()
        listener.active = True
        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        assert listener.silence_count == 0
        assert len(listener.audio_buffer) == 0

    def test_triggers_transcription_after_enough_silence(self):
        listener = self._make_listener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        for _ in range(listener.MIN_SPEECH_CHUNKS):
            result = listener.feed_chunk(48000, loud)
            assert result is None

        silent = np.zeros(1000, dtype=np.float32)

        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "transcrição teste"
        mock_model.transcribe.return_value = ([seg], None)

        with patch("core.stt._get_whisper", return_value=mock_model):
            for i in range(listener.SILENCE_CHUNKS_NEEDED - 1):
                result = listener.feed_chunk(48000, silent)
                assert result is None

            result = listener.feed_chunk(48000, silent)
            assert result == "transcrição teste"

    def test_resets_after_transcription(self):
        listener = self._make_listener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        for _ in range(listener.MIN_SPEECH_CHUNKS):
            listener.feed_chunk(48000, loud)

        silent = np.zeros(1000, dtype=np.float32)

        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "teste"
        mock_model.transcribe.return_value = ([seg], None)

        with patch("core.stt._get_whisper", return_value=mock_model):
            for _ in range(listener.SILENCE_CHUNKS_NEEDED):
                listener.feed_chunk(48000, silent)

        assert listener.audio_buffer == []
        assert listener.speech_detected is False
        assert listener.processing is False

    def test_handles_stereo_input(self):
        listener = self._make_listener()
        listener.active = True

        stereo = np.column_stack([
            np.ones(1000, dtype=np.float32) * 0.5,
            np.ones(1000, dtype=np.float32) * 0.3,
        ])
        listener.feed_chunk(48000, stereo)
        assert listener.speech_detected is True

    def test_handles_int16_input(self):
        listener = self._make_listener()
        listener.active = True

        loud_int16 = (np.ones(1000, dtype=np.float32) * 16000).astype(np.int16)
        listener.feed_chunk(48000, loud_int16)
        assert listener.speech_detected is True

    def test_not_enough_speech_chunks_behavior(self):
        listener = self._make_listener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.speech_detected is True

        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        listener.feed_chunk(48000, silent)
        assert len(listener.audio_buffer) == 3


# ─── TTS (via core.tts) ─────────────────────────────────────────────────────

class TestVPSTTS:
    def test_returns_none_for_empty_text(self):
        result = core.tts.generate_tts("")
        assert result is None

    def test_returns_none_for_error_text(self):
        result = core.tts.generate_tts("❌ OpenClaw não respondeu")
        assert result is None

    def test_truncates_long_text(self):
        long_text = "a" * 2000
        original_engine = core.tts._tts_engine
        core.tts._tts_engine = "edge"

        with patch("core.tts.edge_tts.Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                with open(path, "wb") as f:
                    f.write(b"x" * 200)

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            result = core.tts.generate_tts(long_text)
            if mock_comm.called:
                called_text = mock_comm.call_args[0][0]
                assert len(called_text) <= 1503

        core.tts._tts_engine = original_engine

    def test_cleans_previous_file(self, tmp_path):
        fake_prev = str(tmp_path / "old.mp3")
        with open(fake_prev, "w") as f:
            f.write("old audio")
        core.tts._previous_tts_file = fake_prev

        with patch("core.tts.generate_tts_edge", return_value=None):
            original_engine = core.tts._tts_engine
            core.tts._tts_engine = "edge"
            core.tts.generate_tts("texto")
            core.tts._tts_engine = original_engine

        assert not os.path.exists(fake_prev)


# ─── Toggle Listening (BROWSER mode) ────────────────────────────────────────

class TestToggleListening:
    def test_toggle_on(self):
        mod = _import_app()
        if mod.MODE != "BROWSER":
            pytest.skip("BROWSER mode only")

        listener = mod.continuous_listener
        original_active = listener.active

        result = mod.toggle_listening(False)
        is_on, btn_text, status = result

        assert is_on is True
        assert "Parar" in btn_text
        assert "LIGADA" in status
        assert listener.active is True

        listener.active = original_active

    def test_toggle_off(self):
        mod = _import_app()
        if mod.MODE != "BROWSER":
            pytest.skip("BROWSER mode only")

        listener = mod.continuous_listener
        listener.active = True

        result = mod.toggle_listening(True)
        is_on, btn_text, status = result

        assert is_on is False
        assert "Ativar" in btn_text
        assert "manual" in status.lower() or "DESLIGADA" in status
        assert listener.active is False


# ─── Handle Stream Chunk (BROWSER mode) ──────────────────────────────────────

class TestHandleStreamChunk:
    def test_none_audio_returns_unchanged(self):
        mod = _import_app()
        if not hasattr(mod, "handle_stream_chunk"):
            pytest.skip("handle_stream_chunk not defined (LOCAL mode)")

        history = [{"role": "user", "content": "hello"}]
        result_history, result_audio = mod.handle_stream_chunk(None, history)
        assert result_history == history
        assert result_audio is None

    def test_manual_mode_accumulates_buffer(self):
        mod = _import_app()
        if not hasattr(mod, "handle_stream_chunk"):
            pytest.skip("handle_stream_chunk not defined (LOCAL mode)")

        listener = mod.continuous_listener
        listener.active = False
        listener.audio_buffer = []

        sr = 48000
        data = np.ones(1000, dtype=np.int16)
        mod.handle_stream_chunk((sr, data), [])

        assert len(listener.audio_buffer) == 1
        assert listener.sample_rate == sr

        listener.audio_buffer = []
        listener.sample_rate = None

    def test_continuous_mode_feeds_to_vad(self):
        mod = _import_app()
        if not hasattr(mod, "handle_stream_chunk"):
            pytest.skip("handle_stream_chunk not defined (LOCAL mode)")

        listener = mod.continuous_listener
        listener.active = True
        listener.reset()

        sr = 48000
        loud = (np.ones(1000, dtype=np.float32) * 0.5).astype(np.float32)
        loud_chunk = (sr, loud)

        result_history, result_audio = mod.handle_stream_chunk(loud_chunk, [])
        assert result_audio is None

        listener.active = False
        listener.reset()
