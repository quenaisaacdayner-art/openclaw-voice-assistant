#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# OpenClaw Voice Assistant — Setup automático
# Roda: bash setup.sh
# Detecta OS, instala Python se necessário, cria venv, instala deps
# ═══════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()   { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

echo ""
echo "═══════════════════════════════════════════════"
echo "  OpenClaw Voice Assistant — Setup"
echo "═══════════════════════════════════════════════"
echo ""

# ─── 1. Detectar OS ──────────────────────────────────────────
OS="unknown"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS="$ID"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
fi

log "OS detectado: $OS ($OSTYPE)"

# ─── 2. Verificar/Instalar Python 3.10+ ─────────────────────
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
    warn "Python 3.10+ não encontrado. Instalando..."

    case "$OS" in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv
            ;;
        fedora|rhel|centos)
            dnf install -y python3 python3-pip
            ;;
        arch|manjaro)
            pacman -Sy --noconfirm python python-pip
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install python@3.12
            else
                fail "Instale Homebrew (https://brew.sh) ou Python 3.10+ manualmente"
            fi
            ;;
        *)
            fail "OS não reconhecido ($OS). Instale Python 3.10+ manualmente e rode novamente."
            ;;
    esac

    # Re-detectar após instalação
    for cmd in python3 python; do
        if command -v $cmd &>/dev/null; then
            PYTHON=$cmd
            break
        fi
    done

    [ -z "$PYTHON" ] && fail "Instalação do Python falhou. Instale manualmente."
fi

PY_VERSION=$($PYTHON --version 2>&1)
log "Python encontrado: $PY_VERSION ($PYTHON)"

# ─── 3. Instalar venv se necessário (Ubuntu/Debian) ─────────
if ! $PYTHON -m venv --help &>/dev/null; then
    warn "Módulo venv não encontrado. Instalando..."
    case "$OS" in
        ubuntu|debian)
            apt-get install -y -qq python3-venv
            ;;
        *)
            fail "Módulo venv indisponível. Instale python3-venv manualmente."
            ;;
    esac
fi

# ─── 4. Criar virtualenv ────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -d "venv" ]; then
    log "Virtualenv já existe (venv/)"
else
    log "Criando virtualenv..."
    $PYTHON -m venv venv
    log "Virtualenv criado"
fi

# Ativar
source venv/bin/activate
log "Virtualenv ativado ($(python --version))"

# ─── 5. Instalar dependências ───────────────────────────────
log "Instalando dependências base..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Setup completo!"
echo "═══════════════════════════════════════════════"
echo ""
echo "  Para rodar:"
echo "    source venv/bin/activate"
echo "    bash scripts/run_local.sh      # Cenário 1: tudo local"
echo "    bash scripts/run_vps.sh        # Cenário 2: tudo VPS"
echo ""
echo "  Para TTS local (Kokoro/Piper) + mic direto:"
echo "    pip install -r requirements-local.txt"
echo ""
echo "  Docs: README.md"
echo ""
