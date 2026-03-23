"""Tests for shared logic in core/ modules.

Tests the core implementations directly since they're now the single source of truth.
"""
import os
import sys
import json
import tempfile
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.llm
import core.history
import core.stt


# ─── SSE Streaming Parser ────────────────────────────────────────────────────

class TestSSEStreaming:
    """Tests ask_openclaw_stream — the SSE parser in core.llm."""

    def test_accumulates_delta_content(self, mock_openai_stream_lines):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(mock_openai_stream_lines)

        with patch.object(core.llm._session, "post", return_value=mock_resp):
            results = list(core.llm.ask_openclaw_stream("test", "tok", []))

        assert len(results) == 5
        assert results[0] == "Olá"
        assert results[1] == "Olá Dayner"
        assert results[-1] == "Olá Dayner. Tudo bem?"

    def test_ignores_empty_lines(self):
        lines = [
            "",
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "",
            "data: [DONE]",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(core.llm._session, "post", return_value=mock_resp):
            results = list(core.llm.ask_openclaw_stream("test", "tok", []))
        assert results == ["ok"]

    def test_ignores_non_data_lines(self):
        lines = [
            "event: message",
            'data: {"choices":[{"delta":{"content":"sim"}}]}',
            ": comment",
            "data: [DONE]",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(core.llm._session, "post", return_value=mock_resp):
            results = list(core.llm.ask_openclaw_stream("test", "tok", []))
        assert results == ["sim"]

    def test_handles_empty_delta(self):
        lines = [
            'data: {"choices":[{"delta":{}}]}',
            'data: {"choices":[{"delta":{"content":"fim"}}]}',
            "data: [DONE]",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(core.llm._session, "post", return_value=mock_resp):
            results = list(core.llm.ask_openclaw_stream("test", "tok", []))
        assert results == ["fim"]

    def test_sends_stream_true_in_body(self):
        lines = ["data: [DONE]"]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)

        with patch.object(core.llm._session, "post", return_value=mock_resp) as mock_post:
            list(core.llm.ask_openclaw_stream("test", "tok", []))
            body = mock_post.call_args[1]["json"]
            assert body["stream"] is True


# ─── Sentence End Detection ──────────────────────────────────────────────────

class TestFindSentenceEnd:
    def test_period_followed_by_space(self):
        assert core.llm._find_sentence_end("Olá mundo. Tudo bem?") > 0
        text = "Olá mundo. Tudo bem?"
        pos = core.llm._find_sentence_end(text)
        assert text[:pos].strip().endswith(".")

    def test_exclamation(self):
        assert core.llm._find_sentence_end("Incrível! Vamos lá") > 0

    def test_question_mark(self):
        assert core.llm._find_sentence_end("Tudo bem? Sim") > 0

    def test_ellipsis(self):
        assert core.llm._find_sentence_end("Então… vamos ver") > 0

    def test_no_sentence_end_returns_zero(self):
        assert core.llm._find_sentence_end("palavra sem ponto") == 0

    def test_period_at_end_detected(self):
        assert core.llm._find_sentence_end("fim.") > 0

    def test_period_in_number_does_not_match(self):
        assert core.llm._find_sentence_end("valor é 3.14") == 0


# ─── Chat History Builder ────────────────────────────────────────────────────

class TestBuildApiHistory:
    def test_strips_voice_prefix(self):
        history = [
            {"role": "user", "content": "[🎤 Voz]: olá"},
            {"role": "assistant", "content": "oi"},
        ]
        result = core.history.build_api_history(history)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "olá"

    def test_keeps_normal_messages(self):
        history = [
            {"role": "user", "content": "pergunta normal"},
            {"role": "assistant", "content": "resposta"},
        ]
        result = core.history.build_api_history(history)
        assert len(result) == 2

    def test_truncates_to_max_history(self):
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"msg {i}"})
            history.append({"role": "assistant", "content": f"resp {i}"})
        result = core.history.build_api_history(history)
        assert len(result) == 20  # MAX_HISTORY * 2

    def test_ignores_non_user_assistant_roles(self):
        history = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "olá"},
        ]
        result = core.history.build_api_history(history)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_empty_content_excluded(self):
        history = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "resposta"},
        ]
        result = core.history.build_api_history(history)
        assert len(result) == 1


# ─── Audio Transcription (Gradio input) ──────────────────────────────────────

class TestTranscribeAudio:
    def test_none_input_returns_empty(self):
        assert core.stt.transcribe_audio(None) == ""

    def test_converts_stereo_to_mono(self, gradio_audio_stereo):
        sr, stereo_data = gradio_audio_stereo
        assert len(stereo_data.shape) == 2

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)

        with patch.object(core.stt, "_get_whisper", return_value=mock_model):
            core.stt.transcribe_audio(gradio_audio_stereo)
            mock_model.transcribe.assert_called_once()

    def test_converts_float_to_int16(self, gradio_audio_float32):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)

        with patch.object(core.stt, "_get_whisper", return_value=mock_model):
            core.stt.transcribe_audio(gradio_audio_float32)
            mock_model.transcribe.assert_called_once()

    def test_returns_error_string_on_exception(self, gradio_audio_int16):
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("whisper crash")

        with patch.object(core.stt, "_get_whisper", return_value=mock_model):
            result = core.stt.transcribe_audio(gradio_audio_int16)
            assert "[Erro na transcrição:" in result

    def test_cleans_up_temp_file(self, gradio_audio_int16):
        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "teste"
        mock_model.transcribe.return_value = ([seg], None)

        created_files = []
        original_write = __import__("scipy").io.wavfile.write

        def track_write(path, *args, **kwargs):
            created_files.append(path)
            return original_write(path, *args, **kwargs)

        with patch.object(core.stt, "_get_whisper", return_value=mock_model):
            with patch("core.stt.wavfile.write", side_effect=track_write):
                core.stt.transcribe_audio(gradio_audio_int16)

        for f in created_files:
            assert not os.path.exists(f)
