"""Tests for voice_assistant_vps.py — VPS-specific behavior.

Captures current behavior — does NOT fix bugs.
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


def _import_vps():
    with patch("voice_assistant_vps.load_token", return_value="test-token"):
        import voice_assistant_vps as mod
        return mod


# ─── VPS Configuration ───────────────────────────────────────────────────────

class TestVPSConfig:
    def test_gateway_port_19789(self):
        mod = _import_vps()
        assert "19789" in mod.GATEWAY_URL

    def test_no_piper_in_vps(self):
        """VPS version doesn't use Piper TTS — Edge only."""
        mod = _import_vps()
        # VPS module doesn't import or define PIPER_AVAILABLE
        assert not hasattr(mod, "PIPER_AVAILABLE") or not hasattr(mod, "piper_voice")


# ─── BrowserContinuousListener ───────────────────────────────────────────────

class TestBrowserContinuousListener:
    def _make_listener(self):
        mod = _import_vps()
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
        # Create loud audio (RMS >> 0.01)
        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.speech_detected is True
        assert len(listener.audio_buffer) == 1

    def test_silence_after_speech_increments_counter(self):
        listener = self._make_listener()
        listener.active = True

        # Feed speech first
        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.silence_count == 0

        # Feed silence
        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        assert listener.silence_count == 1
        # Trailing silence is kept in buffer
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

        # Feed MIN_SPEECH_CHUNKS of loud audio
        loud = np.ones(1000, dtype=np.float32) * 0.5
        for _ in range(listener.MIN_SPEECH_CHUNKS):
            result = listener.feed_chunk(48000, loud)
            assert result is None

        # Feed SILENCE_CHUNKS_NEEDED of silence
        silent = np.zeros(1000, dtype=np.float32)

        mod = _import_vps()
        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "transcrição teste"
        mock_model.transcribe.return_value = ([seg], None)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            for i in range(listener.SILENCE_CHUNKS_NEEDED - 1):
                result = listener.feed_chunk(48000, silent)
                assert result is None

            # Last silence chunk should trigger transcription
            result = listener.feed_chunk(48000, silent)
            assert result == "transcrição teste"

    def test_resets_after_transcription(self):
        listener = self._make_listener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        for _ in range(listener.MIN_SPEECH_CHUNKS):
            listener.feed_chunk(48000, loud)

        silent = np.zeros(1000, dtype=np.float32)

        mod = _import_vps()
        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "teste"
        mock_model.transcribe.return_value = ([seg], None)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            for _ in range(listener.SILENCE_CHUNKS_NEEDED):
                listener.feed_chunk(48000, silent)

        # After transcription, state should be reset
        assert listener.audio_buffer == []
        assert listener.speech_detected is False
        assert listener.processing is False

    def test_handles_stereo_input(self):
        listener = self._make_listener()
        listener.active = True

        sr = 48000
        stereo = np.column_stack([
            np.ones(1000, dtype=np.float32) * 0.5,
            np.ones(1000, dtype=np.float32) * 0.3,
        ])
        # Should not crash — converts to mono internally
        listener.feed_chunk(sr, stereo)
        assert listener.speech_detected is True

    def test_handles_int16_input(self):
        listener = self._make_listener()
        listener.active = True

        loud_int16 = (np.ones(1000, dtype=np.float32) * 16000).astype(np.int16)
        listener.feed_chunk(48000, loud_int16)
        assert listener.speech_detected is True

    def test_not_enough_speech_chunks_behavior(self):
        """Document: silence chunks ARE counted in audio_buffer length.
        
        Current code checks `len(self.audio_buffer) >= self.MIN_SPEECH_CHUNKS`.
        Silence chunks after speech are ALSO appended to audio_buffer.
        So 1 speech + 2 silence = 3 chunks = triggers transcription.
        This means MIN_SPEECH_CHUNKS doesn't actually filter by speech-only chunks.
        """
        listener = self._make_listener()
        listener.active = True

        # Only 1 speech chunk
        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.speech_detected is True

        # After 2 silence chunks, buffer has 3 items (1 loud + 2 silent)
        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        listener.feed_chunk(48000, silent)
        assert len(listener.audio_buffer) == 3  # 1 speech + 2 silence = MIN_SPEECH_CHUNKS

        # This means the check `len(audio_buffer) >= MIN_SPEECH_CHUNKS` 
        # passes even with only 1 actual speech chunk


