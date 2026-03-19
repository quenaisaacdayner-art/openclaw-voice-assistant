"""Extended tests for voice_assistant_app.py — LOCAL mode features.

Adapted for unified core/ architecture.
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

import core.config as config
import core.stt
import core.tts
import core.llm
import core.history


def _import_app():
    with patch("core.config.load_token", return_value="test-token"):
        with patch("core.tts.init_piper"):
            import voice_assistant_app as mod
            return mod


# ─── Whisper lazy loading ────────────────────────────────────────────────────

class TestGetWhisper:
    def test_lazy_loads_on_first_call(self):
        original = core.stt._whisper_model
        core.stt._whisper_model = None

        mock_model = MagicMock()
        with patch("core.stt.WhisperModel", return_value=mock_model):
            result = core.stt._get_whisper()
            assert result is mock_model
            assert core.stt._whisper_model is mock_model

        core.stt._whisper_model = original

    def test_returns_cached_on_second_call(self):
        original = core.stt._whisper_model
        cached = MagicMock()
        core.stt._whisper_model = cached

        result = core.stt._get_whisper()
        assert result is cached

        core.stt._whisper_model = original

    def test_uses_cpu_int8(self):
        original = core.stt._whisper_model
        core.stt._whisper_model = None

        with patch("core.stt.WhisperModel", return_value=MagicMock()) as mock_cls:
            core.stt._get_whisper()
            mock_cls.assert_called_once_with(config.WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

        core.stt._whisper_model = original


# ─── generate_tts wrapper ───────────────────────────────────────────────────

class TestGenerateTTS:
    def test_returns_none_for_empty_text(self):
        assert core.tts.generate_tts("") is None
        assert core.tts.generate_tts(None) is None

    def test_returns_none_for_error_prefix(self):
        assert core.tts.generate_tts("❌ erro aconteceu") is None

    def test_piper_fallback_to_edge(self):
        original_engine = core.tts._tts_engine
        original_voice = core.tts.piper_voice
        core.tts._tts_engine = "piper"
        core.tts.piper_voice = MagicMock()

        with patch("core.tts.generate_tts_piper", return_value=None):
            with patch("core.tts.generate_tts_edge", return_value="/tmp/fallback.mp3") as mock_edge:
                result = core.tts.generate_tts("texto")
                mock_edge.assert_called_once()
                assert result == "/tmp/fallback.mp3"

        core.tts._tts_engine = original_engine
        core.tts.piper_voice = original_voice

    def test_edge_only_when_engine_edge(self):
        original_engine = core.tts._tts_engine
        core.tts._tts_engine = "edge"

        with patch("core.tts.generate_tts_edge", return_value="/tmp/out.mp3") as mock_edge:
            result = core.tts.generate_tts("texto")
            mock_edge.assert_called_once()

        core.tts._tts_engine = original_engine

    def test_cleans_previous_file(self, tmp_path):
        old_file = str(tmp_path / "prev.mp3")
        with open(old_file, "w") as f:
            f.write("old")
        core.tts._previous_tts_file = old_file

        original_engine = core.tts._tts_engine
        core.tts._tts_engine = "edge"
        with patch("core.tts.generate_tts_edge", return_value=None):
            core.tts.generate_tts("text")
        core.tts._tts_engine = original_engine

        assert not os.path.exists(old_file)

    def test_truncates_long_text(self):
        original_engine = core.tts._tts_engine
        core.tts._tts_engine = "edge"

        with patch("core.tts.generate_tts_edge", return_value=None) as mock_edge:
            core.tts.generate_tts("a" * 2000)
            called_text = mock_edge.call_args[0][0]
            assert len(called_text) == 1503

        core.tts._tts_engine = original_engine

    def test_tracks_new_file_in_global(self):
        original_engine = core.tts._tts_engine
        core.tts._tts_engine = "edge"
        core.tts._previous_tts_file = None

        with patch("core.tts.generate_tts_edge", return_value="/tmp/new.mp3"):
            core.tts.generate_tts("text")
            assert core.tts._previous_tts_file == "/tmp/new.mp3"

        core.tts._tts_engine = original_engine
        core.tts._previous_tts_file = None


# ─── toggle_listening (LOCAL mode) ───────────────────────────────────────────

class TestToggleListeningWeb:
    def test_toggle_on_success(self):
        mod = _import_app()
        if mod.MODE != "LOCAL":
            pytest.skip("LOCAL mode only")

        listener = mod.continuous_listener
        with patch.object(listener, "start", return_value=True):
            result = mod.toggle_listening(False)
            is_on, btn, status, audio_update = result
            assert is_on is True
            assert "Parar" in btn

    def test_toggle_on_failure(self):
        mod = _import_app()
        if mod.MODE != "LOCAL":
            pytest.skip("LOCAL mode only")

        listener = mod.continuous_listener
        with patch.object(listener, "start", return_value=False):
            result = mod.toggle_listening(False)
            is_on, btn, status, audio_update = result
            assert is_on is False
            assert "Falha" in status or "Ativar" in btn

    def test_toggle_off(self):
        mod = _import_app()
        if mod.MODE != "LOCAL":
            pytest.skip("LOCAL mode only")

        listener = mod.continuous_listener
        with patch.object(listener, "stop") as mock_stop:
            result = mod.toggle_listening(True)
            is_on, btn, status, audio_update = result
            assert is_on is False
            mock_stop.assert_called_once()


# ─── poll_continuous ─────────────────────────────────────────────────────────

class TestPollContinuous:
    def test_returns_unchanged_when_off(self):
        mod = _import_app()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined (BROWSER mode)")

        history = [{"role": "user", "content": "hi"}]
        results = list(mod.poll_continuous(history, False))
        assert len(results) >= 1
        assert results[-1] == (history, None)

    def test_returns_unchanged_when_processing(self):
        mod = _import_app()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined")

        mod.continuous_listener.processing = True
        results = list(mod.poll_continuous([], True))
        assert results[-1] == ([], None)
        mod.continuous_listener.processing = False

    def test_returns_unchanged_when_no_text(self):
        mod = _import_app()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined")

        mod.continuous_listener.processing = False
        with patch.object(mod.continuous_listener, "get_text", return_value=None):
            results = list(mod.poll_continuous([], True))
            assert results[-1] == ([], None)

    def test_processes_text_when_available(self):
        mod = _import_app()
        if not hasattr(mod, "poll_continuous"):
            pytest.skip("poll_continuous not defined")

        mod.continuous_listener.processing = False
        with patch.object(mod.continuous_listener, "get_text", return_value="olá"):
            with patch.object(mod, "ask_openclaw_stream") as mock_stream:
                mock_stream.return_value = iter(["resposta"])
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.poll_continuous([], True))
                    last_history, last_audio = results[-1]
                    assert any("[🎤 Voz]" in m.get("content", "") for m in last_history)
                    assert any(m["role"] == "assistant" for m in last_history)

        assert mod.continuous_listener.processing is False


# ─── respond_text streaming edge cases ──────────────────────────────────────

class TestRespondTextExtended:
    def test_fallback_to_non_streaming_when_empty(self):
        mod = _import_app()

        with patch.object(mod, "ask_openclaw_stream", return_value=iter([])):
            with patch.object(mod, "ask_openclaw", return_value="fallback") as mock_ask:
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_text("pergunta", []))
                    mock_ask.assert_called_once()
                    last = results[-1]
                    history = last[1]
                    assert any(m.get("content") == "fallback" for m in history)

    def test_exception_falls_back_to_non_streaming(self):
        mod = _import_app()

        with patch.object(mod, "ask_openclaw_stream", side_effect=Exception("network")):
            with patch.object(mod, "ask_openclaw", return_value="safe fallback"):
                with patch.object(mod, "generate_tts", return_value=None):
                    results = list(mod.respond_text("pergunta", []))
                    last = results[-1]
                    history = last[1]
                    assert any(m.get("content") == "safe fallback" for m in history)

    def test_first_sentence_tts_during_stream(self):
        mod = _import_app()

        with patch.object(mod, "ask_openclaw_stream") as mock_stream:
            mock_stream.return_value = iter(["Primeira frase. ", "Primeira frase. Segunda parte"])
            tts_calls = []

            def fake_tts(text):
                tts_calls.append(text)
                return "/tmp/audio.wav" if text else None

            with patch.object(mod, "generate_tts", side_effect=fake_tts):
                results = list(mod.respond_text("pergunta", []))

        assert len(tts_calls) >= 1


# ─── respond_audio extended ──────────────────────────────────────────────────

class TestRespondAudioExtended:
    def test_streaming_exception_fallback(self):
        mod = _import_app()

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
        mod = _import_app()

        with patch.object(mod, "transcribe_audio", return_value="olá"):
            with patch.object(mod, "ask_openclaw_stream", return_value=iter([])):
                with patch.object(mod, "ask_openclaw", return_value="non-stream") as mock_ask:
                    with patch.object(mod, "generate_tts", return_value=None):
                        audio_input = (48000, np.ones(1000, dtype=np.int16))
                        results = list(mod.respond_audio(audio_input, []))
                        mock_ask.assert_called_once()


# ─── ContinuousListener extended ────────────────────────────────────────────

class TestContinuousListenerExtended:
    def test_stop_with_recorder(self):
        mod = _import_app()
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
        mod = _import_app()
        listener = mod.ContinuousListener()
        mock_recorder = MagicMock()
        mock_recorder.stop.side_effect = RuntimeError("already stopped")
        mock_recorder.shutdown.side_effect = RuntimeError("cleanup failed")
        listener.recorder = mock_recorder

        listener.stop()
        assert listener.running is False

    def test_multiple_texts_queued(self):
        mod = _import_app()
        listener = mod.ContinuousListener()
        listener._on_text("primeiro")
        listener._on_text("segundo")
        listener._on_text("terceiro")

        assert listener.get_text() == "primeiro"
        assert listener.get_text() == "segundo"
        assert listener.get_text() == "terceiro"
        assert listener.get_text() is None

    def test_start_returns_true_when_already_running(self):
        mod = _import_app()
        if mod.MODE != "LOCAL":
            pytest.skip("LOCAL mode only — start() checks MODE first")
        listener = mod.ContinuousListener()
        listener.running = True
        assert listener.start() is True
        listener.running = False


# ─── Edge TTS async workaround ──────────────────────────────────────────────

class TestEdgeTTSAsyncWorkaround:
    def test_uses_thread_pool_not_asyncio_run(self):
        source = open(core.tts.__file__, "r", encoding="utf-8").read()
        assert "ThreadPoolExecutor" in source


# ─── find_sentence_end (via core.llm) ────────────────────────────────────────

class TestFindSentenceEndWeb:
    def test_period_space(self):
        assert core.llm._find_sentence_end("Olá. Mundo") > 0

    def test_no_match_returns_zero(self):
        assert core.llm._find_sentence_end("sem ponto") == 0

    def test_period_at_end_detected(self):
        assert core.llm._find_sentence_end("fim.") > 0

    def test_multiple_sentences_returns_first(self):
        text = "Primeira. Segunda. Terceira."
        pos = core.llm._find_sentence_end(text)
        before = text[:pos].strip()
        assert before == "Primeira."


# ─── build_api_history (via core.history) ────────────────────────────────────

class TestBuildApiHistoryWeb:
    def test_max_history_is_module_constant(self):
        assert hasattr(core.history, "MAX_HISTORY")
        assert core.history.MAX_HISTORY == 10

    def test_strips_voice_prefix_keeps_content(self):
        history = [
            {"role": "user", "content": "[🎤 Voz]: olá"},
            {"role": "assistant", "content": "oi"},
            {"role": "user", "content": "texto normal"},
            {"role": "assistant", "content": "resposta"},
        ]
        result = core.history.build_api_history(history)
        user_msgs = [m for m in result if m["role"] == "user"]
        assert len(user_msgs) == 2
        assert user_msgs[0]["content"] == "olá"
        assert user_msgs[1]["content"] == "texto normal"
