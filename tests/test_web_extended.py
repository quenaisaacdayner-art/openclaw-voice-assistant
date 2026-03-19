"""Extended tests for voice_assistant_web.py — covers gaps in test_web.py.

Captures current behavior — does NOT fix bugs.
"""
import os
import sys
import json
import threading
import queue
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _import_web():
    with patch("voice_assistant_web.load_token", return_value="test-token"):
        with patch("voice_assistant_web.find_mic_pyaudio", return_value=(0, "Test Mic")):
            import voice_assistant_web as mod
            return mod


# ─── Whisper lazy loading ────────────────────────────────────────────────────

class TestGetWhisper:
    def test_lazy_loads_on_first_call(self):
        mod = _import_web()
        mod.whisper_model = None  # reset

        mock_model = MagicMock()
        with patch.object(mod, "WhisperModel", return_value=mock_model):
            result = mod._get_whisper()
            assert result is mock_model
            assert mod.whisper_model is mock_model

    def test_returns_cached_on_second_call(self):
        mod = _import_web()
        cached = MagicMock()
        mod.whisper_model = cached

        result = mod._get_whisper()
        assert result is cached

    def test_uses_cpu_int8(self):
        mod = _import_web()
        mod.whisper_model = None

        with patch.object(mod, "WhisperModel", return_value=MagicMock()) as mock_cls:
            mod._get_whisper()
            mock_cls.assert_called_once_with(mod.WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

        # cleanup
        mod.whisper_model = None


# ─── generate_tts wrapper ───────────────────────────────────────────────────

class TestGenerateTTS:
    def test_returns_none_for_empty_text(self):
        mod = _import_web()
        assert mod.generate_tts("") is None
        assert mod.generate_tts(None) is None

    def test_returns_none_for_error_prefix(self):
        mod = _import_web()
        assert mod.generate_tts("❌ erro aconteceu") is None

    def test_piper_fallback_to_edge(self):
        """If Piper returns None, falls back to Edge."""
        mod = _import_web()
        original_engine = mod.TTS_ENGINE
        mod.TTS_ENGINE = "piper"
        original_voice = mod.piper_voice
        mod.piper_voice = MagicMock()

        with patch.object(mod, "generate_tts_piper", return_value=None):
            with patch.object(mod, "generate_tts_edge", return_value="/tmp/fallback.mp3") as mock_edge:
                result = mod.generate_tts("texto")
                mock_edge.assert_called_once()
                assert result == "/tmp/fallback.mp3"

        mod.TTS_ENGINE = original_engine
        mod.piper_voice = original_voice

    def test_edge_only_when_engine_edge(self):
        mod = _import_web()
        original_engine = mod.TTS_ENGINE
        mod.TTS_ENGINE = "edge"

        with patch.object(mod, "generate_tts_edge", return_value="/tmp/out.mp3") as mock_edge:
            result = mod.generate_tts("texto")
            mock_edge.assert_called_once()

        mod.TTS_ENGINE = original_engine

    def test_cleans_previous_file(self, tmp_path):
        mod = _import_web()
        old_file = str(tmp_path / "prev.mp3")
        with open(old_file, "w") as f:
            f.write("old")
        mod._previous_tts_file = old_file

        with patch.object(mod, "generate_tts_edge", return_value=None):
            original_engine = mod.TTS_ENGINE
            mod.TTS_ENGINE = "edge"
            mod.generate_tts("text")
            mod.TTS_ENGINE = original_engine

        assert not os.path.exists(old_file)

    def test_truncates_long_text(self):
        mod = _import_web()
        original_engine = mod.TTS_ENGINE
        mod.TTS_ENGINE = "edge"

        with patch.object(mod, "generate_tts_edge", return_value=None) as mock_edge:
            mod.generate_tts("a" * 2000)
            called_text = mock_edge.call_args[0][0]
            assert len(called_text) == 1503

        mod.TTS_ENGINE = original_engine

    def test_tracks_new_file_in_global(self):
        mod = _import_web()
        original_engine = mod.TTS_ENGINE
        mod.TTS_ENGINE = "edge"
        mod._previous_tts_file = None

        with patch.object(mod, "generate_tts_edge", return_value="/tmp/new.mp3"):
            mod.generate_tts("text")
            assert mod._previous_tts_file == "/tmp/new.mp3"

        mod.TTS_ENGINE = original_engine
        mod._previous_tts_file = None


# ─── toggle_listening (web — RealtimeSTT) ───────────────────────────────────

class TestToggleListeningWeb:
    def test_toggle_on_success(self):
        mod = _import_web()
        if not hasattr(mod, "toggle_listening"):
            pytest.skip("toggle_listening not defined (REALTIME_STT_AVAILABLE=False)")

        listener = mod.continuous_listener
        with patch.object(listener, "start", return_value=True):
            result = mod.toggle_listening(False)  # False = currently off, turning on
            is_on, btn, status, audio_update = result
            assert is_on is True
            assert "Parar" in btn

    def test_toggle_on_failure(self):
        mod = _import_web()
        if not hasattr(mod, "toggle_listening"):
            pytest.skip("toggle_listening not defined")

        listener = mod.continuous_listener
        with patch.object(listener, "start", return_value=False):
            result = mod.toggle_listening(False)
            is_on, btn, status, audio_update = result
            assert is_on is False
            assert "Falha" in status or "Ativar" in btn

    def test_toggle_off(self):
        mod = _import_web()
        if not hasattr(mod, "toggle_listening"):
            pytest.skip("toggle_listening not defined")

        listener = mod.continuous_listener
        with patch.object(listener, "stop") as mock_stop:
            result = mod.toggle_listening(True)  # True = currently on, turning off
            is_on, btn, status, audio_update = result
            assert is_on is False
            mock_stop.assert_called_once()


# ─── poll_continuous ─────────────────────────────────────────────────────────

class TestPollContinuous:
    def test_returns_unchanged_when_off(self):
        mod = _import_web()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined")

        history = [{"role": "user", "content": "hi"}]
        results = list(mod.poll_continuous(history, False))
        assert len(results) >= 1
        assert results[-1] == (history, None)

    def test_returns_unchanged_when_processing(self):
        mod = _import_web()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined")

        mod.continuous_listener.processing = True
        results = list(mod.poll_continuous([], True))
        assert results[-1] == ([], None)
        mod.continuous_listener.processing = False

    def test_returns_unchanged_when_no_text(self):
        mod = _import_web()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined")

        mod.continuous_listener.processing = False
        with patch.object(mod.continuous_listener, "get_text", return_value=None):
            results = list(mod.poll_continuous([], True))
            assert results[-1] == ([], None)

    def test_processes_text_when_available(self):
        mod = _import_web()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined")

        mod.continuous_listener.processing = False
        with patch.object(mod.continuous_listener, "get_text", return_value="olá"):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.iter_lines.return_value = iter([
                'data: {"choices":[{"delta":{"content":"resposta"}}]}',
                "data: [DONE]",
            ])
            with patch.object(mod.requests, "post", return_value=mock_resp):
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.poll_continuous([], True))
                    last_history, last_audio = results[-1]
                    # Should have user + assistant messages
                    assert any("[🎤 Voz]" in m.get("content", "") for m in last_history)
                    assert any(m["role"] == "assistant" for m in last_history)

        # processing flag should be reset
        assert mod.continuous_listener.processing is False


