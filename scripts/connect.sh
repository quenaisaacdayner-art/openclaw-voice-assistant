#!/bin/bash
# Tunnel SSH para conectar ao gateway OpenClaw na VPS
# Uso: bash scripts/connect.sh [porta] [usuario@host]
ssh -N -L ${1:-19789}:127.0.0.1:${1:-19789} ${2:-root@31.97.171.12} &
SSH_PID=$!
trap "kill $SSH_PID 2>/dev/null" EXIT
python voice_assistant_app.py --gateway http://127.0.0.1:${1:-19789}/v1/chat/completions
