"""Configuração centralizada — constantes carregadas de variáveis de ambiente."""

import os
import sys
import json

# Diretório raiz do projeto (um nível acima de core/)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _detect_gateway_url():
    """Auto-detecta URL do gateway: env var > openclaw.json > fallback 18789."""
    env_url = os.environ.get("OPENCLAW_GATEWAY_URL")
    if env_url:
        return env_url
    config_path = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        port = cfg["gateway"]["port"]
        return f"http://127.0.0.1:{port}/v1/chat/completions"
    except (FileNotFoundError, KeyError, json.JSONDecodeError, TypeError):
        return "http://127.0.0.1:18789/v1/chat/completions"


GATEWAY_URL = _detect_gateway_url()
MODEL = os.environ.get("OPENCLAW_MODEL", "anthropic/claude-sonnet-4-6")
TTS_VOICE = os.environ.get("TTS_VOICE", "pt-BR-AntonioNeural")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper")  # "piper", "edge" ou "kokoro"
PIPER_MODEL = os.path.join(PROJECT_DIR, "models", "pt_BR-faber-medium.onnx")


def load_token():
    """Carrega token do gateway OpenClaw de ~/.openclaw/openclaw.json ou env var."""
    config_path = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        token = config["gateway"]["auth"]["token"]
        if token:
            return token
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass

    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if token:
        return token

    raise RuntimeError(
        "Token não encontrado. Configure em ~/.openclaw/openclaw.json ou OPENCLAW_GATEWAY_TOKEN"
    )
