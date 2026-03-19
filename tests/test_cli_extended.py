"""Extended tests for voice_assistant.py (CLI version).

Covers gaps not in test_cli.py. Captures current behavior — does NOT fix bugs.
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
import voice_assistant as cli


# ─── find_microphone extended ────────────────────────────────────────────────

class TestFindMicrophoneExtended:
    def test_microfone_keyword_portuguese(self):
        """Accepts 'Microfone' (Portuguese) as mic keyword."""
        fake_devices = [
            {"name": "Microfone do headset", "max_input_channels": 1},
        ]
        with patch("voice_assistant.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 0
            assert "Microfone" in name

    def test_microphone_keyword_english(self):
        fake_devices = [
            {"name": "USB Microphone", "max_input_channels": 1},
        ]
        with patch("voice_assistant.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 0

    def test_intel_wins_over_microphone_keyword(self):
        """Intel Smart Sound has higher priority than other mics."""
        fake_devices = [
            {"name": "USB Microphone", "max_input_channels": 1},
            {"name": "Intel Smart Sound Technology", "max_input_channels": 2},
        ]
        with patch("voice_assistant.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 1
            assert "Intel" in name

    def test_zero_input_channels_skipped(self):
        """Devices with max_input_channels=0 are output-only, skipped."""
        fake_devices = [
            {"name": "Intel Smart Sound Technology", "max_input_channels": 0},
            {"name": "Microphone", "max_input_channels": 1},
        ]
        with patch("voice_assistant.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 1
            assert "Microphone" in name

    def test_virtual_mic_skipped(self):
        fake_devices = [
            {"name": "Virtual Microphone", "max_input_channels": 1},
        ]
        fake_default = {"name": "System Default"}
        with patch("voice_assistant.sd.query_devices",
                    side_effect=lambda **kw: fake_default if kw.get("kind") else fake_devices):
            idx, name = cli.find_microphone()
            assert idx is None


# ─── ask_openclaw extended ───────────────────────────────────────────────────

class TestAskOpenClawExtended:
    def test_malformed_json_response(self):
        """If response JSON is missing 'choices', returns None via KeyError."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"not_choices": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("voice_assistant.requests.post", return_value=mock_resp):
            result = cli.ask_openclaw("olá", "tok", [])
            assert result is None

    def test_empty_choices_list(self):
        """Empty choices list raises IndexError → returns None."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("voice_assistant.requests.post", return_value=mock_resp):
            result = cli.ask_openclaw("olá", "tok", [])
            assert result is None

    def test_sends_correct_model(self, mock_openai_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        with patch("voice_assistant.requests.post", return_value=mock_resp) as mock_post:
            cli.ask_openclaw("olá", "tok", [])
            body = mock_post.call_args[1]["json"]
            assert body["model"] == cli.MODEL

    def test_timeout_set_to_120(self, mock_openai_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        with patch("voice_assistant.requests.post", return_value=mock_resp) as mock_post:
            cli.ask_openclaw("olá", "tok", [])
            assert mock_post.call_args[1]["timeout"] == 120

    def test_generic_request_exception_returns_none(self):
        import requests as req
        with patch("voice_assistant.requests.post",
                    side_effect=req.RequestException("generic")):
            result = cli.ask_openclaw("olá", "tok", [])
            assert result is None


# ─── speak_piper ─────────────────────────────────────────────────────────────

class TestSpeakPiper:
    def test_writes_wav_and_plays(self):
        class FakeChunk:
            audio_int16_bytes = b"\x00\x01" * 4000
            sample_channels = 1
            sample_width = 2
            sample_rate = 22050

        mock_voice = MagicMock()
        mock_voice.synthesize.return_value = [FakeChunk()]

        with patch("voice_assistant.play_audio") as mock_play:
            with patch("voice_assistant.os.path.getsize", return_value=8000):
                result = cli.speak_piper("teste", mock_voice)
                assert result is True
                mock_play.assert_called_once()

    def test_returns_false_on_empty_chunks(self):
        mock_voice = MagicMock()
        mock_voice.synthesize.return_value = []

        result = cli.speak_piper("teste", mock_voice)
        assert result is False

    def test_returns_false_on_small_file(self):
        class FakeChunk:
            audio_int16_bytes = b"\x00"
            sample_channels = 1
            sample_width = 2
            sample_rate = 22050

        mock_voice = MagicMock()
        mock_voice.synthesize.return_value = [FakeChunk()]

        with patch("voice_assistant.os.path.getsize", return_value=50):
            result = cli.speak_piper("teste", mock_voice)
            assert result is False

    def test_returns_false_on_exception(self):
        mock_voice = MagicMock()
        mock_voice.synthesize.side_effect = RuntimeError("piper crash")

        result = cli.speak_piper("teste", mock_voice)
        assert result is False


# ─── speak_edge ──────────────────────────────────────────────────────────────

class TestSpeakEdge:
    def test_plays_audio_on_success(self):
        with patch("voice_assistant.edge_tts.Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                with open(path, "wb") as f:
                    f.write(b"fake mp3 " * 50)

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            with patch("voice_assistant.play_audio") as mock_play:
                result = cli.speak_edge("teste")
                assert result is True
                mock_play.assert_called_once()

    def test_returns_false_on_missing_file(self):
        with patch("voice_assistant.edge_tts.Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                pass  # writes nothing

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            with patch("voice_assistant.os.path.exists", return_value=False):
                with patch("voice_assistant.play_audio"):
                    result = cli.speak_edge("teste")
                    assert result is False

    def test_returns_false_on_tiny_file(self):
        with patch("voice_assistant.edge_tts.Communicate") as mock_comm:
            mock_instance = MagicMock()

            async def fake_save(path):
                with open(path, "wb") as f:
                    f.write(b"x")

            mock_instance.save = fake_save
            mock_comm.return_value = mock_instance

            with patch("voice_assistant.play_audio"):
                result = cli.speak_edge("teste")
                assert result is False


# ─── play_audio ──────────────────────────────────────────────────────────────

class TestPlayAudioExtended:
    def test_linux_tries_players_in_order(self):
        """On Linux, tries mpv, ffplay, aplay in order."""
        with patch("voice_assistant.sys.platform", "linux"):
            with patch("voice_assistant.os.system", return_value=0) as mock_sys:
                with patch("voice_assistant.subprocess.Popen") as mock_popen:
                    cli.play_audio("test.wav")
                    # First which check should be for mpv
                    first_call = mock_sys.call_args_list[0][0][0]
                    assert "mpv" in first_call

    def test_linux_ffplay_uses_nodisp_flag(self):
        """ffplay gets special flags: -nodisp -autoexit."""
        with patch("voice_assistant.sys.platform", "linux"):
            # First call (mpv) fails, second call (ffplay) succeeds
            with patch("voice_assistant.os.system", side_effect=[1, 0]):
                with patch("voice_assistant.subprocess.Popen") as mock_popen:
                    cli.play_audio("test.wav")
                    args = mock_popen.call_args[0][0]
                    assert "ffplay" in args
                    assert "-nodisp" in args
                    assert "-autoexit" in args


# ─── speak wrapper ───────────────────────────────────────────────────────────

class TestSpeakWrapper:
    def test_edge_engine_skips_piper(self):
        """When TTS_ENGINE='edge', piper is never called."""
        original = cli.TTS_ENGINE
        cli.TTS_ENGINE = "edge"

        with patch("voice_assistant.speak_piper") as mock_piper:
            with patch("voice_assistant.speak_edge", return_value=True):
                cli.speak("teste", piper_voice=MagicMock())
                mock_piper.assert_not_called()

        cli.TTS_ENGINE = original

    def test_short_text_not_truncated(self):
        """Text <= 1500 chars is not truncated."""
        text = "a" * 1500
        with patch("voice_assistant.speak_piper", return_value=True) as mock_piper:
            cli.speak(text, piper_voice=MagicMock())
            called_text = mock_piper.call_args[0][0]
            assert len(called_text) == 1500
            assert "..." not in called_text


# ─── load_token extended ────────────────────────────────────────────────────

class TestLoadTokenExtended:
    def test_malformed_json_falls_through(self, tmp_path):
        """Invalid JSON in config file is caught, falls through to env."""
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()
        config_file = config_dir / "openclaw.json"
        config_file.write_text("NOT VALID JSON {{{")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch.dict(os.environ, {"OPENCLAW_GATEWAY_TOKEN": "fallback"}):
                token = cli.load_token()
                assert token == "fallback"

    def test_empty_token_string_falls_through(self, tmp_path):
        """Empty string token in config is falsy, falls through."""
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()
        config_file = config_dir / "openclaw.json"
        config_file.write_text(json.dumps({
            "gateway": {"auth": {"token": ""}}
        }))

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch.dict(os.environ, {"OPENCLAW_GATEWAY_TOKEN": "env-tok"}):
                token = cli.load_token()
                assert token == "env-tok"


# ─── transcribe ──────────────────────────────────────────────────────────────

class TestTranscribeExtended:
    def test_vad_parameters_min_silence(self, fake_wav_file):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)
        cli.transcribe(fake_wav_file, mock_model)
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
        result = cli.transcribe(fake_wav_file, mock_model)
        assert result == "palavra1 palavra2 palavra3"
