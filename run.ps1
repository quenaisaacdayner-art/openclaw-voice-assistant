# OpenClaw Voice Assistant — Script "faz tudo" (Windows PowerShell)
# Uso: .\run.ps1 [-ServerHost IP] [-Port NUM] [-GatewayUrl URL] [-Model MODELO] [-Whisper tiny|small]

param(
    [string]$ServerHost,
    [int]$Port,
    [string]$GatewayUrl,
    [string]$Model,
    [ValidateSet("tiny", "small")]
    [string]$Whisper
)

$ErrorActionPreference = "Stop"

# --- Detectar diretorio do script ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# --- Verificar venv ---
if (-not (Test-Path "venv")) {
    Write-Host "Virtualenv nao encontrado. Rodando setup.ps1..."
    & .\setup.ps1
}

& .\venv\Scripts\Activate.ps1

# --- Matar processo na porta ---
$targetPort = if ($Port) { $Port } elseif ($env:PORT) { [int]$env:PORT } else { 7860 }
$oldProc = Get-NetTCPConnection -LocalPort $targetPort -ErrorAction SilentlyContinue | Select-Object -First 1
if ($oldProc) {
    Write-Host "Matando processo anterior na porta $targetPort (PID: $($oldProc.OwningProcess))"
    Stop-Process -Id $oldProc.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# --- Configurar variaveis de ambiente ---
# Auto-detectar gateway URL de ~/.openclaw/openclaw.json
if (-not $env:OPENCLAW_GATEWAY_URL) {
    try {
        $clawConfig = Get-Content "$HOME\.openclaw\openclaw.json" -Raw | ConvertFrom-Json
        $clawPort = $clawConfig.gateway.port
    } catch {
        $clawPort = 18789
    }
    $env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:${clawPort}/v1/chat/completions"
}

if (-not $env:OPENCLAW_MODEL)  { $env:OPENCLAW_MODEL = "anthropic/claude-sonnet-4-6" }
if (-not $env:WHISPER_MODEL)   { $env:WHISPER_MODEL = "tiny" }
if (-not $env:TTS_ENGINE)      { $env:TTS_ENGINE = "edge" }
if (-not $env:SERVER_HOST)     { $env:SERVER_HOST = "127.0.0.1" }
if (-not $env:PORT)            { $env:PORT = "7860" }

# CLI params sobrescrevem tudo
if ($GatewayUrl) { $env:OPENCLAW_GATEWAY_URL = $GatewayUrl }
if ($Model)      { $env:OPENCLAW_MODEL = $Model }
if ($Whisper)    { $env:WHISPER_MODEL = $Whisper }
if ($ServerHost) { $env:SERVER_HOST = $ServerHost }
if ($Port)       { $env:PORT = $Port }

# --- Banner ---
Write-Host ""
Write-Host ("=" * 39)
Write-Host "  OpenClaw Voice Assistant"
Write-Host ("=" * 39)
Write-Host "  Gateway: $env:OPENCLAW_GATEWAY_URL"
Write-Host "  Modelo:  $env:OPENCLAW_MODEL"
Write-Host "  Whisper: $env:WHISPER_MODEL"
Write-Host "  TTS:     $env:TTS_ENGINE"
Write-Host "  URL:     http://$($env:SERVER_HOST):$($env:PORT)"
Write-Host ("=" * 39)
Write-Host ""

# --- Abrir browser (com delay de 2s, em background) ---
$url = "http://$($env:SERVER_HOST):$($env:PORT)"
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process $using:url
} | Out-Null

# --- Rodar server ---
python server_ws.py
