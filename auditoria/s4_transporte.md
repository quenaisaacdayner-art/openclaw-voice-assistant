# Auditoria S4: Transporte & Conexão

> Data: 2026-03-23
> Prompt: `prompts/s4_transporte/s4_completo.md`
> Executor: Claude Code (~2min 4s)
> Auditor: OpenClaw Principal (Opus 4)

---

## Resultado geral: ✅ APROVADO

87 testes passaram, 0 falharam. Todas as 3 features implementadas conforme o prompt.

---

## Feature 1: Backoff Exponencial — ✅

### Verificado em `static/index.html`:
- [x] Variáveis criadas: `reconnectDelay`, `RECONNECT_MIN` (3000), `RECONNECT_MAX` (30000), `RECONNECT_FACTOR` (2), `reconnectAttempts` — **linhas 541-545**
- [x] `ws.onclose`: incrementa `reconnectAttempts`, calcula delay com `Math.pow`, mostra tentativa + delay na UI — **linhas 654-659**
- [x] `ws.onopen`: reset de `reconnectAttempts = 0` e `reconnectDelay = RECONNECT_MIN` — **linhas 628-629**

### Observação:
- Sequência de delays: 3s → 6s → 12s → 24s → 30s → 30s... (correto, cap em 30s)

---

## Feature 2: Keep-Alive (Ping/Pong) — ✅

### Verificado em `static/index.html`:
- [x] Variáveis: `keepAliveTimer`, `pongReceived` (true), `KEEPALIVE_INTERVAL` (30000) — **linhas 548-550**
- [x] `startKeepAlive()`: setInterval 30s, checa `pongReceived`, fecha WS se sem resposta — **linhas 583-597**
- [x] `stopKeepAlive()`: clearInterval + null — **linhas 600-604**
- [x] `ws.onopen`: chama `startKeepAlive()` — **linha 650**
- [x] `ws.onclose`: chama `stopKeepAlive()` — **linha 654**
- [x] `disconnect()`: chama `stopKeepAlive()` — **linha 986**
- [x] Handler `pong`: seta `pongReceived = true`, loga latência — **linha 699**

### Verificado em `server_ws.py`:
- [x] Handler `ping`: responde com `pong` + timestamp — **linhas 356-358**
- [x] Posicionado ANTES de `vad_event` (processamento rápido) — correto

### Observação:
- Fluxo de detecção de morte: ping enviado → 30s sem pong → `ws.close()` → `onclose` → backoff reconecta
- Tempo máximo pra detectar conexão morta: ~60s (30s intervalo + 30s timeout). Aceitável.

---

## Feature 3: Session Persistence — ✅

### Verificado em `static/index.html`:
- [x] Variáveis: `chatMessages` (array), `MAX_RESTORE` (20), `hasConnectedBefore` (false) — **linhas 553-555**
- [x] `trimChatMessages()`: mantém últimas 20 mensagens — **linhas 608-611**
- [x] Push de `user` message no handler `transcript` + `trimChatMessages()` — **linhas 711-712**
- [x] Push de `assistant` message quando `data.done === true` + `trimChatMessages()` — **linhas 718-719**
- [x] `ws.onopen`: detecta reconexão via `hasConnectedBefore`, envia `restore_history` — **linhas 624-648**
- [x] `disconnect()`: limpa `chatMessages = []` e `hasConnectedBefore = false` — **linhas 1028-1029**
- [x] Handler `session_restored`: log de confirmação — presente

### Verificado em `server_ws.py`:
- [x] Handler `restore_history`: valida lista, filtra roles, limita 20 msgs, trunca 5000 chars/msg — **linhas 360-380**
- [x] Responde com `session_restored` + count — **linhas 376-379**
- [x] `continue` após processar (não cai nos handlers de áudio) — **linha 380**

### Validação de segurança:
- [x] Limite de mensagens: 20 (server-side) ✅
- [x] Limite de chars por mensagem: 5000 (server-side) ✅
- [x] Validação de roles: só aceita "user" e "assistant" ✅
- [x] Validação de tipo: checa `isinstance(msg, dict)` e `isinstance(content, str)` ✅
- [x] Mensagens vazias: rejeitadas via `msg["content"].strip()` ✅

---

## Testes automatizados

- 87 passed, 0 failed (`python -m pytest tests/ -v`)
- Features de transporte são frontend/WS → testes manuais são o guardrail principal
- Testes existentes de STT/TTS/LLM/CLI não foram afetados (esperado — zero mudanças no core/)

---

## Testes manuais (recomendados)

| # | Teste | Como |
|---|-------|------|
| 1 | Backoff crescente | Parar server → ver delays no console (3→6→12→24→30) |
| 2 | Backoff reset | Reiniciar server → reconecta → próxima queda volta pra 3s |
| 3 | Keep-alive ping | Conectar → esperar 30s → ver "[KA] Pong: XXms" no console |
| 4 | Keep-alive morte | Matar server sem fechar limpo → browser reconecta em ~60s |
| 5 | Session restore | Conversar → matar server → reiniciar → perguntar "o que eu disse?" |
| 6 | Disconnect limpo | Clicar Encerrar → reconectar → histórico zerado |

> Dayner confirmou que testou alguns e estavam com sucesso.

---

## Arquivos modificados

| Arquivo | Mudanças | Linhas afetadas (aprox) |
|---------|----------|------------------------|
| `static/index.html` | Variáveis, funções keepalive/trim, onopen/onclose/onmessage/disconnect | ~80 linhas adicionadas |
| `server_ws.py` | Handlers `ping` e `restore_history` no receive loop | ~25 linhas adicionadas |

## Pendente

- [ ] Commit: `feat: S4 transporte — backoff, keep-alive, session persistence`
