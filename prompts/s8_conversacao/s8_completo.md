# S8: Conversação & Contexto — PROMPT COMPLETO

> Prompt unificado. Leia e execute TUDO.
> Pré-requisito: S1-S7 completos
> Arquivos a modificar: `static/index.html`
> Arquivos a criar: nenhum

---

## Visão geral

2 features de conversação. Zero mudanças no backend. Implementar nesta ordem:

1. Timestamps nas mensagens (user + assistant)
2. Export da conversa (botão no config panel → download JSON)

---

## FEATURE 1: Timestamps nas mensagens

### Objetivo

Cada mensagem (user e assistant) deve mostrar a hora em que foi enviada/recebida. Útil pra contexto temporal e pro export.

### Dados (`chatMessages`)

Modificar os pushes pra incluir timestamp:

**No handler de `transcript` (mensagem do user):**
```javascript
case 'transcript':
    if (!pendingTextInput) addUserMessage(data.text);
    if (data.text && data.text.trim()) {
        chatMessages.push({ 
            role: 'user', 
            content: data.text.trim(),
            timestamp: new Date().toISOString()
        });
        trimChatMessages();
        checkSessionLength();
    }
    break;
```

**No handler de `text` (mensagem do assistant, quando `data.done`):**
```javascript
case 'text':
    updateAssistantMessage(data.text, data.done);
    if (data.done && data.text) {
        chatMessages.push({ 
            role: 'assistant', 
            content: data.text,
            timestamp: new Date().toISOString()
        });
        trimChatMessages();
        checkSessionLength();
    }
    break;
```

**No handler de `text_input` (quando user envia texto manualmente) — se existir push ali, mesmo tratamento.**

### Visual

Adicionar timestamp embaixo de cada bolha de mensagem.

**CSS — adicionar:**

```css
.message-time {
    font-size: 0.65rem;
    color: #666;
    margin-top: 2px;
    text-align: right;
}
.user .message-time { text-align: right; }
.assistant .message-time { text-align: left; }
```

**Modificar `addUserMessage(text)`:**

Após criar o elemento da mensagem, adicionar:

```javascript
function addUserMessage(text) {
    // ... código existente de criar o div.message.user ...
    
    // Timestamp
    const timeEl = document.createElement('div');
    timeEl.className = 'message-time';
    timeEl.textContent = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    el.appendChild(timeEl);
    
    // ... appendChild ao messages container ...
}
```

**Modificar `updateAssistantMessage(text, done)` — quando `done === true`:**

```javascript
if (done && currentAssistantEl) {
    // ... código existente ...
    
    // Adicionar timestamp quando a resposta completa
    const timeEl = document.createElement('div');
    timeEl.className = 'message-time';
    timeEl.textContent = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    currentAssistantEl.appendChild(timeEl);
}
```

---

## FEATURE 2: Export da conversa

### Objetivo

Botão no config panel que baixa a conversa atual como arquivo `.json`. O JSON inclui mensagens com timestamps, metadata do modelo e data do export.

### UI — Botão no config panel

Adicionar no final do `div.config-panel` (após o último `config-group`):

```html
<div class="config-group">
    <label>Conversa</label>
    <button class="btn" onclick="exportConversation()" id="exportBtn" style="width:100%;padding:8px;font-size:0.85rem;">
        💾 Salvar conversa (.json)
    </button>
    <small>Exporta todas as mensagens da sessão atual com timestamps.</small>
</div>
```

### JavaScript

Adicionar a função:

```javascript
function exportConversation() {
    if (chatMessages.length === 0) {
        showError('Nenhuma mensagem pra exportar.');
        return;
    }

    const exportData = {
        exported_at: new Date().toISOString(),
        message_count: chatMessages.length,
        messages: chatMessages.map(m => ({
            role: m.role,
            content: m.content,
            timestamp: m.timestamp || null
        }))
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    
    // Nome: ova_conversa_2026-03-23_22-30.json
    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10);
    const timeStr = now.toTimeString().slice(0, 5).replace(':', '-');
    a.download = `ova_conversa_${dateStr}_${timeStr}.json`;
    
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
```

### Formato do JSON exportado

```json
{
    "exported_at": "2026-03-23T22:30:00.000Z",
    "message_count": 8,
    "messages": [
        {
            "role": "user",
            "content": "Oi, como funciona o OpenClaw?",
            "timestamp": "2026-03-23T22:25:10.000Z"
        },
        {
            "role": "assistant",
            "content": "O OpenClaw é um framework...",
            "timestamp": "2026-03-23T22:25:18.000Z"
        }
    ]
}
```

---

## Testes

Rodar após implementar:

```bash
python -m pytest tests/ -v
```

Todos os testes devem continuar passando (mudanças são 100% frontend).

### Testes manuais

1. **Timestamps visíveis:** Enviar uma mensagem (texto ou voz) → hora aparece embaixo da bolha (formato HH:MM) ✅
2. **Timestamp do assistant:** Esperar resposta completa → hora aparece embaixo da bolha do assistant ✅
3. **Export vazio:** Clicar "Salvar conversa" sem mensagens → erro "Nenhuma mensagem pra exportar" ✅
4. **Export com mensagens:** Conversar 2-3 mensagens → clicar "Salvar conversa" → download de `.json` ✅
5. **JSON válido:** Abrir o `.json` exportado → estrutura correta com timestamps ✅
6. **Nome do arquivo:** Formato `ova_conversa_2026-03-23_22-30.json` ✅

---

## Checklist final

- [ ] `chatMessages.push()` inclui `timestamp: new Date().toISOString()` (user + assistant)
- [ ] CSS `.message-time` adicionado
- [ ] `addUserMessage()` mostra timestamp visual (HH:MM)
- [ ] `updateAssistantMessage()` mostra timestamp quando `done`
- [ ] Botão "Salvar conversa" no config panel
- [ ] `exportConversation()` gera JSON e faz download
- [ ] Testes passam: `python -m pytest tests/ -v`
