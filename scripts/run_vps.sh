#!/bin/bash
# Cenário 2: Tudo na VPS (voice app + OpenClaw na VPS)
# Requisitos: OpenClaw Gateway rodando na VPS
# Acesso: ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>

source "$(dirname "$0")/_activate_venv.sh"

# Auto-detecta porta do gateway OpenClaw de ~/.openclaw/openclaw.json
if [ -z "$OPENCLAW_GATEWAY_URL" ]; then
    OPENCLAW_PORT=$(python3 -c "import json; print(json.load(open('$HOME/.openclaw/openclaw.json'))['gateway']['port'])" 2>/dev/null || echo "18789")
    export OPENCLAW_GATEWAY_URL="http://127.0.0.1:${OPENCLAW_PORT}/v1/chat/completions"
fi
export OPENCLAW_MODEL="${OPENCLAW_MODEL:-anthropic/claude-sonnet-4-6}"
export WHISPER_MODEL="${WHISPER_MODEL:-tiny}"
export TTS_ENGINE="${TTS_ENGINE:-edge}"
export SERVER_HOST="0.0.0.0"

echo "🚀 Cenário: VPS (tudo remoto)"
echo "   Gateway: $OPENCLAW_GATEWAY_URL"
echo "   Modelo: $OPENCLAW_MODEL"
echo "   Whisper: $WHISPER_MODEL"
echo "   TTS: $TTS_ENGINE"
echo ""
echo "📡 Acesse via: ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>"
echo "   Depois abra: http://127.0.0.1:7860"
echo ""

# Matar processo anterior na porta 7860 (se existir)
if command -v lsof &>/dev/null; then
    OLD_PID=$(lsof -ti:7860 2>/dev/null)
    if [ -n "$OLD_PID" ]; then
        echo "⚠️  Matando processo anterior na porta 7860 (PID: $OLD_PID)"
        kill $OLD_PID 2>/dev/null
        sleep 1
    fi
fi

APP_MODE="${APP_MODE:-websocket}"

if [ "$APP_MODE" = "gradio" ]; then
    echo "📻 Modo: Gradio (fallback)"
    python voice_assistant_app.py
else
    echo "🔌 Modo: WebSocket S2S"
    python server_ws.py
fi
