"""Tests for voice_assistant.py (CLI version).

Captures current behavior — does NOT fix bugs.
"""
import os
import sys
import json
import wave
import tempfile
import threading
from unittest.mock import patch, MagicMock, PropertyMock
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_assistant as cli


# ─── Configuration defaults ──────────────────────────────────────────────────

class TestDefaults:
    def test_default_gateway_url(self):
        assert "18789" in cli.GATEWAY_URL
        assert cli.GATEWAY_URL.endswith("/v1/chat/completions")

    def test_default_model(self):
        assert cli.MODEL == "openclaw:main"

    def test_default_tts_voice(self):
        assert cli.TTS_VOICE == "pt-BR-AntonioNeural"

    def test_default_whisper_model(self):
        assert cli.WHISPER_MODEL == "small"

    def test_sample_rate(self):
        assert cli.SAMPLE_RATE == 16000

    def test_channels_mono(self):
        assert cli.CHANNELS == 1

    def test_default_tts_engine(self):
        assert cli.TTS_ENGINE == "piper"

    def test_max_history_is_defined_in_main(self):
        """MAX_HISTORY is a local variable inside main(), not a module-level constant."""
        source = open(cli.__file__, "r", encoding="utf-8").read()
        assert "MAX_HISTORY = 20" in source

    def test_audio_file_paths_in_script_dir(self):
        script_dir = os.path.dirname(os.path.abspath(cli.__file__))
        assert cli.AUDIO_FILE.startswith(script_dir)
        assert cli.AUDIO_FILE_EDGE.startswith(script_dir)

    def test_piper_model_path_in_models_dir(self):
        assert "models" in cli.PIPER_MODEL
        assert cli.PIPER_MODEL.endswith(".onnx")


# ─── find_microphone ─────────────────────────────────────────────────────────

class TestFindMicrophone:
    def test_prefers_intel_smart_sound(self):
        fake_devices = [
            {"name": "Iriun Webcam", "max_input_channels": 2},
            {"name": "Intel Smart Sound Technology", "max_input_channels": 2},
            {"name": "Realtek Microphone", "max_input_channels": 1},
        ]
        with patch("voice_assistant.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 1
            assert "Intel" in name

    def test_skips_iriun_virtual(self):
        fake_devices = [
            {"name": "Iriun Webcam #4", "max_input_channels": 2},
            {"name": "Micrófono Real", "max_input_channels": 1},
        ]
        with patch("voice_assistant.sd.query_devices", return_value=fake_devices):
            idx, name = cli.find_microphone()
            assert idx == 1
            assert "Iriun" not in name

    def test_falls_back_to_default(self):
        fake_devices = [
            {"name": "Iriun Webcam", "max_input_channels": 2},
            {"name": "Virtual Cable", "max_input_channels": 2},
        ]
        fake_default = {"name": "System Default Mic"}
        with patch("voice_assistant.sd.query_devices", side_effect=lambda **kw: fake_default if kw.get("kind") else fake_devices):
            idx, name = cli.find_microphone()
            assert idx is None
            assert name == "System Default Mic"

    def test_device_without_name_key(self):
        """Devices missing 'name' should not crash."""
        fake_devices = [
            {"max_input_channels": 2},  # no 'name'
        ]
        fake_default = {"name": "Fallback"}
        with patch("voice_assistant.sd.query_devices", side_effect=lambda **kw: fake_default if kw.get("kind") else fake_devices):
            idx, name = cli.find_microphone()
            assert idx is None


# ─── load_token ───────────────────────────────────────────────────────────────

class TestLoadToken:
    def test_loads_from_config_file(self, fake_openclaw_config):
        config_dir = os.path.dirname(fake_openclaw_config)
        with patch("os.path.expanduser", return_value=os.path.dirname(config_dir)):
            token = cli.load_token()
            assert token == "test-token-abc123"

    def test_falls_back_to_env_var(self, fake_openclaw_config_no_token):
        config_dir = os.path.dirname(fake_openclaw_config_no_token)
        with patch("os.path.expanduser", return_value=os.path.dirname(config_dir)):
            with patch.dict(os.environ, {"OPENCLAW_GATEWAY_TOKEN": "env-token-xyz"}):
                token = cli.load_token()
                assert token == "env-token-xyz"

    def test_exits_when_no_token(self, tmp_path):
        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch.dict(os.environ, {}, clear=True):
                # Remove any existing OPENCLAW_GATEWAY_TOKEN
                env = os.environ.copy()
                env.pop("OPENCLAW_GATEWAY_TOKEN", None)
                with patch.dict(os.environ, env, clear=True):
                    with pytest.raises(SystemExit):
                        cli.load_token()


# ─── transcribe ──────────────────────────────────────────────────────────────

class TestTranscribe:
    def test_returns_empty_string_on_error(self, fake_wav_file):
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = Exception("model error")
        result = cli.transcribe(fake_wav_file, mock_model)
        assert result == ""

    def test_joins_segments(self, fake_wav_file):
        seg1 = MagicMock()
        seg1.text = "olá"
        seg2 = MagicMock()
        seg2.text = "mundo"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], None)
        result = cli.transcribe(fake_wav_file, mock_model)
        assert result == "olá mundo"

    def test_strips_whitespace(self, fake_wav_file):
        seg = MagicMock()
        seg.text = "  texto com espaços  "
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], None)
        result = cli.transcribe(fake_wav_file, mock_model)
        assert result == "texto com espaços"

    def test_empty_segments_returns_empty(self, fake_wav_file):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)
        result = cli.transcribe(fake_wav_file, mock_model)
        assert result == ""

    def test_uses_vad_filter(self, fake_wav_file):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)
        cli.transcribe(fake_wav_file, mock_model)
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1]["vad_filter"] is True
        assert call_kwargs[1]["language"] == "pt"
        assert call_kwargs[1]["beam_size"] == 5