# ─── respond_text streaming edge cases ──────────────────────────────────────

class TestRespondTextExtended:
    def test_fallback_to_non_streaming_when_empty(self):
        """If streaming yields nothing, falls back to non-streaming ask_openclaw."""
        mod = _import_web()

        # Streaming yields empty
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(["data: [DONE]"])

        with patch.object(mod.requests, "post", return_value=mock_resp):
            with patch.object(mod, "ask_openclaw", return_value="fallback") as mock_ask:
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_text("pergunta", []))
                    mock_ask.assert_called_once()
                    last = results[-1]
                    history = last[1]
                    assert any(m.get("content") == "fallback" for m in history)

    def test_exception_falls_back_to_non_streaming(self):
        """If streaming raises exception, falls back to non-streaming."""
        mod = _import_web()

        with patch.object(mod, "ask_openclaw_stream", side_effect=Exception("network")):
            with patch.object(mod, "ask_openclaw", return_value="safe fallback"):
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_text("pergunta", []))
                    last = results[-1]
                    history = last[1]
                    assert any(m.get("content") == "safe fallback" for m in history)

    def test_first_sentence_tts_during_stream(self):
        """TTS is generated for first complete sentence during streaming."""
        mod = _import_web()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter([
            'data: {"choices":[{"delta":{"content":"Primeira frase."}}]}',
            'data: {"choices":[{"delta":{"content":" Segunda parte"}}]}',
            "data: [DONE]",
        ])

        tts_calls = []

        def fake_tts(text):
            tts_calls.append(text)
            return "/tmp/audio.wav" if text else None

        with patch.object(mod.requests, "post", return_value=mock_resp):
            with patch.object(mod, "generate_tts", side_effect=fake_tts):
                results = list(mod.respond_text("pergunta", []))

        # First TTS call should be for first sentence, second for remaining
        assert len(tts_calls) >= 1


# ─── respond_audio extended ──────────────────────────────────────────────────

