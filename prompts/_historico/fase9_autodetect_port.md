# Fase 9: Auto-detecção de porta + Check de porta ocupada

> Leia CLAUDE.md, TESTING_LOG.md e TESTING_RESULTS.md antes de começar.

## Contexto

Nos testes dos 3 cenários, o problema #1 foi: a porta do gateway OpenClaw é `19789` na VPS mas os scripts e o código tinham `18789` hardcoded. Tivemos que configurar manualmente.

O código Python (`core/config.py`) já auto-detecta o **token** de `~/.openclaw/openclaw.json` (função `load_token()`), mas a **porta/URL do gateway** ainda está hardcoded como `18789`.

Além disso, ao trocar de cenário, o processo anterior fica rodando na porta 7860, impedindo o novo server de subir.

## Objetivo

Duas mudanças. NÃO mudar lógica de conversação, NÃO mudar interface.

---

## Tarefa 1: Auto-detecção de porta em `core/config.py`

Atualmente:
```python
GATEWAY_URL = os.environ.get(
    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions"
)
```

**Mudar para:** Se `OPENCLAW_GATEWAY_URL` não estiver no env, ler a porta de `~/.openclaw/openclaw.json` (campo `gateway.port`). Se o arquivo não existir ou não tiver o campo, usar `18789` como fallback.

Referência: seguir o mesmo padrão de `load_token()` que já existe no mesmo arquivo — abrir o JSON, extrair o valor, fallback se não encontrar.

Resultado esperado:
- VPS com porta 19789 → funciona sem configurar nada
- Laptop com porta 18789 → funciona igual (fallback)
- Env var `OPENCLAW_GATEWAY_URL` definida → usa a env var (prioridade máxima, não lê arquivo)

---

## Tarefa 2: Check de porta ocupada nos scripts bash

Nos 6 scripts de cenário (`scripts/run_local.sh`, `run_vps.sh`, `run_local_remote_gateway.sh` + os `.ps1`), adicionar check **antes** de iniciar o server:

### Bash (`.sh`):
```bash
# Matar processo anterior na porta 7860 (se existir)
if command -v lsof &>/dev/null; then
    OLD_PID=$(lsof -ti:7860 2>/dev/null)
    if [ -n "$OLD_PID" ]; then
        echo "⚠️  Matando processo anterior na porta 7860 (PID: $OLD_PID)"
        kill $OLD_PID 2>/dev/null
        sleep 1
    fi
fi
```

### PowerShell (`.ps1`):
```powershell
# Matar processo anterior na porta 7860 (se existir)
$oldProc = Get-NetTCPConnection -LocalPort 7860 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($oldProc) {
    Write-Host "⚠️  Matando processo anterior na porta 7860 (PID: $($oldProc.OwningProcess))"
    Stop-Process -Id $oldProc.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
```

Colocar esse bloco ANTES do `python server_ws.py` (ou `python voice_assistant_app.py`), depois do bloco de echo/Write-Host com info do cenário.

---

## Tarefa 3: Corrigir teste pré-existente (bonus)

O teste `test_default_tts_engine` falha porque o env tem `TTS_ENGINE=edge` mas o teste espera `"piper"`.

- Verificar em `tests/` qual teste é esse
- Se o teste checa o DEFAULT do config.py, o default correto é `"piper"` (ver config.py: `TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper")`)
- O teste provavelmente precisa limpar a env var antes de checar o default, OU o script de run está setando `TTS_ENGINE=edge` globalmente
- Fix: o teste deve usar `monkeypatch.delenv("TTS_ENGINE", raising=False)` antes de importar/recarregar o config

---

## Restrições

- **NÃO alterar:** lógica de conversação, barge-in, streaming, interface HTML, llm.py, tts.py, stt.py
- **NÃO alterar:** server_ws.py (já foi modificado na fase 8)
- **Arquivos a modificar:** `core/config.py` (Tarefa 1), `scripts/run_*.sh` e `scripts/run_*.ps1` (Tarefa 2), teste relevante (Tarefa 3)
- Manter compatibilidade com os 3 cenários

## Testes

1. `pytest` — todos devem passar (incluindo o que falhava antes, se Tarefa 3 feita)
2. Verificar que sem env var `OPENCLAW_GATEWAY_URL`, o server detecta a porta correta de `openclaw.json`

## Entrega

- Criar `auditoria/fase9.md` com diff e resultados dos testes
