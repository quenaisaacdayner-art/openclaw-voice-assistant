# Cenário 1: Tudo local (laptop com OpenClaw)
$env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
if (-not $env:OPENCLAW_MODEL) { $env:OPENCLAW_MODEL = "anthropic/claude-sonnet-4-6" }
if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = "tiny" }
if (-not $env:TTS_ENGINE) { $env:TTS_ENGINE = "edge" }
$env:SERVER_HOST = "127.0.0.1"

Write-Host "🚀 Cenário: LOCAL (tudo no laptop)"
Write-Host "   Gateway: $env:OPENCLAW_GATEWAY_URL"
Write-Host "   Modelo: $env:OPENCLAW_MODEL"
Write-Host "   Whisper: $env:WHISPER_MODEL"
Write-Host "   TTS: $env:TTS_ENGINE"

if (-not $env:APP_MODE) { $env:APP_MODE = "websocket" }

if ($env:APP_MODE -eq "gradio") {
    Write-Host "📻 Modo: Gradio (fallback)"
    python voice_assistant_app.py
} else {
    Write-Host "🔌 Modo: WebSocket S2S"
    python server_ws.py
}
