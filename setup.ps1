# OpenClaw Voice Assistant — Setup (Windows PowerShell)
# Roda: .\setup.ps1

$ErrorActionPreference = "Stop"

function Log($msg) { Write-Host "✅ $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "⚠️  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "❌ $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "═══════════════════════════════════════════════"
Write-Host "  OpenClaw Voice Assistant — Setup (Windows)"
Write-Host "═══════════════════════════════════════════════"
Write-Host ""

# 1. Verificar Python 3.10+
$py = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $parts = $ver.Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $py = $cmd
                break
            }
        }
    } catch {}
}

if (-not $py) {
    Fail "Python 3.10+ não encontrado. Instale de https://python.org/downloads e marque 'Add to PATH'"
}

$pyVersion = & $py --version 2>&1
Log "Python encontrado: $pyVersion ($py)"

# 2. Criar virtualenv
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (Test-Path "venv") {
    Log "Virtualenv já existe (venv\)"
} else {
    Log "Criando virtualenv..."
    & $py -m venv venv
    if ($LASTEXITCODE -ne 0) { Fail "Falha ao criar virtualenv" }
    Log "Virtualenv criado"
}

# 3. Ativar
$activateScript = Join-Path $scriptDir "venv\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Fail "Script de ativação não encontrado em venv\Scripts\Activate.ps1"
}
& $activateScript
Log "Virtualenv ativado"

# 4. Instalar dependências
Log "Instalando dependências base..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

Write-Host ""
Write-Host "═══════════════════════════════════════════════"
Write-Host "  ✅ Setup completo!"
Write-Host "═══════════════════════════════════════════════"
Write-Host ""
Write-Host "  Para rodar:"
Write-Host "    .\venv\Scripts\Activate.ps1"
Write-Host "    .\scripts\run_local.ps1         # Cenário 1: tudo local"
Write-Host ""
Write-Host "  Para TTS local (Kokoro/Piper) + mic direto:"
Write-Host "    pip install -r requirements-local.txt"
Write-Host ""
Write-Host "  Docs: README.md"
Write-Host ""
