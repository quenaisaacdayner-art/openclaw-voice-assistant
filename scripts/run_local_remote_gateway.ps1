# Cenário 3: Voice app local → OpenClaw na VPS
# Auto-detecta porta do gateway OpenClaw
if (-not $env:OPENCLAW_GATEWAY_URL) {
    try {
        $clawConfig = Get-Content "$HOME\.openclaw\openclaw.json" -Raw | ConvertFrom-Json
        $port = $clawConfig.gateway.port
    } catch { $port = 18789 }
    $env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:${port}/v1/chat/completions"
}
if (-not $env:OPENCLAW_MODEL) { $env:OPENCLAW_MODEL = "anthropic/claude-sonnet-4-6" }
if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = "tiny" }
if (-not $env:TTS_ENGINE) { $env:TTS_ENGINE = "edge" }
$env:SERVER_HOST = "127.0.0.1"

Write-Host "🚀 Cenário: LOCAL → VPS (voice app local, OpenClaw remoto)"
Write-Host "⚠️  Tunnel SSH necessário: ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>"

# Matar processo anterior na porta 7860 (se existir)
$oldProc = Get-NetTCPConnection -LocalPort 7860 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($oldProc) {
    Write-Host "⚠️  Matando processo anterior na porta 7860 (PID: $($oldProc.OwningProcess))"
    Stop-Process -Id $oldProc.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

if (-not $env:APP_MODE) { $env:APP_MODE = "websocket" }

if ($env:APP_MODE -eq "gradio") {
    Write-Host "📻 Modo: Gradio (fallback)"
    python voice_assistant_app.py
} else {
    Write-Host "🔌 Modo: WebSocket S2S"
    python server_ws.py
}