# ─── TTS Generation (VPS — Edge only) ────────────────────────────────────────

class TestVPSTTS:
    def test_returns_none_for_empty_text(self):
        mod = _import_vps()
        result = mod.generate_tts("")
        assert result is None

    def test_returns_none_for_error_text(self):
        mod = _import_vps()
        result = mod.generate_tts("❌ OpenClaw não respondeu")
        assert result is None

    def test_truncates_long_text(self):
        mod = _import_vps()
        long_text = "a" * 2000

        with patch.object(mod.edge_tts, "Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                # Write a valid file to pass size check
                with open(path, "wb") as f:
                    f.write(b"x" * 200)

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            result = mod.generate_tts(long_text)
            if mock_comm.called:
                called_text = mock_comm.call_args[0][0]
                assert len(called_text) <= 1503  # 1500 + "..."

    def test_cleans_previous_file(self, tmp_path):
        mod = _import_vps()
        fake_prev = str(tmp_path / "old.mp3")
        with open(fake_prev, "w") as f:
            f.write("old audio")
        mod._previous_tts_file = fake_prev

        # Generate new (will fail but should still clean old)
        with patch.object(mod.edge_tts, "Communicate", side_effect=Exception("fail")):
            mod.generate_tts("texto")

        assert not os.path.exists(fake_prev)


# ─── Toggle Listening ─────────────────────────────────────────────────────────

class TestToggleListening:
    def test_toggle_on(self):
        mod = _import_vps()
        # is_on=False means we're turning ON
        listener = mod.continuous_listener
        original_active = listener.active

        result = mod.toggle_listening(False)
        is_on, btn_text, status = result

        assert is_on is True
        assert "Parar" in btn_text
        assert "LIGADA" in status
        assert listener.active is True

        # Cleanup
        listener.active = original_active

    def test_toggle_off(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = True

        result = mod.toggle_listening(True)
        is_on, btn_text, status = result

        assert is_on is False
        assert "Ativar" in btn_text
        assert "manual" in status.lower() or "DESLIGADA" in status
        assert listener.active is False


# ─── Handle Stream Chunk ─────────────────────────────────────────────────────

class TestHandleStreamChunk:
    def test_none_audio_returns_unchanged(self):
        mod = _import_vps()
        history = [{"role": "user", "content": "hello"}]
        result_history, result_audio = mod.handle_stream_chunk(None, history)
        assert result_history == history
        assert result_audio is None

    def test_manual_mode_accumulates_buffer(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = False
        listener.audio_buffer = []

        sr = 48000
        data = np.ones(1000, dtype=np.int16)
        mod.handle_stream_chunk((sr, data), [])

        assert len(listener.audio_buffer) == 1
        assert listener.sample_rate == sr

        # Cleanup
        listener.audio_buffer = []
        listener.sample_rate = None

    def test_continuous_mode_feeds_to_vad(self):
        mod = _import_vps()
        listener = mod.continuous_listener
        listener.active = True
        listener.reset()

        sr = 48000
        loud = (np.ones(1000, dtype=np.float32) * 0.5).astype(np.float32)
        # Convert to int16 as Gradio would send
        loud_chunk = (sr, loud)

        result_history, result_audio = mod.handle_stream_chunk(loud_chunk, [])
        # No transcription yet (not enough silence)
        assert result_audio is None

        # Cleanup
        listener.active = False
        listener.reset()