# ─── ask_openclaw ─────────────────────────────────────────────────────────────

class TestAskOpenClaw:
    def test_successful_response(self, mock_openai_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        with patch("voice_assistant.requests.post", return_value=mock_resp):
            result = cli.ask_openclaw("olá", "token123", [])
            assert result == "Resposta do agente OpenClaw."

    def test_sends_history_plus_user_message(self, mock_openai_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        history = [
            {"role": "user", "content": "msg anterior"},
            {"role": "assistant", "content": "resp anterior"},
        ]

        with patch("voice_assistant.requests.post", return_value=mock_resp) as mock_post:
            cli.ask_openclaw("nova msg", "tok", history)
            sent_body = mock_post.call_args[1]["json"]
            assert len(sent_body["messages"]) == 3
            assert sent_body["messages"][-1]["content"] == "nova msg"
            assert sent_body["messages"][-1]["role"] == "user"

    def test_connection_error_returns_none(self):
        with patch("voice_assistant.requests.post", side_effect=Exception("conn refused")):
            # Actually uses requests.ConnectionError
            import requests as req
            with patch("voice_assistant.requests.post", side_effect=req.ConnectionError()):
                result = cli.ask_openclaw("olá", "tok", [])
                assert result is None

    def test_timeout_returns_none(self):
        import requests as req
        with patch("voice_assistant.requests.post", side_effect=req.Timeout()):
            result = cli.ask_openclaw("olá", "tok", [])
            assert result is None

    def test_uses_bearer_auth(self, mock_openai_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        with patch("voice_assistant.requests.post", return_value=mock_resp) as mock_post:
            cli.ask_openclaw("olá", "my-secret-token", [])
            headers = mock_post.call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer my-secret-token"

    def test_history_is_not_mutated(self, mock_openai_response):
        """Passing history should not modify the original list."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_openai_response
        mock_resp.raise_for_status = MagicMock()

        history = [{"role": "user", "content": "old"}]
        original_len = len(history)

        with patch("voice_assistant.requests.post", return_value=mock_resp):
            cli.ask_openclaw("new", "tok", history)
            assert len(history) == original_len


# ─── speak / TTS ──────────────────────────────────────────────────────────────

class TestSpeak:
    def test_truncates_long_text(self):
        """Text > 1500 chars gets truncated with '...'."""
        long_text = "a" * 2000
        with patch("voice_assistant.speak_piper", return_value=True) as mock_piper:
            cli.speak(long_text, piper_voice=MagicMock())
            called_text = mock_piper.call_args[0][0]
            assert len(called_text) == 1503  # 1500 + "..."
            assert called_text.endswith("...")

    def test_piper_fallback_to_edge(self):
        """If Piper fails, falls back to Edge TTS."""
        with patch("voice_assistant.speak_piper", return_value=False):
            with patch("voice_assistant.speak_edge", return_value=True) as mock_edge:
                cli.speak("teste", piper_voice=MagicMock())
                mock_edge.assert_called_once()

    def test_edge_only_when_no_piper_voice(self):
        """When piper_voice is None, goes straight to Edge."""
        with patch("voice_assistant.speak_edge", return_value=True) as mock_edge:
            original_engine = cli.TTS_ENGINE
            cli.TTS_ENGINE = "piper"
            cli.speak("teste", piper_voice=None)
            mock_edge.assert_called_once()
            cli.TTS_ENGINE = original_engine


# ─── record_audio ─────────────────────────────────────────────────────────────

class TestRecordAudio:
    def test_catches_portaudio_error(self):
        """record_audio catches sd.PortAudioError but the PortAudioError(-1) __str__
        returns an int, causing a TypeError in the print(). Documenting this crash."""
        import sounddevice as sd_mod
        with patch("voice_assistant.sd.InputStream", side_effect=sd_mod.PortAudioError(-1)):
            # Current code: catches PortAudioError → tries print(f"...{e}") → crashes
            # because PortAudioError(-1).__str__() returns int, not str.
            with pytest.raises(TypeError):
                cli.record_audio(0)

    def test_silent_audio_returns_none(self):
        """Audio with peak < 100 is rejected."""
        silent_frames = [np.zeros((1600, 1), dtype=np.int16)]

        def fake_stream_context(*args, **kwargs):
            stream = MagicMock()
            stream.start = MagicMock()
            stream.stop = MagicMock()
            stream.close = MagicMock()
            return stream

        # This is hard to test in isolation due to the threading/input() pattern
        # Documenting the behavior: peak < 100 → returns None
        pass


# ─── play_audio ───────────────────────────────────────────────────────────────

class TestPlayAudio:
    def test_windows_uses_start(self):
        with patch("voice_assistant.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch("voice_assistant.subprocess.Popen") as mock_popen:
                # Reimport won't work due to module caching, test the function directly
                # The function checks sys.platform at call time
                cli.play_audio("test.mp3")
                mock_popen.assert_called_once()

    def test_mac_uses_afplay(self):
        with patch("voice_assistant.sys.platform", "darwin"):
            with patch("voice_assistant.subprocess.Popen") as mock_popen:
                cli.play_audio("test.mp3")
                args = mock_popen.call_args[0][0]
                assert args[0] == "afplay"
