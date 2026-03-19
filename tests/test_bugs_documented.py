"""Tests that explicitly document known bugs and behavioral quirks.

These tests PASS with the current buggy behavior. They exist so that
if someone fixes a bug, these tests will FAIL — signaling a deliberate
behavioral change that needs review.

Does NOT fix bugs. Does NOT suggest improvements.
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


def _import_vps():
    with patch("voice_assistant_vps.load_token", return_value="test"):
        import voice_assistant_vps as mod
        return mod


def _import_web():
    with patch("voice_assistant_web.load_token", return_value="test"):
        with patch("voice_assistant_web.find_mic_pyaudio", return_value=(0, "Mock")):
            import voice_assistant_web as mod
            return mod


# ─── BUG 1: Voice messages excluded from LLM context ────────────────────────

class TestBugVoiceMessagesExcluded:
    """build_api_history filters out messages starting with '[🎤'.
    This means ALL voice-transcribed user messages are excluded from the
    API context sent to the LLM. The LLM never sees what the user said by voice.
    """

    def test_voice_user_message_excluded_from_api_context(self):
        """Voice transcription is shown in chat UI but NOT sent to LLM."""
        mod = _import_vps()
        history = [
            {"role": "user", "content": "[🎤 Voz]: qual é a previsão do tempo?"},
            {"role": "assistant", "content": "Está ensolarado hoje."},
        ]
        api_messages = mod.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        # BUG: user voice message is completely absent
        assert len(user_msgs) == 0

    def test_mixed_voice_and_text_only_text_sent(self):
        """In a mixed conversation, only typed messages reach the LLM."""
        mod = _import_vps()
        history = [
            {"role": "user", "content": "[🎤 Voz]: olá"},          # voice — excluded
            {"role": "assistant", "content": "oi!"},
            {"role": "user", "content": "como vai?"},               # typed — included
            {"role": "assistant", "content": "bem!"},
            {"role": "user", "content": "[🎤 Voz]: tchau"},         # voice — excluded
            {"role": "assistant", "content": "até mais!"},
        ]
        api_messages = mod.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "como vai?"

    def test_all_voice_conversation_sends_no_user_context(self):
        """A fully voice-based conversation sends ZERO user messages to LLM."""
        mod = _import_vps()
        history = [
            {"role": "user", "content": "[🎤 Voz]: primeira pergunta"},
            {"role": "assistant", "content": "primeira resposta"},
            {"role": "user", "content": "[🎤 Voz]: segunda pergunta"},
            {"role": "assistant", "content": "segunda resposta"},
        ]
        api_messages = mod.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        # BUG: LLM only sees its own responses, not what the user asked
        assert len(user_msgs) == 0

    def test_web_version_same_bug(self):
        """Web version has the exact same bug."""
        mod = _import_web()
        history = [
            {"role": "user", "content": "[🎤 Voz]: olá"},
            {"role": "assistant", "content": "oi"},
        ]
        api_messages = mod.build_api_history(history)
        user_msgs = [m for m in api_messages if m["role"] == "user"]
        assert len(user_msgs) == 0


# ─── BUG 2: MIN_SPEECH_CHUNKS counts silence chunks ─────────────────────────

class TestBugMinSpeechChunksCountsSilence:
    """BrowserContinuousListener.MIN_SPEECH_CHUNKS is meant to ensure
    enough speech was captured, but it checks len(audio_buffer) which
    includes silence chunks too. So 1 speech + 2 silence = 3 = passes.
    """

    def test_one_speech_plus_silence_passes_min_check(self):
        """1 speech chunk + enough silence chunks passes MIN_SPEECH_CHUNKS."""
        mod = _import_vps()
        listener = mod.BrowserContinuousListener()
        listener.active = True

        # 1 speech chunk
        loud = np.ones(1000, dtype=np.float32) * 0.5
        listener.feed_chunk(48000, loud)
        assert listener.speech_detected is True

        # 2 silence chunks → buffer has 3 items total
        silent = np.zeros(1000, dtype=np.float32)
        listener.feed_chunk(48000, silent)
        listener.feed_chunk(48000, silent)

        # BUG: buffer length (3) >= MIN_SPEECH_CHUNKS (3)
        # even though only 1 of those 3 is actual speech
        assert len(listener.audio_buffer) >= listener.MIN_SPEECH_CHUNKS

    def test_pure_silence_does_not_trigger(self):
        """Pure silence (no speech_detected) never triggers transcription."""
        mod = _import_vps()
        listener = mod.BrowserContinuousListener()
        listener.active = True

        silent = np.zeros(1000, dtype=np.float32)
        for _ in range(20):
            result = listener.feed_chunk(48000, silent)
            assert result is None

        assert not listener.speech_detected
        assert len(listener.audio_buffer) == 0


# ─── BUG 3: MAX_HISTORY inconsistency ───────────────────────────────────────

class TestBugMaxHistoryInconsistency:
    """CLI defines MAX_HISTORY=20 (local var in main()).
    Web and VPS define MAX_HISTORY=10 (module constant).
    Web/VPS then use MAX_HISTORY*2=20 messages.
    CLI uses MAX_HISTORY=20 messages directly.
    Net effect: all keep 20 messages, but via different logic.
    """

    def test_cli_max_history_is_20(self):
        source = open(os.path.join(PROJECT_ROOT, "voice_assistant.py"), "r", encoding="utf-8").read()
        assert "MAX_HISTORY = 20" in source

    def test_web_max_history_is_10(self):
        mod = _import_web()
        assert mod.MAX_HISTORY == 10

    def test_vps_max_history_is_10(self):
        mod = _import_vps()
        assert mod.MAX_HISTORY == 10

    def test_web_effective_messages_is_20(self):
        """Web uses MAX_HISTORY * 2 = 20 messages."""
        mod = _import_web()
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"msg {i}"})
            history.append({"role": "assistant", "content": f"resp {i}"})
        result = mod.build_api_history(history)
        assert len(result) == 20  # MAX_HISTORY * 2

    def test_cli_max_history_is_local_variable(self):
        """MAX_HISTORY in CLI is defined inside main(), not at module level."""
        import voice_assistant as cli
        # Module-level attribute should NOT exist
        assert not hasattr(cli, "MAX_HISTORY")

    def test_web_max_history_is_module_level(self):
        mod = _import_web()
        assert hasattr(mod, "MAX_HISTORY")

    def test_vps_max_history_is_module_level(self):
        mod = _import_vps()
        assert hasattr(mod, "MAX_HISTORY")


# ─── BUG 4: CLI load_token sys.exit vs Web/VPS RuntimeError ─────────────────

class TestBugTokenErrorHandlingDiffers:
    """CLI calls sys.exit(1) when token is missing.
    Web and VPS raise RuntimeError.
    Different error handling for the same condition.
    """

    def test_cli_exits_on_missing_token(self, tmp_path):
        import voice_assistant as cli
        with patch("os.path.expanduser", return_value=str(tmp_path)):
            env = os.environ.copy()
            env.pop("OPENCLAW_GATEWAY_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(SystemExit):
                    cli.load_token()

    def test_web_raises_runtime_error(self, tmp_path):
        mod = _import_web()
        with patch("os.path.expanduser", return_value=str(tmp_path)):
            env = os.environ.copy()
            env.pop("OPENCLAW_GATEWAY_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError):
                    mod.load_token()

    def test_vps_raises_runtime_error(self, tmp_path):
        mod = _import_vps()
        with patch("os.path.expanduser", return_value=str(tmp_path)):
            env = os.environ.copy()
            env.pop("OPENCLAW_GATEWAY_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError):
                    mod.load_token()


# ─── BUG 5: CLI ask_openclaw returns None, Web/VPS return error string ──────

class TestBugAskOpenClawErrorHandlingDiffers:
    """CLI ask_openclaw returns None on error.
    Web/VPS ask_openclaw returns an error string starting with '❌'.
    Callers must handle both patterns differently.
    """

    def test_cli_connection_error_returns_none(self):
        import voice_assistant as cli
        import requests as req
        with patch("voice_assistant.requests.post", side_effect=req.ConnectionError()):
            result = cli.ask_openclaw("test", "tok", [])
            assert result is None

    def test_vps_connection_error_returns_string(self):
        mod = _import_vps()
        import requests as req
        with patch.object(mod.requests, "post", side_effect=req.ConnectionError()):
            result = mod.ask_openclaw("test", [])
            assert isinstance(result, str)
            assert result.startswith("❌")

    def test_web_connection_error_returns_string(self):
        mod = _import_web()
        import requests as req
        with patch.object(mod.requests, "post", side_effect=req.ConnectionError()):
            result = mod.ask_openclaw("test", [])
            assert isinstance(result, str)
            assert result.startswith("❌")


# ─── BUG 6: ask_openclaw_stream doesn't catch HTTP errors before iterating ──

class TestBugStreamingNoPreIterationErrorHandling:
    """ask_openclaw_stream calls resp.raise_for_status() which raises
    an exception if the HTTP response is 4xx/5xx. This exception is NOT
    caught inside the generator — it propagates to the caller.
    The caller catches it with a bare `except Exception`.
    """

    def test_http_error_propagates_from_stream(self):
        mod = _import_vps()
        import requests as req

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

        with patch.object(mod.requests, "post", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                list(mod.ask_openclaw_stream("test", []))

    def test_connection_error_propagates_from_stream(self):
        """Connection error during POST also propagates."""
        mod = _import_vps()
        import requests as req

        with patch.object(mod.requests, "post", side_effect=req.ConnectionError()):
            with pytest.raises(req.ConnectionError):
                list(mod.ask_openclaw_stream("test", []))


# ─── QUIRK: _find_sentence_end doesn't match period at end of string ────────

class TestQuirkSentenceEndDetection:
    """The regex [.!?…]\\s requires whitespace AFTER punctuation.
    So a sentence ending at the end of the string (no trailing space)
    is never detected. This means TTS for the last sentence only
    happens after streaming is complete, not during.
    """

    def test_period_at_end_not_detected(self):
        mod = _import_vps()
        assert mod._find_sentence_end("Frase completa.") == 0

    def test_exclamation_at_end_not_detected(self):
        mod = _import_vps()
        assert mod._find_sentence_end("Incrível!") == 0

    def test_question_at_end_not_detected(self):
        mod = _import_vps()
        assert mod._find_sentence_end("Tudo bem?") == 0

    def test_only_detected_with_trailing_text(self):
        mod = _import_vps()
        assert mod._find_sentence_end("Frase. Mais texto") > 0


# ─── QUIRK: generate_tts skips error messages ───────────────────────────────

class TestQuirkTTSSkipsErrors:
    """generate_tts checks text.startswith('❌') and returns None.
    This prevents error messages from being spoken aloud.
    But it only checks the first character — an error in the middle
    of a response would still be spoken.
    """

    def test_error_at_start_skipped(self):
        mod = _import_vps()
        result = mod.generate_tts("❌ Erro grave")
        assert result is None

    def test_error_in_middle_not_skipped(self):
        """Error emoji in the middle of text is NOT filtered."""
        mod = _import_vps()
        with patch.object(mod.edge_tts, "Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                with open(path, "wb") as f:
                    f.write(b"x" * 200)

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            result = mod.generate_tts("Texto com ❌ no meio")
            # NOT filtered — proceeds to generate TTS
            assert result is not None or mock_comm.called


# ─── QUIRK: CLI vs Web/VPS different ask_openclaw signatures ────────────────

class TestQuirkDifferentSignatures:
    """CLI ask_openclaw takes (text, token, history).
    Web/VPS ask_openclaw takes (text, history_messages) — token is global.
    Same function name, different signatures across files.
    """

    def test_cli_signature_has_token_param(self):
        source = open(os.path.join(PROJECT_ROOT, "voice_assistant.py"), "r", encoding="utf-8").read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ask_openclaw":
                arg_names = [a.arg for a in node.args.args]
                assert "token" in arg_names
                assert "text" in arg_names
                assert "history" in arg_names
                break

    def test_vps_signature_no_token_param(self):
        source = open(os.path.join(PROJECT_ROOT, "voice_assistant_vps.py"), "r", encoding="utf-8").read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ask_openclaw":
                arg_names = [a.arg for a in node.args.args]
                assert "token" not in arg_names
                assert "text" in arg_names
                assert "history_messages" in arg_names
                break

    def test_web_signature_no_token_param(self):
        source = open(os.path.join(PROJECT_ROOT, "voice_assistant_web.py"), "r", encoding="utf-8").read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ask_openclaw":
                arg_names = [a.arg for a in node.args.args]
                assert "token" not in arg_names
                break
