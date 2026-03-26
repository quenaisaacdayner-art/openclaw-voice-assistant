#!/bin/bash
# OpenClaw Voice Assistant — Auto-setup (called by index.ts plugin)
# Creates venv + installs Python dependencies
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Find Python 3.10+
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        ver=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo $ver | cut -d. -f1)
        minor=$(echo $ver | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON=$cmd
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    # Try installing on Debian/Ubuntu
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            ubuntu|debian)
                apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv
                ;;
        esac
    fi
    for cmd in python3 python; do
        if command -v $cmd &>/dev/null; then PYTHON=$cmd; break; fi
    done
    [ -z "$PYTHON" ] && { echo "❌ Python 3.10+ not found"; exit 1; }
fi

echo "✅ Python: $($PYTHON --version)"

# 2. Ensure venv module exists
if ! $PYTHON -m venv --help &>/dev/null; then
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        [ "$ID" = "ubuntu" ] || [ "$ID" = "debian" ] && apt-get install -y -qq python3-venv
    fi
fi

# 3. Create venv
if [ ! -d "venv" ]; then
    echo "Creating virtualenv..."
    $PYTHON -m venv venv
fi

# 4. Install dependencies
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "✅ Setup complete"
