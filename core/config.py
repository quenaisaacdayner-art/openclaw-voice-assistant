"""Configuração centralizada — constantes carregadas de variáveis de ambiente."""

import os
import sys
import json

# Diretório raiz do projeto (um nível acima de core/)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GATEWAY_URL = os.environ.get(
    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions"
)
MODEL = os.environ.get("OPENCLAW_MODEL", "openclaw:main")
TTS_VOICE = os.environ.get("TTS_VOICE", "pt-BR-AntonioNeural")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper")  # "piper" (local) ou "edge" (Microsoft)
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
