#!/bin/bash
# Cenário 3: Voice app local → OpenClaw na VPS
# Requisitos: Tunnel SSH para gateway da VPS
# Setup: ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>

source "$(dirname "$0")/_activate_venv.sh"

export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1/chat/completions"
export OPENCLAW_MODEL="${OPENCLAW_MODEL:-anthropic/claude-sonnet-4-6}"
export WHISPER_MODEL="${WHISPER_MODEL:-tiny}"
export TTS_ENGINE="${TTS_ENGINE:-edge}"
export SERVER_HOST="127.0.0.1"

echo "🚀 Cenário: LOCAL → VPS (voice app local, OpenClaw remoto)"
echo "   Gateway: $OPENCLAW_GATEWAY_URL (via SSH tunnel)"
echo "   Modelo: $OPENCLAW_MODEL"
echo "   Whisper: $WHISPER_MODEL"
echo "   TTS: $TTS_ENGINE"
echo ""
echo "⚠️  Certifique-se de que o tunnel SSH está ativo:"
echo "    ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>"
echo ""

APP_MODE="${APP_MODE:-websocket}"

if [ "$APP_MODE" = "gradio" ]; then
    echo "📻 Modo: Gradio (fallback)"
    python voice_assistant_app.py
else
    echo "🔌 Modo: WebSocket S2S"
    python server_ws.py
fi
