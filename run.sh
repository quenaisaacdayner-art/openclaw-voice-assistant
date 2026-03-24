#!/bin/bash
# OpenClaw Voice Assistant — Script "faz tudo" (Linux/Mac)
# Uso: bash run.sh [--host IP] [--port NUM] [--gateway-url URL] [--model MODELO] [--whisper tiny|small] [--help]

set -e

# ─── Detectar diretorio do script ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Help ─────────────────────────────────────────────────────────────────────
show_help() {
    cat <<'HELP'
OpenClaw Voice Assistant — run.sh

Uso: bash run.sh [opcoes]

Opcoes:
  --host <ip>           Endereco do server (default: 127.0.0.1, use 0.0.0.0 pra VPS)
  --port <numero>       Porta do server (default: 7860)
  --gateway-url <url>   URL do OpenClaw Gateway
  --model <modelo>      Modelo LLM (ex: anthropic/claude-sonnet-4-6)
  --whisper <tiny|small> Modelo Whisper STT
  --help                Mostrar esta ajuda
HELP
    exit 0
}

# ─── Parse argumentos CLI ─────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)      CLI_HOST="$2"; shift 2 ;;
        --port)      CLI_PORT="$2"; shift 2 ;;
        --gateway-url) CLI_GATEWAY_URL="$2"; shift 2 ;;
        --model)     CLI_MODEL="$2"; shift 2 ;;
        --whisper)   CLI_WHISPER="$2"; shift 2 ;;
        --help)      show_help ;;
        *) echo "Opcao desconhecida: $1"; show_help ;;
    esac
done

# ─── Verificar venv ──────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "Virtualenv nao encontrado. Rodando setup.sh..."
    bash setup.sh
fi

source venv/bin/activate 2>/dev/null || {
    echo "Falha ao ativar virtualenv. Rode: bash setup.sh"
    exit 1
}

# ─── Matar processo na porta 7860 ────────────────────────────────────────────
TARGET_PORT="${CLI_PORT:-${PORT:-7860}}"
if command -v lsof &>/dev/null; then
    OLD_PID=$(lsof -ti:"$TARGET_PORT" 2>/dev/null || true)
    if [ -n "$OLD_PID" ]; then
        echo "Matando processo anterior na porta $TARGET_PORT (PID: $OLD_PID)"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
    fi
fi

# ─── Configurar variaveis de ambiente ─────────────────────────────────────────
# Auto-detectar gateway URL de ~/.openclaw/openclaw.json
if [ -z "$OPENCLAW_GATEWAY_URL" ]; then
    OPENCLAW_PORT=$(python3 -c "import json; print(json.load(open('$HOME/.openclaw/openclaw.json'))['gateway']['port'])" 2>/dev/null || echo "18789")
    export OPENCLAW_GATEWAY_URL="http://127.0.0.1:${OPENCLAW_PORT}/v1/chat/completions"
fi

export OPENCLAW_MODEL="${OPENCLAW_MODEL:-anthropic/claude-sonnet-4-6}"
export WHISPER_MODEL="${WHISPER_MODEL:-tiny}"
export TTS_ENGINE="${TTS_ENGINE:-edge}"
export SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
export PORT="${PORT:-7860}"

# CLI flags sobrescrevem tudo
[ -n "$CLI_GATEWAY_URL" ] && export OPENCLAW_GATEWAY_URL="$CLI_GATEWAY_URL"
[ -n "$CLI_MODEL" ] && export OPENCLAW_MODEL="$CLI_MODEL"
[ -n "$CLI_WHISPER" ] && export WHISPER_MODEL="$CLI_WHISPER"
[ -n "$CLI_HOST" ] && export SERVER_HOST="$CLI_HOST"
[ -n "$CLI_PORT" ] && export PORT="$CLI_PORT"

# ─── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  OpenClaw Voice Assistant"
echo "═══════════════════════════════════════"
echo "  Gateway: $OPENCLAW_GATEWAY_URL"
echo "  Modelo:  $OPENCLAW_MODEL"
echo "  Whisper: $WHISPER_MODEL"
echo "  TTS:     $TTS_ENGINE"
echo "  URL:     http://${SERVER_HOST}:${PORT}"
echo "═══════════════════════════════════════"
echo ""

# ─── Abrir browser (com delay de 2s, em background) ──────────────────────────
URL="http://${SERVER_HOST}:${PORT}"
if [[ "$OSTYPE" == "darwin"* ]]; then
    (sleep 2 && open "$URL") &
elif command -v xdg-open &>/dev/null; then
    (sleep 2 && xdg-open "$URL") &
fi

# ─── Rodar server ────────────────────────────────────────────────────────────
python server_ws.py
