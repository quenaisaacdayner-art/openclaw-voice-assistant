"""Extended tests for voice_assistant_cli.py (CLI version).

Adapted for the unified core/ architecture.
"""
import os
import sys
import json
import wave
import tempfile
from unittest.mock import patch, MagicMock, call
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_assistant_cli as cli
import core.config as config
import core.llm
import core.tts


# ─── find_microphone extended ────────────────────────────────────────────────

class TestFindMicrophoneExtended:
    def test_microfone_keyword_portuguese(self):
        fake_devices = [
            {"name": "Microfone do headset", "max_input_channels": 1},
        ]
        with patch("voice_assistant_cli.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 0
            assert "Microfone" in name

    def test_microphone_keyword_english(self):
        fake_devices = [
            {"name": "USB Microphone", "max_input_channels": 1},
        ]
        with patch("voice_assistant_cli.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 0

    def test_intel_wins_over_microphone_keyword(self):
        fake_devices = [
            {"name": "USB Microphone", "max_input_channels": 1},
            {"name": "Intel Smart Sound Technology", "max_input_channels": 2},
        ]
        with patch("voice_assistant_cli.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 1
            assert "Intel" in name

    def test_zero_input_channels_skipped(self):
        fake_devices = [
            {"name": "Intel Smart Sound Technology", "max_input_channels": 0},
            {"name": "Microphone", "max_input_channels": 1},
        ]
        with patch("voice_assistant_cli.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 1
            assert "Microphone" in name

    def test_virtual_mic_skipped(self):
        fake_devices = [
            {"name": "Virtual Microphone", "max_input_channels": 1},
        ]
        fake_default = {"name": "System Default"}
        with patch("voice_assistant_cli.sd.query_devices",
                    side_effect=lambda **kw: fake_default if kw.get("kind") else fake_devices):
            idx, name = cli.find_microphone()
            assert idx is None


# ─── ask_openclaw extended ───────────────────────────────────────────────────

class TestAskOpenClawExtended:
    def test_malformed_json_response(self):
        """If response JSON is missing 'choices', returns error string."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"not_choices": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(core.llm._session, "post", return_value=mock_resp):
            result = core.llm.ask_openclaw("olá", "tok", [])
            assert isinstance(result, str)
            assert "❌" in result

    def test_empty_choices_list(self):
        """Empty choices list → error string."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(core.llm._session, "post", return_value=mock_resp):
            result = core.llm.ask_openclaw("olá", "tok", [])
            assert isinstance(result, str)
            assert "❌" in result

    def test_sends_correct_model(self, mock_openai_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        with patch.object(core.llm._session, "post", return_value=mock_resp) as mock_post:
            core.llm.ask_openclaw("olá", "tok", [])
            body = mock_post.call_args[1]["json"]
            assert body["model"] == config.MODEL

    def test_timeout_set_to_120(self, mock_openai_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        with patch.object(core.llm._session, "post", return_value=mock_resp) as mock_post:
            core.llm.ask_openclaw("olá", "tok", [])
            assert mock_post.call_args[1]["timeout"] == 120

    def test_generic_request_exception_returns_error_string(self):
        import requests as req
        with patch.object(core.llm._session, "post",
                    side_effect=req.RequestException("generic")):
            result = core.llm.ask_openclaw("olá", "tok", [])
            assert isinstance(result, str)
            assert "❌" in result


# ─── TTS (via core.tts) ─────────────────────────────────────────────────────

class TestTTSViaCore:
    def test_generate_tts_returns_none_for_empty(self):
        assert core.tts.generate_tts("") is None
        assert core.tts.generate_tts(None) is None

    def test_generate_tts_returns_none_for_error_prefix(self):
        assert core.tts.generate_tts("❌ erro") is None

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


# ─── play_audio ──────────────────────────────────────────────────────────────

class TestPlayAudioExtended:
    def test_linux_tries_players_in_order(self):
        with patch("voice_assistant_cli.sys.platform", "linux"):
            with patch("voice_assistant_cli.os.system", return_value=0) as mock_sys:
                with patch("voice_assistant_cli.subprocess.Popen") as mock_popen:
                    cli.play_audio("test.wav")
                    first_call = mock_sys.call_args_list[0][0][0]
                    assert "mpv" in first_call

    def test_linux_ffplay_uses_nodisp_flag(self):
        with patch("voice_assistant_cli.sys.platform", "linux"):
            with patch("voice_assistant_cli.os.system", side_effect=[1, 0]):
                with patch("voice_assistant_cli.subprocess.Popen") as mock_popen:
                    cli.play_audio("test.wav")
                    args = mock_popen.call_args[0][0]
                    assert "ffplay" in args
                    assert "-nodisp" in args
                    assert "-autoexit" in args


# ─── speak wrapper ───────────────────────────────────────────────────────────

class TestSpeakWrapper:
    def test_short_text_not_truncated(self):
        text = "a" * 1500
        with patch("voice_assistant_cli.generate_tts", return_value="/tmp/a.wav") as mock_tts:
            with patch("voice_assistant_cli.play_audio"):
                cli.speak(text)
                called_text = mock_tts.call_args[0][0]
                assert len(called_text) == 1500
                assert "..." not in called_text


# ─── load_token extended ────────────────────────────────────────────────────

class TestLoadTokenExtended:
    def test_malformed_json_falls_through(self, tmp_path):
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()
        config_file = config_dir / "openclaw.json"
        config_file.write_text("NOT VALID JSON {{{")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch.dict(os.environ, {"OPENCLAW_GATEWAY_TOKEN": "fallback"}):
                token = config.load_token()
                assert token == "fallback"

    def test_empty_token_string_falls_through(self, tmp_path):
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()
        config_file = config_dir / "openclaw.json"
        config_file.write_text(json.dumps({
            "gateway": {"auth": {"token": ""}}
        }))

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch.dict(os.environ, {"OPENCLAW_GATEWAY_TOKEN": "env-tok"}):
                token = config.load_token()
                assert token == "env-tok"


# ─── transcribe extended ────────────────────────────────────────────────────

class TestTranscribeExtended:
    def test_vad_parameters_min_silence(self, fake_wav_file):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)
        with patch("voice_assistant_cli._get_whisper", return_value=mock_model):
            cli.transcribe(fake_wav_file)
            call_kwargs = mock_model.transcribe.call_args[1]
            assert call_kwargs["vad_parameters"]["min_silence_duration_ms"] == 500

    def test_multiple_segments_joined_with_space(self, fake_wav_file):
        segs = []
        for word in ["palavra1", "palavra2", "palavra3"]:
            s = MagicMock()
            s.text = word
            segs.append(s)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (segs, None)
        with patch("voice_assistant_cli._get_whisper", return_value=mock_model):
            result = cli.transcribe(fake_wav_file)
            assert result == "palavra1 palavra2 palavra3"