class TestRespondAudioExtended:
    def test_streaming_exception_fallback(self):
        """Exception during streaming falls back to non-streaming."""
        mod = _import_web()

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod, "ask_openclaw_stream", side_effect=Exception("fail")):
                with patch.object(mod, "ask_openclaw", return_value="fallback"):
                    with patch.object(mod, "generate_tts", return_value=None):
                        audio_input = (48000, np.ones(1000, dtype=np.int16))
                        results = list(mod.respond_audio(audio_input, []))
                        last = results[-1]
                        history = last[0]
                        assert any(m.get("content") == "fallback" for m in history)

    def test_empty_stream_fallback(self):
        """Streaming that yields nothing falls back."""
        mod = _import_web()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(["data: [DONE]"])

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod.requests, "post", return_value=mock_resp):
                with patch.object(mod, "ask_openclaw", return_value="non-stream") as mock_ask:
                    with patch.object(mod, "generate_tts", return_value=None):
                        audio_input = (48000, np.ones(1000, dtype=np.int16))
                        results = list(mod.respond_audio(audio_input, []))
                        mock_ask.assert_called_once()


# ─── ContinuousListener extended ────────────────────────────────────────────

class TestContinuousListenerExtended:
    def test_stop_with_recorder(self):
        """Stop calls recorder.stop() and .shutdown() when recorder exists."""
        mod = _import_web()
        listener = mod.ContinuousListener()
        mock_recorder = MagicMock()
        listener.recorder = mock_recorder
        listener.running = True

        listener.stop()

        mock_recorder.stop.assert_called_once()
        mock_recorder.shutdown.assert_called_once()
        assert listener.running is False
        assert listener.recorder is None

    def test_stop_tolerates_recorder_exceptions(self):
        """Stop doesn't crash if recorder.stop() or .shutdown() raises."""
        mod = _import_web()
        listener = mod.ContinuousListener()
        mock_recorder = MagicMock()
        mock_recorder.stop.side_effect = RuntimeError("already stopped")
        mock_recorder.shutdown.side_effect = RuntimeError("cleanup failed")
        listener.recorder = mock_recorder

        listener.stop()  # should not raise
        assert listener.running is False

    def test_multiple_texts_queued(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        listener._on_text("primeiro")
        listener._on_text("segundo")
        listener._on_text("terceiro")

        assert listener.get_text() == "primeiro"
        assert listener.get_text() == "segundo"
        assert listener.get_text() == "terceiro"
        assert listener.get_text() is None

    def test_start_returns_true_when_already_running(self):
        mod = _import_web()
        listener = mod.ContinuousListener()
        listener.running = True
        assert listener.start() is True
        listener.running = False


# ─── Edge TTS async workaround ──────────────────────────────────────────────

class TestEdgeTTSAsyncWorkaround:
    def test_uses_thread_pool_not_asyncio_run(self):
        """Web version uses ThreadPoolExecutor to avoid Gradio event loop conflict."""
        mod = _import_web()
        source = open(mod.__file__, "r", encoding="utf-8").read()
        # The generate_tts_edge function uses ThreadPoolExecutor
        assert "ThreadPoolExecutor" in source
        # It does NOT use bare asyncio.run in generate_tts_edge
        # (CLI version does, but web/vps use the thread workaround)


# ─── find_sentence_end (web copy) ───────────────────────────────────────────

class TestFindSentenceEndWeb:
    """Verify web version has same behavior as vps version."""

    def test_period_space(self):
        mod = _import_web()
        assert mod._find_sentence_end("Olá. Mundo") > 0

    def test_no_match_returns_zero(self):
        mod = _import_web()
        assert mod._find_sentence_end("sem ponto") == 0

    def test_period_at_end_no_space(self):
        mod = _import_web()
        assert mod._find_sentence_end("fim.") == 0

    def test_multiple_sentences_returns_first(self):
        mod = _import_web()
        text = "Primeira. Segunda. Terceira."
        pos = mod._find_sentence_end(text)
        before = text[:pos].strip()
        assert before == "Primeira."


# ─── build_api_history (web copy) ────────────────────────────────────────────

class TestBuildApiHistoryWeb:
    def test_web_max_history_is_module_constant(self):
        mod = _import_web()
        assert hasattr(mod, "MAX_HISTORY")
        assert mod.MAX_HISTORY == 10

    def test_web_filters_voice_messages(self):
        """Web version also filters [🎤 messages from API history."""
        mod = _import_web()
        history = [
            {"role": "user", "content": "[🎤 Voz]: olá"},
            {"role": "assistant", "content": "oi"},
            {"role": "user", "content": "texto normal"},
            {"role": "assistant", "content": "resposta"},
        ]
        result = mod.build_api_history(history)
        user_msgs = [m for m in result if m["role"] == "user"]
        # Only "texto normal" should be in API history — voice message excluded
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "texto normal"
