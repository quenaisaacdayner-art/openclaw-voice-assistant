"""Tests documenting code duplication across the 3 scripts.

These tests verify that all 3 versions implement the same core behaviors,
even though they're copy-pasted. NOT fixing this — just documenting it.
"""
import os
import sys
import ast
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_file(name):
    with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


def _get_function_names(source):
    """Extract all top-level and class-method function names from source."""
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


class TestDuplication:
    """Document which functions exist in which files."""

    def test_all_three_have_load_token(self):
        for name in ["voice_assistant.py", "voice_assistant_web.py", "voice_assistant_vps.py"]:
            source = _read_file(name)
            fns = _get_function_names(source)
            assert "load_token" in fns, f"{name} missing load_token"

    def test_all_three_have_ask_openclaw(self):
        for name in ["voice_assistant.py", "voice_assistant_web.py", "voice_assistant_vps.py"]:
            source = _read_file(name)
            fns = _get_function_names(source)
            assert "ask_openclaw" in fns, f"{name} missing ask_openclaw"

    def test_streaming_only_in_web_and_vps(self):
        """CLI version does NOT have streaming — web and VPS do."""
        cli = _get_function_names(_read_file("voice_assistant.py"))
        web = _get_function_names(_read_file("voice_assistant_web.py"))
        vps = _get_function_names(_read_file("voice_assistant_vps.py"))

        assert "ask_openclaw_stream" not in cli
        assert "ask_openclaw_stream" in web
        assert "ask_openclaw_stream" in vps

    def test_cli_has_unique_functions(self):
        """CLI has record_audio and play_audio (not in web/vps)."""
        cli = _get_function_names(_read_file("voice_assistant.py"))
        assert "record_audio" in cli
        assert "play_audio" in cli

    def test_web_has_realtime_stt_listener(self):
        source = _read_file("voice_assistant_web.py")
        assert "ContinuousListener" in source
        assert "REALTIME_STT_AVAILABLE" in source

    def test_vps_has_browser_listener(self):
        source = _read_file("voice_assistant_vps.py")
        assert "BrowserContinuousListener" in source

    def test_web_and_vps_both_have_build_api_history(self):
        web = _get_function_names(_read_file("voice_assistant_web.py"))
        vps = _get_function_names(_read_file("voice_assistant_vps.py"))
        assert "build_api_history" in web
        assert "build_api_history" in vps

    def test_web_and_vps_both_have_respond_text(self):
        web = _get_function_names(_read_file("voice_assistant_web.py"))
        vps = _get_function_names(_read_file("voice_assistant_vps.py"))
        assert "respond_text" in web
        assert "respond_text" in vps

    def test_web_and_vps_both_have_respond_audio(self):
        web = _get_function_names(_read_file("voice_assistant_web.py"))
        vps = _get_function_names(_read_file("voice_assistant_vps.py"))
        assert "respond_audio" in web
        assert "respond_audio" in vps

    def test_web_and_vps_both_have_transcribe_audio(self):
        web = _get_function_names(_read_file("voice_assistant_web.py"))
        vps = _get_function_names(_read_file("voice_assistant_vps.py"))
        assert "transcribe_audio" in web
        assert "transcribe_audio" in vps

    def test_web_and_vps_both_have_find_sentence_end(self):
        web = _get_function_names(_read_file("voice_assistant_web.py"))
        vps = _get_function_names(_read_file("voice_assistant_vps.py"))
        assert "_find_sentence_end" in web
        assert "_find_sentence_end" in vps

    def test_gateway_url_differs(self):
        """CLI and web use 18789, VPS uses 19789."""
        cli = _read_file("voice_assistant.py")
        web = _read_file("voice_assistant_web.py")
        vps = _read_file("voice_assistant_vps.py")

        assert "18789" in cli
        assert "18789" in web
        assert "19789" in vps

    def test_tts_engines_differ(self):
        """CLI and web support Piper + Edge. VPS is Edge only."""
        cli = _read_file("voice_assistant.py")
        web = _read_file("voice_assistant_web.py")
        vps = _read_file("voice_assistant_vps.py")

        assert "PIPER_AVAILABLE" in cli
        assert "PIPER_AVAILABLE" in web
        assert "PIPER_AVAILABLE" not in vps

    def test_piper_model_committed_in_repo(self):
        """63MB Piper model is in the repo — documenting this fact."""
        model_path = os.path.join(PROJECT_ROOT, "models", "pt_BR-faber-medium.onnx")
        assert os.path.exists(model_path)
        size_mb = os.path.getsize(model_path) / (1024 * 1024)
        assert size_mb > 50  # It's ~60MB


class TestFileInventory:
    """Document what files exist and their sizes."""

    def test_three_main_scripts(self):
        for name in ["voice_assistant.py", "voice_assistant_web.py", "voice_assistant_vps.py"]:
            path = os.path.join(PROJECT_ROOT, name)
            assert os.path.exists(path), f"Missing: {name}"

    def test_teste_tts_exists(self):
        """Diagnostic script exists in repo."""
        assert os.path.exists(os.path.join(PROJECT_ROOT, "teste_tts.py"))

    def test_upgrade_plan_exists(self):
        assert os.path.exists(os.path.join(PROJECT_ROOT, "UPGRADE_PLAN.md"))

    def test_requirements_has_all_deps(self):
        with open(os.path.join(PROJECT_ROOT, "requirements.txt")) as f:
            content = f.read()
        for dep in ["faster-whisper", "edge-tts", "numpy", "requests", "gradio", "scipy"]:
            assert dep in content, f"Missing dependency: {dep}"

    def test_requirements_includes_realtime_stt(self):
        """RealtimeSTT is in requirements even though it only works locally."""
        with open(os.path.join(PROJECT_ROOT, "requirements.txt")) as f:
            content = f.read()
        assert "RealtimeSTT" in content

    def test_requirements_includes_pyaudio(self):
        """PyAudio is in requirements even though VPS doesn't need it."""
        with open(os.path.join(PROJECT_ROOT, "requirements.txt")) as f:
            content = f.read()
        assert "PyAudio" in content
