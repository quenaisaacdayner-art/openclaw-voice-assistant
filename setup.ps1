# OpenClaw Voice Assistant — Auto-setup (called by index.ts plugin)
# Creates venv + installs Python dependencies
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# 1. Find Python 3.10+
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
    Write-Error "Python 3.10+ not found. Install from https://python.org"
    exit 1
}

Write-Host "Python: $(& $py --version 2>&1)"

# 2. Create venv
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtualenv..."
    & $py -m venv venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Failed to create venv"; exit 1 }
}

# 3. Install dependencies
& "$scriptDir\venv\Scripts\Activate.ps1"
pip install --upgrade pip -q
pip install -r requirements.txt -q

Write-Host "Setup complete"
