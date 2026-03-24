"""
OpenClaw Voice Assistant — Entry point (comando `ova`)
Uso: ova [--host IP] [--port NUM] [--gateway-url URL] [--model MODELO] [--whisper tiny|small]
"""

import argparse
import os
import sys
import platform
import subprocess
import threading
import webbrowser

__version__ = "0.1.0"

# Garantir que a raiz do projeto esta no path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _kill_port(port):
    """Mata processo usando a porta especificada. Falha silenciosamente."""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["powershell", "-Command",
                 f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                 f"Select-Object -First 1 -ExpandProperty OwningProcess"],
                capture_output=True, text=True, timeout=5
            )
            pid = result.stdout.strip()
            if pid and pid.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               capture_output=True, timeout=5)
        else:
            result = subprocess.run(
                ["lsof", f"-ti:{port}"],
                capture_output=True, text=True, timeout=5
            )
            pid = result.stdout.strip()
            if pid:
                subprocess.run(["kill", pid], capture_output=True, timeout=5)
    except Exception:
        pass


def _print_banner(gateway_url, model, whisper, tts, host, port):
    """Imprime banner com configuracao atual."""
    url = f"http://{host}:{port}"
    print()
    print("\u2550" * 39)
    print("  OpenClaw Voice Assistant")
    print("\u2550" * 39)
    print(f"  Gateway: {gateway_url}")
    print(f"  Modelo:  {model}")
    print(f"  Whisper: {whisper}")
    print(f"  TTS:     {tts}")
    print(f"  URL:     {url}")
    print("\u2550" * 39)
    print()


def main(args=None):
    """Entry point principal."""
    parser = argparse.ArgumentParser(
        prog="ova",
        description="OpenClaw Voice Assistant — Speech-to-Speech"
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Endereco do server (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7860,
                        help="Porta (default: 7860)")
    parser.add_argument("--gateway-url",
                        help="URL do OpenClaw Gateway")
    parser.add_argument("--model",
                        help="Modelo LLM (ex: anthropic/claude-sonnet-4-6)")
    parser.add_argument("--whisper", choices=["tiny", "small"],
                        help="Modelo Whisper (tiny ou small)")
    parser.add_argument("--tts-engine", choices=["edge", "piper", "kokoro"],
                        help="Engine TTS")
    parser.add_argument("--tts-voice",
                        help="Voz TTS")
    parser.add_argument("--no-browser", action="store_true",
                        help="Nao abrir browser automaticamente")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")

    parsed = parser.parse_args(args)

    # Setar env vars ANTES de importar modulos do core
    if parsed.gateway_url:
        os.environ["OPENCLAW_GATEWAY_URL"] = parsed.gateway_url
    if parsed.model:
        os.environ["OPENCLAW_MODEL"] = parsed.model
    if parsed.whisper:
        os.environ["WHISPER_MODEL"] = parsed.whisper
    if parsed.tts_engine:
        os.environ["TTS_ENGINE"] = parsed.tts_engine
    if parsed.tts_voice:
        os.environ["TTS_VOICE"] = parsed.tts_voice

    os.environ["SERVER_HOST"] = parsed.host
    os.environ["PORT"] = str(parsed.port)

    # Ler valores finais (respeitando env vars ja definidas)
    gateway_url = os.environ.get("OPENCLAW_GATEWAY_URL",
                                 "http://127.0.0.1:18789/v1/chat/completions")
    model = os.environ.get("OPENCLAW_MODEL", "anthropic/claude-sonnet-4-6")
    whisper = os.environ.get("WHISPER_MODEL", "tiny")
    tts = os.environ.get("TTS_ENGINE", "edge")
    host = parsed.host
    port = parsed.port

    # Matar processo anterior na porta
    _kill_port(port)

    # Banner
    _print_banner(gateway_url, model, whisper, tts, host, port)

    # Abrir browser (com delay de 2s)
    if not parsed.no_browser:
        url = f"http://{host}:{port}"
        threading.Timer(2.0, webbrowser.open, [url]).start()

    # Importar e rodar uvicorn DEPOIS de setar env vars
    import importlib
    uvicorn = importlib.import_module("uvicorn")
    server_ws = importlib.import_module("server_ws")
    uvicorn.run(server_ws.app, host=host, port=port)


if __name__ == "__main__":
    main()
