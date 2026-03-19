"""Tests verifying core/ is the single source of truth.

After unification, all shared logic lives in core/ and scripts import from it.
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
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def _get_imports(source):
    """Extract import sources from source code."""
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


# ─── Core has all shared functions ──────────────────────────────────────────

class TestCoreIsSource:
    """Verify core/ contains all the shared functions."""

    def test_core_config_has_load_token(self):
        source = _read_file(os.path.join("core", "config.py"))
        fns = _get_function_names(source)
        assert "load_token" in fns

    def test_core_stt_has_transcribe_audio(self):
        source = _read_file(os.path.join("core", "stt.py"))
        fns = _get_function_names(source)
        assert "transcribe_audio" in fns
        assert "_get_whisper" in fns

    def test_core_tts_has_generate_tts(self):
        source = _read_file(os.path.join("core", "tts.py"))
        fns = _get_function_names(source)
        assert "generate_tts" in fns
        assert "generate_tts_piper" in fns
        assert "generate_tts_edge" in fns
        assert "init_piper" in fns

    def test_core_llm_has_ask_openclaw(self):
        source = _read_file(os.path.join("core", "llm.py"))
        fns = _get_function_names(source)
        assert "ask_openclaw" in fns
        assert "ask_openclaw_stream" in fns
        assert "_find_sentence_end" in fns

    def test_core_history_has_build_api_history(self):
        source = _read_file(os.path.join("core", "history.py"))
        fns = _get_function_names(source)
        assert "build_api_history" in fns

    def test_core_config_has_constants(self):
        source = _read_file(os.path.join("core", "config.py"))
        for const in ["GATEWAY_URL", "MODEL", "TTS_VOICE", "WHISPER_MODEL_SIZE", "TTS_ENGINE", "PIPER_MODEL"]:
            assert const in source, f"Missing constant: {const}"


# ─── Scripts import from core ──────────────────────────────────────────────

class TestScriptsImportFromCore:
    """Verify CLI and App import from core/, not reimplementing."""

    def test_cli_imports_from_core(self):
        source = _read_file("voice_assistant_cli.py")
        imports = _get_imports(source)
        assert "core.config" in imports
        assert "core.stt" in imports
        assert "core.llm" in imports
        assert "core.tts" in imports

    def test_app_imports_from_core(self):
        source = _read_file("voice_assistant_app.py")
        imports = _get_imports(source)
        assert "core.config" in imports
        assert "core.stt" in imports
        assert "core.llm" in imports
        assert "core.tts" in imports
        assert "core.history" in imports

    def test_cli_does_not_redefine_shared_functions(self):
        """CLI should NOT have its own ask_openclaw, generate_tts, etc."""
        source = _read_file("voice_assistant_cli.py")
        fns = _get_function_names(source)
        for fn in ["ask_openclaw", "generate_tts", "load_token", "transcribe_audio"]:
            assert fn not in fns, f"CLI redefines {fn} — should import from core/"

    def test_app_does_not_redefine_shared_functions(self):
        """App should NOT have its own ask_openclaw, transcribe_audio, etc."""
        source = _read_file("voice_assistant_app.py")
        fns = _get_function_names(source)
        for fn in ["ask_openclaw", "ask_openclaw_stream", "generate_tts",
                    "load_token", "transcribe_audio", "_get_whisper",
                    "build_api_history", "_find_sentence_end"]:
            assert fn not in fns, f"App redefines {fn} — should import from core/"


# ─── App has both listener classes ──────────────────────────────────────────

class TestAppListeners:
    def test_app_has_continuous_listener(self):
        source = _read_file("voice_assistant_app.py")
        assert "class ContinuousListener" in source

    def test_app_has_browser_continuous_listener(self):
        source = _read_file("voice_assistant_app.py")
        assert "class BrowserContinuousListener" in source

    def test_app_has_respond_text(self):
        source = _read_file("voice_assistant_app.py")
        fns = _get_function_names(source)
        assert "respond_text" in fns

    def test_app_has_respond_audio(self):
        source = _read_file("voice_assistant_app.py")
        fns = _get_function_names(source)
        assert "respond_audio" in fns


# ─── Unified ask_openclaw signature ────────────────────────────────────────

class TestUnifiedSignatures:
    def test_core_ask_openclaw_has_token_param(self):
        source = _read_file(os.path.join("core", "llm.py"))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ask_openclaw":
                arg_names = [a.arg for a in node.args.args]
                assert "text" in arg_names
                assert "token" in arg_names
                assert "history_messages" in arg_names
                break

    def test_core_ask_openclaw_stream_has_token_param(self):
        source = _read_file(os.path.join("core", "llm.py"))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ask_openclaw_stream":
                arg_names = [a.arg for a in node.args.args]
                assert "token" in arg_names
                break


# ─── File inventory ────────────────────────────────────────────────────────

class TestFileInventory:
    def test_core_package_exists(self):
        core_dir = os.path.join(PROJECT_ROOT, "core")
        assert os.path.isdir(core_dir)
        for name in ["__init__.py", "config.py", "stt.py", "tts.py", "llm.py", "history.py"]:
            assert os.path.exists(os.path.join(core_dir, name)), f"Missing core/{name}"

    def test_unified_app_exists(self):
        assert os.path.exists(os.path.join(PROJECT_ROOT, "voice_assistant_app.py"))

    def test_cli_exists(self):
        assert os.path.exists(os.path.join(PROJECT_ROOT, "voice_assistant_cli.py"))

    def test_old_scripts_removed(self):
        """Old scripts were removed in Fase 3 — only unified app and CLI remain."""
        for name in ["voice_assistant.py", "voice_assistant_web.py", "voice_assistant_vps.py"]:
            assert not os.path.exists(os.path.join(PROJECT_ROOT, name)), f"Old script {name} should have been removed"

    def test_requirements_has_all_deps(self):
        with open(os.path.join(PROJECT_ROOT, "requirements.txt")) as f:
            content = f.read()
        for dep in ["faster-whisper", "edge-tts", "numpy", "requests", "gradio", "scipy"]:
            assert dep in content, f"Missing dependency: {dep}"
