"""Tests that explicitly document known bugs and behavioral quirks.

These tests PASS with the current buggy behavior. They exist so that
if someone fixes a bug, these tests will FAIL — signaling a deliberate
behavioral change that needs review.

After unification, bugs are in core/ and voice_assistant_app.py.
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
        with patch("core.tts.init_piper"):
            import voice_assistant_app as mod
            return mod


# ─── BUG 1: Voice messages excluded from LLM context ────────────────────────

class TestBugVoiceMessagesExcluded:
    """build_api_history filters out messages starting with '[🎤'.
    This means ALL voice-transcribed user messages are excluded from the
    API context sent to the LLM.
    """

    def test_voice_user_message_excluded_from_api_context(self):
        history = [
            {"role": "user", "content": "[🎤 Voz]: qual é a previsão do tempo?"},
            {"role": "assistant", "content": "Está ensolarado hoje."},
        ]
        api_messages = core.history.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 0

    def test_mixed_voice_and_text_only_text_sent(self):
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
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "como vai?"

    def test_all_voice_conversation_sends_no_user_context(self):
        history = [
            {"role": "user", "content": "[🎤 Voz]: primeira pergunta"},
            {"role": "assistant", "content": "primeira resposta"},
            {"role": "user", "content": "[🎤 Voz]: segunda pergunta"},
            {"role": "assistant", "content": "segunda resposta"},
        ]
        api_messages = core.history.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 0


# ─── BUG 2: MIN_SPEECH_CHUNKS counts silence chunks ─────────────────────────

class TestBugMinSpeechChunksCountsSilence:
    """BrowserContinuousListener.MIN_SPEECH_CHUNKS checks len(audio_buffer)
    which includes silence chunks too."""

    def test_one_speech_plus_silence_passes_min_check(self):
        mod = _import_app()
        listener = mod.BrowserContinuousListener()
        listener.active = True

        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.speech_detected is True

        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        listener.feed_chunk(48000, silent)

        assert len(listener.audio_buffer) >= listener.MIN_SPEECH_CHUNKS

    def test_pure_silence_does_not_trigger(self):
        mod = _import_app()
        listener = mod.BrowserContinuousListener()
        listener.active = True

        silent = np.zeros(1000, dtype=np.float32)
        for _ in range(20):
            result = listener.feed_chunk(48000, silent)
            assert result is None

        assert not listener.speech_detected
        assert len(listener.audio_buffer) == 0


# ─── BUG 3: MAX_HISTORY — now unified in core.history ───────────────────────

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


# ─── BUG 4: load_token now consistently raises RuntimeError ──────────────────

class TestTokenErrorHandlingUnified:
    """After unification, load_token always raises RuntimeError."""

    def test_core_load_token_raises_runtime_error(self, tmp_path):
        with patch("os.path.expanduser", return_value=str(tmp_path)):
            env = os.environ.copy()
            env.pop("OPENCLAW_GATEWAY_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError, match="Token"):
                    core.config.load_token()


# ─── BUG 5: ask_openclaw error handling — now unified ────────────────────────

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


# ─── BUG 6: ask_openclaw_stream doesn't catch HTTP errors before iterating ──

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


# ─── QUIRK: _find_sentence_end doesn't match period at end of string ────────

class TestQuirkSentenceEndDetection:
    def test_period_at_end_not_detected(self):
        assert core.llm._find_sentence_end("Frase completa.") == 0

    def test_exclamation_at_end_not_detected(self):
        assert core.llm._find_sentence_end("Incrível!") == 0

    def test_question_at_end_not_detected(self):
        assert core.llm._find_sentence_end("Tudo bem?") == 0

    def test_only_detected_with_trailing_text(self):
        assert core.llm._find_sentence_end("Frase. Mais texto") > 0


# ─── QUIRK: generate_tts skips error messages ───────────────────────────────

class TestQuirkTTSSkipsErrors:
    def test_error_at_start_skipped(self):
        result = core.tts.generate_tts("❌ Erro grave")
        assert result is None

    def test_error_in_middle_not_skipped(self):
        with patch("core.tts.generate_tts_edge") as mock_edge:
            mock_edge.return_value = "/tmp/audio.mp3"
            # Force edge engine
            original = core.tts._tts_engine
            core.tts._tts_engine = "edge"
            result = core.tts.generate_tts("Texto com ❌ no meio")
            core.tts._tts_engine = original
            assert result is not None or mock_edge.called


# ─── QUIRK: ask_openclaw signatures now unified ─────────────────────────────

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
