"""Testes para o entry point `ova` (core/__main__.py) e pyproject.toml."""

import importlib
import os
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

# Garantir raiz do projeto no path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


_real_import_module = importlib.import_module


def _run_main_mocked(args=None):
    """Roda main() com uvicorn e server_ws mockados. Retorna mock_uvicorn."""
    from core.__main__ import main

    mock_uvicorn = MagicMock()
    mock_server_ws = MagicMock()

    def fake_import(name):
        if name == "uvicorn":
            return mock_uvicorn
        if name == "server_ws":
            return mock_server_ws
        return _real_import_module(name)

    with patch("importlib.import_module", side_effect=fake_import), \
         patch("webbrowser.open"):
        main(args or ["--no-browser"])

    return mock_uvicorn, mock_server_ws


# ─── test_core_main_importable ───────────────────────────────────────────────

def test_core_main_importable():
    """from core.__main__ import main nao levanta excecao."""
    from core.__main__ import main
    assert callable(main)


# ─── test_pyproject_exists ───────────────────────────────────────────────────

def test_pyproject_exists():
    """pyproject.toml existe e tem [project.scripts]."""
    pyproject_path = os.path.join(PROJECT_ROOT, "pyproject.toml")
    assert os.path.isfile(pyproject_path)
    with open(pyproject_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "[project.scripts]" in content
    assert 'ova = "core.__main__:main"' in content


# ─── test_ova_help ───────────────────────────────────────────────────────────

def test_ova_help():
    """ova --help retorna codigo 0 e contem 'OpenClaw Voice Assistant'."""
    result = subprocess.run(
        [sys.executable, "-m", "core", "--help"],
        capture_output=True, text=True, timeout=10,
        cwd=PROJECT_ROOT
    )
    assert result.returncode == 0
    assert "OpenClaw Voice Assistant" in result.stdout or "ova" in result.stdout


# ─── test_ova_version ────────────────────────────────────────────────────────

def test_ova_version():
    """ova --version retorna '0.1.0'."""
    result = subprocess.run(
        [sys.executable, "-m", "core", "--version"],
        capture_output=True, text=True, timeout=10,
        cwd=PROJECT_ROOT
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


# ─── test_main_sets_env_vars ─────────────────────────────────────────────────

def test_main_sets_env_vars():
    """main() com --model seta os.environ['OPENCLAW_MODEL']."""
    _run_main_mocked(["--model", "test-model", "--no-browser"])
    assert os.environ.get("OPENCLAW_MODEL") == "test-model"


# ─── test_main_default_host ─────────────────────────────────────────────────

def test_main_default_host():
    """Sem args, host default e 127.0.0.1."""
    mock_uvicorn, _ = _run_main_mocked(["--no-browser"])
    mock_uvicorn.run.assert_called_once()
    _, kwargs = mock_uvicorn.run.call_args
    assert kwargs["host"] == "127.0.0.1"


# ─── test_main_default_port ─────────────────────────────────────────────────

def test_main_default_port():
    """Sem args, port default e 7860."""
    mock_uvicorn, _ = _run_main_mocked(["--no-browser"])
    mock_uvicorn.run.assert_called_once()
    _, kwargs = mock_uvicorn.run.call_args
    assert kwargs["port"] == 7860
