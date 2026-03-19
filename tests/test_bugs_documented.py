"""Tests for bugs that were fixed in Fase 2.

These tests verify the CORRECT behavior after fixes.
Previously they documented buggy behavior — now they confirm the fixes work.
"""
import os
import sys
import json
import ast
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import core.config
import core.llm
import core.history
import core.tts


def _import_app():
    """Import voice_assistant_app with mocked startup side effects."""
    with patch("core.config.load_token", return_value="test-token"):
        with patch("core.tts.init_tts"):
            import voice_assistant_app as mod
            return mod


# ─── FIX 1: Voice messages INCLUDED in LLM context ────────────────────────

class TestFixVoiceMessagesIncluded:
    """build_api_history now strips the '[🎤 Voz]: ' prefix but keeps the content."""

    def test_voice_user_message_included_in_api_context(self):
        history = [
            {"role": "user", "content": "[🎤 Voz]: qual é a previsão do tempo?"},
            {"role": "assistant", "content": "Está ensolarado hoje."},
        ]
        api_messages = core.history.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "qual é a previsão do tempo?"

    def test_mixed_voice_and_text_both_sent(self):
        history = [
            {"role": "user", "content": "[🎤 Voz]: olá"},
            {"role": "assistant", "content": "oi!"},
            {"role": "user", "content": "como vai?"},
            {"role": "assistant", "content": "bem!"},
            {"role": "user", "content": "[🎤 Voz]: tchau"},
            {"role": "assistant", "content": "até mais!"},
        ]
        api_messages = core.history.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 3
        assert user_msgs[0]["content"] == "olá"
        assert user_msgs[1]["content"] == "como vai?"
        assert user_msgs[2]["content"] == "tchau"

    def test_all_voice_conversation_sends_all_user_context(self):
        history = [
            {"role": "user", "content": "[🎤 Voz]: primeira pergunta"},
            {"role": "assistant", "content": "primeira resposta"},
            {"role": "user", "content": "[🎤 Voz]: segunda pergunta"},
            {"role": "assistant", "content": "segunda resposta"},
        ]
        api_messages = core.history.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 2
        assert user_msgs[0]["content"] == "primeira pergunta"
        assert user_msgs[1]["content"] == "segunda pergunta"

    def test_voice_prefix_without_colon_kept_as_is(self):
        """Messages starting with [🎤 but without ']: ' are kept intact."""
        history = [
            {"role": "user", "content": "[🎤 algo estranho"},
        ]
        api_messages = core.history.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "[🎤 algo estranho"


# ─── FIX 2: MIN_SPEECH_CHUNKS counts only speech chunks ─────────────────────

class TestFixMinSpeechChunksCountsSpeech:
    """BrowserContinuousListener.speech_chunk_count counts only loud chunks."""

    def test_one_speech_plus_silence_does_not_pass_min_check(self):
        mod = _import_app()
        listener = mod.BrowserContinuousListener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.speech_detected is True
        assert listener.speech_chunk_count == 1

        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        listener.feed_chunk(48000, silent)

        # Only 1 speech chunk, MIN_SPEECH_CHUNKS is 3 — not enough
        assert listener.speech_chunk_count == 1
        assert listener.speech_chunk_count < listener.MIN_SPEECH_CHUNKS

    def test_pure_silence_does_not_trigger(self):
        mod = _import_app()
        listener = mod.BrowserContinuousListener()
        listener.active = True

        silent = np.zeros(1000, dtype=np.float32)
        for _ in range(20):
            result = listener.feed_chunk(48000, silent)
            assert result is None

        assert not listener.speech_detected
        assert listener.speech_chunk_count == 0
        assert len(listener.audio_buffer) == 0

    def test_enough_speech_chunks_allows_transcription(self):
        mod = _import_app()
        listener = mod.BrowserContinuousListener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        for _ in range(3):
            listener.feed_chunk(48000, loud)

        assert listener.speech_chunk_count == 3
        assert listener.speech_chunk_count >= listener.MIN_SPEECH_CHUNKS


# ─── MAX_HISTORY — unified in core.history ───────────────────────────────

