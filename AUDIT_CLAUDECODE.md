# AUDIT_CLAUDECODE.md — Auditoria do bug do server crash

**Data:** 2026-03-26
**Auditor:** Claude Code (Opus 4.6)

---

## 1. O que encontrei

### Bug principal: server_ws.py deletado
- `server_ws.py` (560 linhas, app FastAPI principal) foi removido no commit `0ad2a14`
- `core/__main__.py` linha 129 faz `importlib.import_module("server_ws")` — crashava com `ModuleNotFoundError` em <0.2s
- O arquivo já estava restaurado no working tree via `git checkout 0ad2a14~1 -- server_ws.py` (feito pelo OpenClaw Opus)

### Compatibilidade dos imports: OK
Verifiquei todos os imports de `server_ws.py` contra o estado atual de `core/`:
- `core.config`: `load_token`, `GATEWAY_URL`, `MODEL`, `WHISPER_MODEL_SIZE` — todos existem
- `core.stt`: `transcribe_audio`, `init_stt`, `get_current_model` — todos existem
- `core.tts`: `init_tts`, `warmup_tts`, `generate_tts`, `get_engine`, `get_tts_info`, `get_available_voices`, `get_current_voice`, `get_speed` — todos existem
- `core.llm`: `ask_openclaw_stream`, `ask_openclaw`, `_find_sentence_end`, `_session` — todos existem
- `core.history`: `build_api_history`, `MAX_HISTORY` — todos existem
- Imports inline (`set_whisper_model`, `set_voice`, `set_speed`) — todos existem

**Nenhuma incompatibilidade encontrada.** O `server_ws.py` restaurado funciona com o `core/` atual sem alterações.

### waitForServer mascarava o crash
`waitForServer()` em `index.ts` fazia polling HTTP por 30s sem verificar se o processo Python já morreu. Quando o processo crashava em <0.2s, o usuário via "timeout after 30s" em vez do erro real (`ModuleNotFoundError`).

### Testes órfãos
`tests/test_cli.py` (293 linhas) e `tests/test_cli_extended.py` (238 linhas) importavam `voice_assistant_cli` — módulo deletado no mesmo commit `0ad2a14`. Causavam `ModuleNotFoundError` no collection do pytest.

### CLAUDE.md incorreto
A seção "Dependências entre arquivos" dizia que `server_ws.py` "NÃO EXISTE MAIS" e que "o servidor é core/ inteiro via FastAPI". Falso — `server_ws.py` é o app FastAPI principal e `core/` são módulos auxiliares.

---

## 2. O que corrigi

### a) waitForServer — detecção de crash precoce (index.ts)
**Antes:** polling HTTP por 30s, ignora se processo morreu.
**Depois:** race entre 3 condições:
1. Servidor respondeu (HTTP 200 ou 403) → resolve
2. Processo Python morreu (exit event) → reject com stderr capturado
3. Timeout 30s → reject

Agora, se `server_ws.py` não existir, o erro aparece em <1s com o traceback real:
```
Voice assistant failed to start. Python process exited (code 1) before server was ready:
ModuleNotFoundError: No module named 'server_ws'
```

### b) CLAUDE.md atualizado
- Adicionou `server_ws.py` na seção "Estrutura do código"
- Corrigiu seção "Dependências entre arquivos" com grafo real de imports
- Corrigiu descrição de `core/` de "Servidor Python" para "Módulos Python auxiliares"

### c) Testes órfãos removidos
Deletei `tests/test_cli.py` e `tests/test_cli_extended.py` que testavam `voice_assistant_cli` (módulo deletado, não volta).

---

## 3. Avaliação das propostas do OpenClaw Opus

### Proposta: "fazer waitForServer aceitar flag/promise que resolve quando processo morre, e race"
**Concordo.** Implementei exatamente essa abordagem. `waitForServer` agora recebe `proc` e `stderrChunks[]`, faz race entre servidor pronto / processo morto / timeout. Simples e robusto.

### Proposta: "avaliar se os 3 commits devem ser mantidos ou revertidos"
**Manter todos os 3:**
- **`beb9ee9` (separação setup/start):** Boa UX. Usuário não quer `pip install` toda vez que roda `/ova start`. Motivação errada, resultado bom.
- **`6605708` (timeout 120s):** O timeout voltou a 30s na nova `waitForServer` (default do parâmetro). A mudança é efetivamente revertida, mas sem precisar reverter o commit.
- **`0f82277` (setup.sh/setup.ps1):** Válido — os scripts são necessários pro `/ova setup`.

---

## 4. Como o fluxo funciona agora

```
Usuário: /ova setup
  → index.ts roda setup.sh/setup.ps1 → cria venv/ e instala deps
  → Retorna "Setup complete"

Usuário: /ova start
  → index.ts verifica venv/ existe
  → Spawna: venv/python -m core --host 0.0.0.0 --port 7860 --no-browser
  → core/__main__.py seta env vars, importa server_ws via importlib
  → server_ws.py cria app FastAPI, inicializa STT/TTS/LLM, monta rotas
  → uvicorn.run(server_ws.app, host, port)
  → index.ts faz race: servidor pronto vs processo morreu vs timeout 30s
  → Se servidor respondeu: abre tunnel Cloudflare (se não-localhost) e retorna URL
  → Se processo morreu: retorna stderr com traceback real

Usuário: /ova stop
  → Mata processo Python + tunnel Cloudflare

Usuário: /ova status
  → Mostra PID, porta, uptime, URL do tunnel
```

---

## 5. Resultado dos testes

```
65 passed in 7.15s
```

Todos os 65 testes passam. Os 2 testes órfãos foram removidos (referenciavam módulo deletado).

Nota: o README/CLAUDE.md mencionam "118 testes". Esse número incluía os testes de `voice_assistant_cli` (que tinha ~53 testes). O número real agora é 65.

---

## 6. Pendente

1. **Commitar `server_ws.py`** — o arquivo está no working tree mas não está commitado. Precisa de `git add server_ws.py` + commit.
2. **Testar na VPS** — as mudanças no `index.ts` precisam ser deployadas e testadas no Ubuntu 24.04 / Python 3.12.3. Não tenho acesso SSH.
3. **Atualizar contagem de testes** — CLAUDE.md diz "118 testes" mas são 65 agora. Menor prioridade.
