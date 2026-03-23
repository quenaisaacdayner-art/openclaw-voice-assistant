# S4: Transporte & Conexão — PROMPT COMPLETO

> Prompt unificado. Leia e execute TUDO.
> Pré-requisito: S1, S2, S3 já executados
> Arquivos a modificar: `static/index.html`, `server_ws.py`
> NÃO mexer em: `core/`, `voice_assistant_cli.py`

---

## Visão geral

3 features de transporte (resiliência da conexão WebSocket). Implementar TODAS nesta ordem:

1. Backoff exponencial na reconexão
2. Keep-alive (ping/pong) pra detectar conexão morta
3. Session persistence — restaurar histórico após reconexão

---

## FEATURE 1: Backoff Exponencial

### Problema atual

`ws.onclose` reconecta a cada 3 segundos pra sempre. Se o server tá offline, fica tentando 20x/minuto indefinidamente.

### Frontend (`static/index.html`):

Adicionar variáveis de controle (junto das outras variáveis de estado, perto de `let reconnectTimer = null`):

```javascript
let reconnectTimer = null;  // já existe
let reconnectDelay = 3000;  // delay atual (cresce com backoff)
const RECONNECT_MIN = 3000;
const RECONNECT_MAX = 30000;
const RECONNECT_FACTOR = 2;
let reconnectAttempts = 0;
```

Modificar `ws.onclose`:

```javascript
ws.onclose = () => {
    setStatus('disconnected', 'Desconectado');
    reconnectAttempts++;
    reconnectDelay = Math.min(RECONNECT_MIN * Math.pow(RECONNECT_FACTOR, reconnectAttempts - 1), RECONNECT_MAX);
    bottomStatus.textContent = `Reconectando em ${Math.round(reconnectDelay / 1000)}s... (tentativa ${reconnectAttempts})`;
    reconnectTimer = setTimeout(connect, reconnectDelay);
};
```

Modificar `ws.onopen` — adicionar reset do backoff (junto do código existente, NÃO substituir):

```javascript
// Adicionar no INÍCIO do ws.onopen existente:
reconnectAttempts = 0;
reconnectDelay = RECONNECT_MIN;
```

### Backend: nenhuma mudança.

---

## FEATURE 2: Keep-Alive (Ping/Pong)

### Problema atual

Se a conexão morre silenciosamente (WiFi muda, túnel SSH cai), o browser continua mostrando "Conectado" até o usuário tentar falar. Nenhum mecanismo detecta a morte da conexão.

### Frontend (`static/index.html`):

Adicionar variáveis (junto das outras de estado):

```javascript
let keepAliveTimer = null;
let pongReceived = true;
const KEEPALIVE_INTERVAL = 30000; // 30s
const KEEPALIVE_TIMEOUT = 10000;  // 10s pra responder
```

Criar funções de keep-alive:

```javascript
function startKeepAlive() {
    stopKeepAlive();
    pongReceived = true;
    keepAliveTimer = setInterval(() => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        
        if (!pongReceived) {
            // Server não respondeu o último ping — conexão morta
            console.warn('[KA] Pong não recebido — reconectando');
            ws.close(); // vai triggerar onclose → reconnect com backoff
            return;
        }
        
        pongReceived = false;
        ws.send(JSON.stringify({ type: 'ping', t: Date.now() }));
    }, KEEPALIVE_INTERVAL);
}

function stopKeepAlive() {
    if (keepAliveTimer) {
        clearInterval(keepAliveTimer);
        keepAliveTimer = null;
    }
}
```

Modificar `ws.onopen` — adicionar no final:

```javascript
startKeepAlive();
```

Modificar `ws.onclose` — adicionar no início:

```javascript
stopKeepAlive();
```

Modificar `disconnect()` (a função do botão Encerrar) — adicionar junto dos outros cleanups:

```javascript
stopKeepAlive();
```

No handler `ws.onmessage`, dentro do bloco `else` (mensagens JSON), adicionar tratamento do pong:

```javascript
if (data.type === 'pong') {
    pongReceived = true;
    const latency = Date.now() - (data.t || 0);
    console.log(`[KA] Pong: ${latency}ms`);
    // Opcional: mostrar latência na UI se quiser (não obrigatório)
}
```

### Backend (`server_ws.py`):

No main receive loop, dentro do bloco `elif "text" in message`, ANTES dos outros handlers, adicionar:

```python
if data["type"] == "ping":
    await ws.send_json({"type": "pong", "t": data.get("t")})
    continue
```

Importante: colocar ANTES de `if data["type"] == "vad_event"` pra ser processado rápido sem entrar na lógica de áudio.

---

## FEATURE 3: Session Persistence (restaurar histórico após reconexão)

### Problema atual

Quando o WebSocket reconecta (WiFi caiu, server reiniciou), o `chat_history` no server começa vazio. O LLM perde todo o contexto da conversa anterior. A interface mostra as mensagens antigas (são elementos HTML no DOM) mas o server não sabe que elas existem.

### Estratégia

1. Frontend mantém um array `chatMessages` com o histórico da conversa
2. Ao reconectar, frontend envia o histórico pro server via mensagem `restore_history`
3. Server aceita e restaura o `chat_history`
4. Limite: últimas 10 exchanges (20 mensagens = 10 user + 10 assistant) pra não sobrecarregar