class TestMaxHistoryUnified:
    """After unification, MAX_HISTORY is defined once in core.history."""

    def test_core_max_history_is_10(self):
        assert core.history.MAX_HISTORY == 10

    def test_effective_messages_is_20(self):
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"msg {i}"})
            history.append({"role": "assistant", "content": f"resp {i}"})
        result = core.history.build_api_history(history)
        assert len(result) == 20

    def test_cli_still_has_local_max_history(self):
        """CLI defines its own MAX_HISTORY=20 inside main() for direct history slicing."""
        source = open(os.path.join(PROJECT_ROOT, "voice_assistant_cli.py"), "r", encoding="utf-8").read()
        assert "MAX_HISTORY = 20" in source


# ─── Token error handling — unified ──────────────────────────────────────

class TestTokenErrorHandlingUnified:
    """After unification, load_token always raises RuntimeError."""

    def test_core_load_token_raises_runtime_error(self, tmp_path):
        with patch("os.path.expanduser", return_value=str(tmp_path)):
            env = os.environ.copy()
            env.pop("OPENCLAW_GATEWAY_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError, match="Token"):
                    core.config.load_token()


# ─── ask_openclaw error handling — unified ────────────────────────────────

class TestAskOpenClawErrorHandlingUnified:
    """After unification, ask_openclaw always returns error strings."""

    def test_connection_error_returns_error_string(self):
        import requests as req
        with patch.object(core.llm.requests, "post", side_effect=req.ConnectionError()):
            result = core.llm.ask_openclaw("test", "tok", [])
            assert isinstance(result, str)
            assert result.startswith("❌")

    def test_timeout_returns_error_string(self):
        import requests as req
        with patch.object(core.llm.requests, "post", side_effect=req.Timeout()):
            result = core.llm.ask_openclaw("test", "tok", [])
            assert isinstance(result, str)
            assert "Timeout" in result


# ─── ask_openclaw_stream doesn't catch HTTP errors before iterating ──────

class TestBugStreamingNoPreIterationErrorHandling:
    def test_http_error_propagates_from_stream(self):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

        with patch.object(core.llm.requests, "post", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                list(core.llm.ask_openclaw_stream("test", "tok", []))

    def test_connection_error_propagates_from_stream(self):
        import requests as req
        with patch.object(core.llm.requests, "post", side_effect=req.ConnectionError()):
            with pytest.raises(req.ConnectionError):
                list(core.llm.ask_openclaw_stream("test", "tok", []))


# ─── FIX 4: _find_sentence_end detects punctuation at end of string ──────

class TestFixSentenceEndDetection:
    def test_period_at_end_detected(self):
        assert core.llm._find_sentence_end("Frase completa.") > 0

    def test_exclamation_at_end_detected(self):
        assert core.llm._find_sentence_end("Incrível!") > 0

    def test_question_at_end_detected(self):
        assert core.llm._find_sentence_end("Tudo bem?") > 0

    def test_still_detected_with_trailing_text(self):
        assert core.llm._find_sentence_end("Frase. Mais texto") > 0

    def test_no_punctuation_returns_zero(self):
        assert core.llm._find_sentence_end("Sem pontuação") == 0


# ─── QUIRK (kept): generate_tts skips error messages only at start ───────

class TestQuirkTTSSkipsErrors:
    def test_error_at_start_skipped(self):
        result = core.tts.generate_tts("❌ Erro grave")
        assert result is None

    def test_error_in_middle_not_skipped(self):
        """Intentional: only filters ❌ at start. In practice errors always start with ❌."""
        with patch("core.tts.generate_tts_edge") as mock_edge:
            mock_edge.return_value = "/tmp/audio.mp3"
            original = core.tts._tts_engine
            core.tts._tts_engine = "edge"
            result = core.tts.generate_tts("Texto com ❌ no meio")
            core.tts._tts_engine = original
            assert result is not None or mock_edge.called


# ─── Signatures unified ─────────────────────────────────────────────────

class TestSignaturesUnified:
    """After unification, ask_openclaw has one signature: (text, token, history_messages)."""

    def test_core_ask_openclaw_signature(self):
        source = open(os.path.join(PROJECT_ROOT, "core", "llm.py"), "r", encoding="utf-8").read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ask_openclaw":
                arg_names = [a.arg for a in node.args.args]
                assert "text" in arg_names
                assert "token" in arg_names
                assert "history_messages" in arg_names
                break
