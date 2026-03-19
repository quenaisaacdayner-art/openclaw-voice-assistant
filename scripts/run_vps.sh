#!/bin/bash
# Cenário 2: Tudo na VPS (voice app + OpenClaw na VPS)
# Requisitos: OpenClaw Gateway rodando na VPS em :18789
# Acesso: ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>

export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1/chat/completions"
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

APP_MODE="${APP_MODE:-websocket}"

if [ "$APP_MODE" = "gradio" ]; then
    echo "📻 Modo: Gradio (fallback)"
    python voice_assistant_app.py
else
    echo "🔌 Modo: WebSocket S2S"
    python server_ws.py
fi
