"""Tests for logic shared across all 3 scripts.

Tests the web version's implementations since it has the most complete codebase,
but validates patterns common to all scripts.
"""
import os
import sys
import json
import tempfile
import numpy as np
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── SSE Streaming Parser ────────────────────────────────────────────────────

class TestSSEStreaming:
    """Tests ask_openclaw_stream — the SSE parser used by web and vps versions."""

    def _import_module(self):
        """Import vps module with mocks to avoid startup side effects."""
        with patch("voice_assistant_vps.load_token", return_value="test"):
            import voice_assistant_vps as mod
            return mod

    def test_accumulates_delta_content(self, mock_openai_stream_lines):
        mod = self._import_module()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(mock_openai_stream_lines)

        with patch.object(mod.requests, "post", return_value=mock_resp):
            results = list(mod.ask_openclaw_stream("test", []))

        # Should accumulate: "Olá", "Olá Dayner", "Olá Dayner.", etc.
        assert len(results) == 5
        assert results[0] == "Olá"
        assert results[1] == "Olá Dayner"
        assert results[-1] == "Olá Dayner. Tudo bem?"

    def test_ignores_empty_lines(self):
        mod = self._import_module()
        lines = [
            "",
            "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}",
            "",
            "data: [DONE]",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(mod.requests, "post", return_value=mock_resp):
            results = list(mod.ask_openclaw_stream("test", []))
        assert results == ["ok"]

    def test_ignores_non_data_lines(self):
        mod = self._import_module()
        lines = [
            "event: message",
            "data: {\"choices\":[{\"delta\":{\"content\":\"sim\"}}]}",
            ": comment",
            "data: [DONE]",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(mod.requests, "post", return_value=mock_resp):
            results = list(mod.ask_openclaw_stream("test", []))
        assert results == ["sim"]

    def test_handles_empty_delta(self):
        mod = self._import_module()
        lines = [
            'data: {"choices":[{"delta":{}}]}',
            'data: {"choices":[{"delta":{"content":"fim"}}]}',
            "data: [DONE]",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(mod.requests, "post", return_value=mock_resp):
            results = list(mod.ask_openclaw_stream("test", []))
        assert results == ["fim"]

    def test_sends_stream_true_in_body(self):
        mod = self._import_module()
        lines = ["data: [DONE]"]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(mod.requests, "post", return_value=mock_resp) as mock_post:
            list(mod.ask_openclaw_stream("test", []))
            body = mock_post.call_args[1]["json"]
            assert body["stream"] is True


# ─── Sentence End Detection ──────────────────────────────────────────────────

class TestFindSentenceEnd:
    def _get_fn(self):
        with patch("voice_assistant_vps.load_token", return_value="test"):
            import voice_assistant_vps as mod
            return mod._find_sentence_end

    def test_period_followed_by_space(self):
        fn = self._get_fn()
        assert fn("Olá mundo. Tudo bem?") > 0
        # Returns position AFTER the space
        text = "Olá mundo. Tudo bem?"
        pos = fn(text)
        assert text[:pos].strip().endswith(".")

    def test_exclamation(self):
        fn = self._get_fn()
        assert fn("Incrível! Vamos lá") > 0

    def test_question_mark(self):
        fn = self._get_fn()
        assert fn("Tudo bem? Sim") > 0

    def test_ellipsis(self):
        fn = self._get_fn()
        assert fn("Então… vamos ver") > 0

    def test_no_sentence_end_returns_zero(self):
        fn = self._get_fn()
        assert fn("palavra sem ponto") == 0

    def test_period_at_end_without_space_returns_zero(self):
        """Period at very end (no trailing space) returns 0."""
        fn = self._get_fn()
        assert fn("fim.") == 0

    def test_period_in_number_does_not_match(self):
        """3.14 shouldn't count as sentence end (no space after .)."""
        fn = self._get_fn()
        assert fn("valor é 3.14") == 0


# ─── Chat History Builder ────────────────────────────────────────────────────

class TestBuildApiHistory:
    def _get_fn(self):
        with patch("voice_assistant_vps.load_token", return_value="test"):
            import voice_assistant_vps as mod
            return mod.build_api_history

    def test_filters_voice_prefix(self):
        fn = self._get_fn()
        history = [
            {"role": "user", "content": "[🎤 Voz]: olá"},
            {"role": "assistant", "content": "oi"},
        ]
        result = fn(history)
        # Voice messages are EXCLUDED from API history
        assert len(result) == 1
        assert result[0]["role"] == "assistant"

    def test_keeps_normal_messages(self):
        fn = self._get_fn()
        history = [
            {"role": "user", "content": "pergunta normal"},
            {"role": "assistant", "content": "resposta"},
        ]
        result = fn(history)
        assert len(result) == 2

    def test_truncates_to_max_history(self):
        fn = self._get_fn()
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"msg {i}"})
            history.append({"role": "assistant", "content": f"resp {i}"})
        result = fn(history)
        assert len(result) == 20  # MAX_HISTORY * 2

    def test_ignores_non_user_assistant_roles(self):
        fn = self._get_fn()
        history = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "olá"},
        ]
        result = fn(history)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_empty_content_excluded(self):
        fn = self._get_fn()
        history = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "resposta"},
        ]
        result = fn(history)
        assert len(result) == 1


# ─── Audio Transcription (Gradio input) ──────────────────────────────────────

class TestTranscribeAudio:
    def _get_fn(self):
        with patch("voice_assistant_vps.load_token", return_value="test"):
            import voice_assistant_vps as mod
            return mod

    def test_none_input_returns_empty(self):
        mod = self._get_fn()
        assert mod.transcribe_audio(None) == ""

    def test_converts_stereo_to_mono(self, gradio_audio_stereo):
        mod = self._get_fn()
        sr, stereo_data = gradio_audio_stereo
        assert len(stereo_data.shape) == 2  # confirm it's stereo

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            mod.transcribe_audio(gradio_audio_stereo)
            # Should have been called (converted to mono internally)
            mock_model.transcribe.assert_called_once()

    def test_converts_float_to_int16(self, gradio_audio_float32):
        mod = self._get_fn()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            mod.transcribe_audio(gradio_audio_float32)
            mock_model.transcribe.assert_called_once()

    def test_returns_error_string_on_exception(self, gradio_audio_int16):
        mod = self._get_fn()
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("whisper crash")

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            result = mod.transcribe_audio(gradio_audio_int16)
            assert "[Erro na transcrição:" in result

    def test_cleans_up_temp_file(self, gradio_audio_int16):
        mod = self._get_fn()
        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "teste"
        mock_model.transcribe.return_value = ([seg], None)

        created_files = []
        original_write = __import__("scipy").io.wavfile.write

        def track_write(path, *args, **kwargs):
            created_files.append(path)
            return original_write(path, *args, **kwargs)

        with patch.object(mod, "_get_whisper", return_value=mock_model):
            with patch("voice_assistant_vps.wavfile.write", side_effect=track_write):
                mod.transcribe_audio(gradio_audio_int16)

        # Temp file should be cleaned up
        for f in created_files:
            assert not os.path.exists(f)
