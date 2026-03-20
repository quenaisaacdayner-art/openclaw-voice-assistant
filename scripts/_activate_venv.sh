#!/bin/bash
# Auto-ativa virtualenv. Se não existe, roda setup.sh primeiro.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "⚠️  Virtualenv não encontrado. Rodando setup.sh..."
    bash "$PROJECT_DIR/setup.sh"
fi

source "$PROJECT_DIR/venv/bin/activate" 2>/dev/null || {
    echo "❌ Falha ao ativar virtualenv. Rode: bash setup.sh"
    exit 1
}

cd "$PROJECT_DIR"
