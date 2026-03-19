#!/bin/bash
# Cenário 1: Tudo local (laptop com OpenClaw)
# Requisitos: OpenClaw Gateway rodando local em :18789

export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1/chat/completions"
export OPENCLAW_MODEL="${OPENCLAW_MODEL:-anthropic/claude-sonnet-4-6}"
export WHISPER_MODEL="${WHISPER_MODEL:-tiny}"
export TTS_ENGINE="${TTS_ENGINE:-edge}"
export SERVER_HOST="127.0.0.1"

echo "🚀 Cenário: LOCAL (tudo no laptop)"
echo "   Gateway: $OPENCLAW_GATEWAY_URL"
echo "   Modelo: $OPENCLAW_MODEL"
echo "   Whisper: $WHISPER_MODEL"
echo "   TTS: $TTS_ENGINE"
echo ""

APP_MODE="${APP_MODE:-websocket}"

if [ "$APP_MODE" = "gradio" ]; then
    echo "📻 Modo: Gradio (fallback)"
    python voice_assistant_app.py
else
    echo "🔌 Modo: WebSocket S2S"
    python server_ws.py
fi
