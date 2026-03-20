# Registro — Fase 9: Auto-detecção de porta + Check de porta ocupada

> Executada: 20/03/2026
> Objetivo: Auto-detectar porta do gateway de openclaw.json + matar processo anterior na porta 7860

## Resultado dos Testes

- **227 passed, 18 skipped, 0 failed**
- Fix do teste `test_default_tts_engine` (antes falhava por env var TTS_ENGINE=edge)
- Sem regressão

## Arquivos Modificados

| Arquivo | O que mudou |
|---------|-------------|
| `core/config.py` | `GATEWAY_URL` agora auto-detecta porta de `~/.openclaw/openclaw.json` (campo `gateway.port`), com fallback pra 18789 |
| `scripts/run_local.sh` | Check de porta 7860 ocupada antes de iniciar |
| `scripts/run_vps.sh` | Check de porta 7860 ocupada antes de iniciar |
| `scripts/run_local_remote_gateway.sh` | Check de porta 7860 ocupada antes de iniciar |
| `scripts/run_local.ps1` | Check de porta 7860 ocupada antes de iniciar |
| `scripts/run_vps.ps1` | Check de porta 7860 ocupada antes de iniciar |
| `scripts/run_local_remote_gateway.ps1` | Check de porta 7860 ocupada antes de iniciar |
| `tests/test_cli.py` | Fix `test_default_tts_engine` com `monkeypatch.delenv` + `importlib.reload`; `test_default_gateway_url` agora checa apenas sufixo (compatível com auto-detecção) |

## Arquivos Criados

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `auditoria/fase9.md` | ~50 | Este registro |

## O que foi feito

### Tarefa 1: Auto-detecção de porta em `core/config.py`

Nova função `_detect_gateway_url()` que segue o padrão de `load_token()`:
1. Se `OPENCLAW_GATEWAY_URL` está no env → usa direto (prioridade máxima)
2. Senão, lê `~/.openclaw/openclaw.json` → campo `gateway.port`
3. Fallback: `http://127.0.0.1:18789/v1/chat/completions`

### Tarefa 2: Check de porta ocupada nos scripts

Adicionado bloco antes do `python server_ws.py` em todos os 6 scripts:
- **Bash (.sh):** `lsof -ti:7860` → `kill` se encontrar processo
- **PowerShell (.ps1):** `Get-NetTCPConnection -LocalPort 7860` → `Stop-Process` se encontrar

### Tarefa 3: Fix do teste pre-existente

- `test_default_tts_engine`: agora usa `monkeypatch.delenv("TTS_ENGINE")` + `importlib.reload(config)` pra testar o default real
- `test_default_gateway_url`: removido check de `"18789"` (agora auto-detecta da máquina), mantido check do sufixo `/v1/chat/completions`

## Diff total

```
 core/config.py                         | 15 +++++++++++-
 scripts/run_local.sh                   |  9 ++++++++
 scripts/run_vps.sh                     |  9 ++++++++
 scripts/run_local_remote_gateway.sh    |  9 ++++++++
 scripts/run_local.ps1                  |  7 ++++++
 scripts/run_vps.ps1                    |  7 ++++++
 scripts/run_local_remote_gateway.ps1   |  7 ++++++
 tests/test_cli.py                      |  8 ++++---
 auditoria/fase9.md                     | ~50 +++++++++
 9 files changed, ~120 insertions(+), ~5 deletions(-)
```

## Auditoria — OpenClaw Principal (20/03 17:15 BRT)

### Tarefa 1: Auto-detecção de porta ✅
- `_detect_gateway_url()` segue o padrão exato de `load_token()` — correto
- Prioridade: env var > openclaw.json > fallback 18789 — correto
- `TypeError` no except é defensivo (caso `cfg["gateway"]` retorne None) — bom toque
- Abre o JSON 2x no startup (1x porta, 1x token) — aceitável, é startup

### Tarefa 2: Check de porta ocupada ✅
- 6 scripts atualizados (3 .sh + 3 .ps1) — verificado todos
- Bloco posicionado DEPOIS dos echos de info e ANTES do python — correto
- Scripts .sh também mantêm auto-detecção de porta no bash (redundante com config.py mas útil pros echos)

### Tarefa 3: Fix do teste ✅
- `monkeypatch.delenv("TTS_ENGINE")` + `importlib.reload(config)` — correto
- Reload final restaura estado — correto
- `test_default_gateway_url` agora checa só sufixo `/v1/chat/completions` — adaptação necessária e correta

### Veredito: ✅ APROVADO — Zero problemas encontrados