### Frontend (`static/index.html`):

Adicionar variável de estado:

```javascript
let chatMessages = []; // [{role: "user", content: "..."}, {role: "assistant", content: "..."}]
const MAX_RESTORE = 20; // máximo de mensagens pra restaurar (10 exchanges)
```

**Capturar mensagens conforme acontecem** — modificar os pontos onde mensagens são adicionadas ao DOM:

Quando recebe transcrição do usuário (no handler `data.type === 'transcript'`), APÓS mostrar no DOM:
```javascript
if (data.text && data.text.trim()) {
    chatMessages.push({ role: 'user', content: data.text.trim() });
}
```

Quando recebe resposta completa do assistente (no handler `data.type === 'text'` quando `data.done === true`), APÓS mostrar no DOM:
```javascript
chatMessages.push({ role: 'assistant', content: data.text });
```

**Manter limite:**
```javascript
// Adicionar como função helper
function trimChatMessages() {
    if (chatMessages.length > MAX_RESTORE) {
        chatMessages = chatMessages.slice(-MAX_RESTORE);
    }
}
```

Chamar `trimChatMessages()` após cada push em `chatMessages`.

**Enviar histórico ao reconectar** — modificar `ws.onopen`:

Após o bloco existente que envia config (whisper_model), adicionar:

```javascript
// Restaurar histórico se reconectando
if (chatMessages.length > 0 && reconnectAttempts === 0) {
    // reconnectAttempts é 0 porque JÁ foi resetado acima
    // Mas precisamos saber se é reconexão ou primeira conexão
    // Solução: checar se chatMessages tem conteúdo
    ws.send(JSON.stringify({
        type: 'restore_history',
        messages: chatMessages
    }));
    console.log(`[SESSION] Histórico restaurado: ${chatMessages.length} mensagens`);
}
```

**Correção**: precisamos distinguir primeira conexão de reconexão. Adicionar flag:

```javascript
let hasConnectedBefore = false; // junto das outras variáveis de estado
```

No `ws.onopen`, ANTES do reset de `reconnectAttempts`:
```javascript
const isReconnect = hasConnectedBefore;
hasConnectedBefore = true;
```

E o envio do histórico fica:
```javascript
if (isReconnect && chatMessages.length > 0) {
    ws.send(JSON.stringify({
        type: 'restore_history',
        messages: chatMessages
    }));
    console.log(`[SESSION] Histórico restaurado: ${chatMessages.length} mensagens`);
}
```

**Limpar histórico no disconnect manual** — na função `disconnect()`:

```javascript
chatMessages = [];
hasConnectedBefore = false;
```

### Backend (`server_ws.py`):

No main receive loop, adicionar handler ANTES dos outros (logo após o handler de `ping`):

```python
elif data["type"] == "restore_history":
    restored = data.get("messages", [])
    if isinstance(restored, list):
        # Validar e limitar
        valid = []
        for msg in restored[-20:]:  # máximo 20
            if (isinstance(msg, dict)
                and msg.get("role") in ("user", "assistant")
                and isinstance(msg.get("content"), str)
                and msg["content"].strip()):
                valid.append({
                    "role": msg["role"],
                    "content": msg["content"][:5000]  # limite por mensagem
                })
        chat_history.clear()
        chat_history.extend(valid)
        print(f"[SESSION] Histórico restaurado: {len(valid)} mensagens")
        await send_json_msg({
            "type": "session_restored",
            "count": len(valid)
        })
    continue
```

No frontend, tratar a confirmação (no handler de `ws.onmessage`, bloco JSON):

```javascript
if (data.type === 'session_restored') {
    console.log(`[SESSION] Server confirmou: ${data.count} mensagens restauradas`);
}
```

---

## Resumo das mudanças

### `static/index.html`
- Variáveis: `reconnectDelay`, `RECONNECT_*`, `reconnectAttempts`, `keepAliveTimer`, `pongReceived`, `KEEPALIVE_*`, `chatMessages`, `MAX_RESTORE`, `hasConnectedBefore`
- Funções novas: `startKeepAlive()`, `stopKeepAlive()`, `trimChatMessages()`
- Modificados: `connect()` (onopen, onclose), `disconnect()`, handler de `onmessage`

### `server_ws.py`
- Handlers novos no receive loop: `ping` (→ pong), `restore_history` (→ restaura chat_history)
- Zero mudanças no core/, STT, TTS, ou LLM

---

## Testes manuais após implementar

1. **Backoff:** Parar o server → ver no console do browser os delays crescendo (3s, 6s, 12s, 24s, 30s, 30s...)
2. **Backoff reset:** Reiniciar o server → browser reconecta → próxima queda volta pra 3s
3. **Keep-alive:** Conectar → esperar 30s → ver no console "[KA] Pong: XXms"
4. **Keep-alive morte:** Conectar → matar o server SEM fechar limpo → browser detecta em ~30s e reconecta
5. **Session restore:** Conversar 3-4 turnos → matar server → reiniciar → browser reconecta → falar "o que eu disse antes?" → LLM deve saber o contexto
6. **Disconnect limpo:** Clicar "Encerrar" → reconectar → histórico NÃO é restaurado (zerou)
7. **Rodar testes:** `python -m pytest tests/ -v` — todos devem passar (estas mudanças não afetam testes existentes pois são de transporte, não de lógica de processamento)
