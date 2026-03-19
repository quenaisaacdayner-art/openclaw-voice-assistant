# Cenário 3: Voice app local → OpenClaw na VPS
$env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
if (-not $env:OPENCLAW_MODEL) { $env:OPENCLAW_MODEL = "anthropic/claude-sonnet-4-6" }
if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = "tiny" }
if (-not $env:TTS_ENGINE) { $env:TTS_ENGINE = "edge" }
$env:SERVER_HOST = "127.0.0.1"

Write-Host "🚀 Cenário: LOCAL → VPS (voice app local, OpenClaw remoto)"
Write-Host "⚠️  Tunnel SSH necessário: ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>"

python voice_assistant_app.py
