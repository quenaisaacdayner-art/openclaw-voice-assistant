# S5: Robustez & Stress Test — PROMPT COMPLETO

> Prompt unificado. Leia e execute TUDO.
> Pré-requisito: S1-S4 já executados
> Arquivos a modificar: `core/tts.py`, `server_ws.py`, `static/index.html`, `tests/`
> NÃO mexer em: `core/llm.py`, `core/stt.py`, `core/config.py`, `core/history.py`

---

## Visão geral

5 fixes de robustez pra sessões longas (4h+). Implementar TODOS nesta ordem:

1. Limpeza de markdown antes do TTS (voz lê "#", "**", etc.)
2. Timeout no LLM — evitar "Pensando..." infinito
3. Proteção contra fala rápida (race condition)
4. Cleanup de tasks ao desconectar
5. Aviso de sessão longa na UI

---

## FIX 1: Limpeza de Markdown antes do TTS

### Problema

O LLM retorna texto com markdown (headers `#`, bold `**texto**`, italic `*texto*`, code `` `código` ``, bullets `- item`, links `[texto](url)`). O TTS tenta ler esses símbolos em voz alta. O usuário ouve "hashtag hashtag título" ou "asterisco asterisco texto asterisco asterisco".

### Solução

Criar função `_strip_markdown(text)` em `core/tts.py` e chamar ANTES de mandar pro TTS engine.

### Implementação (`core/tts.py`):

Adicionar no topo do arquivo (após os imports, antes das constantes):

```python
import re as _re

def _strip_markdown(text):
    """Remove formatação markdown pra TTS não ler símbolos em voz alta."""
    if not text:
        return text
    
    s = text
    
    # Code blocks (``` ... ```) → manter conteúdo
    s = _re.sub(r'```[\s\S]*?```', '', s)
    
    # Inline code (`texto`) → manter texto
    s = _re.sub(r'`([^`]+)`', r'\1', s)
    
    # Headers (# ## ### etc) → remover os #
    s = _re.sub(r'^#{1,6}\s+', '', s, flags=_re.MULTILINE)
    
    # Bold+italic (***texto*** ou ___texto___) → manter texto
    s = _re.sub(r'\*{3}(.+?)\*{3}', r'\1', s)
    s = _re.sub(r'_{3}(.+?)_{3}', r'\1', s)
    
    # Bold (**texto** ou __texto__) → manter texto
    s = _re.sub(r'\*{2}(.+?)\*{2}', r'\1', s)
    s = _re.sub(r'_{2}(.+?)_{2}', r'\1', s)
    
    # Italic (*texto* ou _texto_) → manter texto
    # Cuidado: não pegar bullets (* item)
    s = _re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'\1', s)
    s = _re.sub(r'(?<!\w)_([^_\n]+?)_(?!\w)', r'\1', s)
    
    # Links [texto](url) → manter texto
    s = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)
    
    # Images ![alt](url) → remover completamente
    s = _re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', s)
    
    # Blockquotes (> texto) → manter texto
    s = _re.sub(r'^>\s+', '', s, flags=_re.MULTILINE)
    
    # Bullets (- item ou * item no início de linha) → manter texto
    s = _re.sub(r'^\s*[-*+]\s+', '', s, flags=_re.MULTILINE)
    
    # Numbered lists (1. item) → manter texto
    s = _re.sub(r'^\s*\d+\.\s+', '', s, flags=_re.MULTILINE)
    
    # Horizontal rules (---, ***, ___) → remover
    s = _re.sub(r'^[-*_]{3,}\s*$', '', s, flags=_re.MULTILINE)
    
    # Strikethrough (~~texto~~) → manter texto
    s = _re.sub(r'~~(.+?)~~', r'\1', s)
    
    # Limpar linhas vazias múltiplas
    s = _re.sub(r'\n{3,}', '\n\n', s)
    
    # Limpar espaços extras
    s = s.strip()
    
    return s
```

### Aplicar no `generate_tts()`:

Na função `generate_tts(text)`, APÓS o truncamento na linha que faz `tts_text = text[:1500]...` e ANTES de passar pros engines, adicionar:

```python
    # Truncar pra TTS
    tts_text = text[:1500] + "..." if len(text) > 1500 else text
    
    # Limpar markdown — TTS não deve ler símbolos
    tts_text = _strip_markdown(tts_text)
    
    if not tts_text:
        return None
```

Nota: adicionar `if not tts_text: return None` APÓS o strip, porque o text pode ficar vazio se era só um code block.

### Testes (`tests/test_tts_strip.py` — CRIAR ARQUIVO NOVO):

```python
"""Testes da limpeza de markdown pro TTS."""
import pytest
from core.tts import _strip_markdown


class TestStripMarkdown:
    def test_removes_headers(self):
        assert _strip_markdown("# Título") == "Título"
        assert _strip_markdown("## Subtítulo") == "Subtítulo"
        assert _strip_markdown("### Nível 3") == "Nível 3"

    def test_removes_bold(self):
        assert _strip_markdown("texto **negrito** aqui") == "texto negrito aqui"
        assert _strip_markdown("texto __negrito__ aqui") == "texto negrito aqui"

    def test_removes_italic(self):
        assert _strip_markdown("texto *itálico* aqui") == "texto itálico aqui"
        assert _strip_markdown("texto _itálico_ aqui") == "texto itálico aqui"

    def test_removes_bold_italic(self):
        assert _strip_markdown("***importante***") == "importante"

    def test_removes_inline_code(self):
        assert _strip_markdown("use `pip install`") == "use pip install"

    def test_removes_code_blocks(self):
        text = "antes\n```python\nprint('oi')\n```\ndepois"
        result = _strip_markdown(text)
        assert "```" not in result
        assert "antes" in result
        assert "depois" in result

    def test_removes_links_keeps_text(self):
        assert _strip_markdown("[clique aqui](http://example.com)") == "clique aqui"

    def test_removes_images(self):
        result = _strip_markdown("![foto](http://img.jpg)")
        assert "![" not in result
        assert "http" not in result

    def test_removes_blockquotes(self):
        assert _strip_markdown("> citação importante") == "citação importante"

    def test_removes_bullets(self):
        text = "- item 1\n- item 2\n* item 3"
        result = _strip_markdown(text)
        assert "- " not in result
        assert "* " not in result
        assert "item 1" in result

    def test_removes_numbered_lists(self):
        text = "1. primeiro\n2. segundo"
        result = _strip_markdown(text)
        assert "1." not in result
        assert "primeiro" in result

    def test_removes_strikethrough(self):
        assert _strip_markdown("~~deletado~~") == "deletado"

    def test_removes_horizontal_rule(self):
        result = _strip_markdown("texto\n---\nmais texto")
        assert "---" not in result
        assert "texto" in result

    def test_empty_input(self):
        assert _strip_markdown("") == ""
        assert _strip_markdown(None) is None

    def test_plain_text_unchanged(self):
        text = "Isso é texto normal sem formatação."
        assert _strip_markdown(text) == text

    def test_mixed_markdown(self):
        text = "# Título\n\nTexto **negrito** com `código` e [link](url).\n\n- Item 1\n- Item 2"
        result = _strip_markdown(text)
        assert "#" not in result
        assert "**" not in result
        assert "`" not in result
        assert "[link]" not in result
        assert "Título" in result
        assert "negrito" in result
        assert "código" in result
        assert "link" in result
        assert "Item 1" in result
```

---

## FIX 2: Timeout no LLM (evitar "Pensando..." infinito)

### Problema

Se o gateway não responde (caiu, rede instável, LLM travou), a função `_llm_and_tts()` fica esperando infinitamente. A UI mostra "Pensando... 45s... 60s... 120s..." sem nunca sair.

### Solução

Timeout de 120 segundos no stream do LLM. Se não receber NENHUM texto em 120s, cancelar e avisar o usuário.

### Implementação (`server_ws.py`):

Adicionar constante no topo (junto das outras constantes/imports):

```python
LLM_TIMEOUT = 120  # segundos sem resposta do LLM antes de cancelar
```

Na função `_llm_and_tts()`, modificar o loop principal de streaming. O loop atualmente é:

```python
while True:
    if cancel_event.is_set():
        break
    try:
        partial = await asyncio.wait_for(text_queue.get(), timeout=0.1)
    except asyncio.TimeoutError:
        continue
```

Substituir por:

```python
t_last_data = time.time()

while True:
    if cancel_event.is_set():
        break
    try:
        partial = await asyncio.wait_for(text_queue.get(), timeout=0.5)
    except asyncio.TimeoutError:
        # Checar timeout global
        if time.time() - t_last_data > LLM_TIMEOUT:
            print(f"[LLM] ⚠️ Timeout: {LLM_TIMEOUT}s sem resposta")
            await send_json_msg({
                "type": "error",
                "message": f"Sem resposta do servidor há {LLM_TIMEOUT}s. Tente novamente."
            })
            stream_error = True
            break
        continue
    
    t_last_data = time.time()  # Reset timer a cada chunk recebido
```

**Nota:** Mudamos o timeout interno de 0.1s → 0.5s pra reduzir polling desnecessário. Não afeta latência percebida.

**Nota 2:** O timer reseta a cada chunk. Então se o LLM demora 30s pro primeiro token (TTFT do Opus 4) mas depois flui normal, NÃO dispara timeout. Só dispara se ficar 120s SEM NENHUM dado.

---

## FIX 3: Proteção contra Fala Rápida (Race Condition)

### Problema

Se o usuário fala, pausa 1 segundo, e fala de novo rápido, dois eventos `speech_end` podem chegar quase juntos. A flag `processing = True` deveria bloquear o segundo, mas se o primeiro `process_speech()` ainda não setou a flag (é assíncrono), ambos podem iniciar.

### Solução

Usar um `asyncio.Lock` que garante exclusão mútua. Se chegar um segundo `speech_end` enquanto o primeiro processa, acumular o áudio pra processar na sequência.

### Implementação (`server_ws.py`):

Na função `websocket_endpoint`, junto das variáveis de estado (após `cancel_event = asyncio.Event()`), adicionar:

```python
processing_lock = asyncio.Lock()
pending_audio = bytearray()  # áudio que chegou durante processamento
```

Modificar o handler de `speech_end` no receive loop:

```python
if data["type"] == "vad_event" and data["event"] == "speech_end":
    if len(audio_buffer) < 1600:  # <50ms = ruído
        audio_buffer.clear()
        continue
    
    if processing_lock.locked():
        # Já processando — guardar áudio pra depois
        pending_audio.extend(audio_buffer)
        audio_buffer.clear()
        continue
    
    process_task = asyncio.create_task(process_speech())
```

Modificar o `finally` de `process_speech()`:

```python
finally:
    processing = False
    if not cancel_event.is_set():
        await send_status("listening")
    
    # Processar áudio pendente (se alguém falou durante o processamento)
    if len(pending_audio) > 1600:
        audio_buffer.extend(pending_audio)
        pending_audio.clear()
        # Não processar aqui — deixar o próximo speech_end triggerar
        # Isso evita loop infinito se o usuário continua falando
```

Modificar `process_speech()` pra usar o lock:

```python
async def process_speech():
    """Processa audio acumulado: STT -> LLM -> TTS"""
    nonlocal processing, chat_history
    
    async with processing_lock:
        processing = True
        cancel_event.clear()

        try:
            # ... todo o corpo existente ...
```

E fechar o `try/except/finally` existente DENTRO do `async with`. O `finally` deve ficar:

```python
        finally:
            processing = False
            if not cancel_event.is_set():
                await send_status("listening")
```

Fazer o mesmo com `process_text()` — envolver o corpo com `async with processing_lock:`.

**Também** adicionar `pending_audio` ao `nonlocal` de `process_speech`.

---

## FIX 4: Cleanup de Tasks ao Desconectar

### Problema

Quando o browser fecha a aba (WebSocketDisconnect), o `cancel_event` é setado e o `process_task` é cancelado. Mas a thread do `_stream_worker` (que faz HTTP pro gateway) pode continuar rodando até terminar ou dar timeout por conta própria. Isso desperdiça CPU e conexões HTTP.

### Solução

Melhorar o bloco `except WebSocketDisconnect` pra garantir cleanup completo.

### Implementação (`server_ws.py`):

Substituir o bloco `except WebSocketDisconnect` existente por:

```python
except WebSocketDisconnect:
    cancel_event.set()
    if process_task and not process_task.done():
        process_task.cancel()
        try:
            await asyncio.wait_for(process_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
    # Limpar buffers
    audio_buffer.clear()
    pending_audio.clear()
    print(f"[WS] Cliente desconectou. Cleanup completo.")
```

### Também: fechar sessão HTTP do LLM se possível

No `core/llm.py`, a `_session` (requests.Session) mantém conexões HTTP abertas. Isso é bom (keep-alive) mas não é um leak. Não precisa de fix adicional.

---

## FIX 5: Aviso de Sessão Longa

### Problema

Depois de 1-2 horas de conversa, as respostas ficam mais lentas porque o `chat_history` acumula tokens. O usuário não sabe por quê.

### Solução

Mostrar um aviso discreto na UI quando o histórico atinge um limiar. Oferecer botão pra limpar.

### Implementação (`static/index.html`):

Adicionar variável:

```javascript
const SESSION_WARN_MESSAGES = 30; // avisar após 30 mensagens (~15 exchanges)
let sessionWarningShown = false;
```

Adicionar função:

```javascript
function checkSessionLength() {
    if (sessionWarningShown) return;
    if (chatMessages.length >= SESSION_WARN_MESSAGES) {
        sessionWarningShown = true;
        
        // Criar toast de aviso
        const warn = document.createElement('div');
        warn.id = 'sessionWarn';
        warn.style.cssText = `
            position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
            background: #2d2d44; color: #ffd700; padding: 12px 20px; border-radius: 10px;
            font-size: 0.9em; z-index: 100; display: flex; align-items: center; gap: 10px;
            border: 1px solid rgba(255,215,0,0.3); max-width: 90%;
        `;
        warn.innerHTML = `
            <span>⚠️ Sessão longa — respostas podem ficar mais lentas.</span>
            <button onclick="clearHistory()" style="
                background: #ffd700; color: #1a1a2e; border: none; padding: 6px 12px;
                border-radius: 6px; cursor: pointer; font-weight: bold; white-space: nowrap;
            ">Limpar histórico</button>
            <button onclick="this.parentElement.remove()" style="
                background: none; border: none; color: #888; cursor: pointer; font-size: 1.2em;
            ">✕</button>
        `;
        document.body.appendChild(warn);
    }
}
```

Adicionar função de limpar histórico:

```javascript
function clearHistory() {
    chatMessages = [];
    sessionWarningShown = false;
    
    // Avisar o server pra limpar também
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'clear_history' }));
    }
    
    // Limpar mensagens da UI (opcional — manter ou limpar)
    const messages = document.getElementById('messages');
    if (messages) messages.innerHTML = '';
    
    // Remover aviso
    const warn = document.getElementById('sessionWarn');
    if (warn) warn.remove();
    
    console.log('[SESSION] Histórico limpo');
}
```

Chamar `checkSessionLength()` após cada push em `chatMessages` (mesmo lugar onde chama `trimChatMessages()`):

```javascript
chatMessages.push({ role: 'user', content: data.text.trim() });
trimChatMessages();
checkSessionLength();
```

### Backend (`server_ws.py`):

Adicionar handler no receive loop (junto dos outros handlers):

```python
elif data["type"] == "clear_history":
    chat_history.clear()
    print("[SESSION] Histórico limpo pelo usuário")
    await send_json_msg({"type": "history_cleared"})
    continue
```

---

## Testes automatizados adicionais

### Criar `tests/test_tts_strip.py` (já descrito no Fix 1 acima — copiar inteiro)

### Criar `tests/test_robustez.py`:

```python
"""Testes de robustez — timeout, cleanup, sessão longa."""
import asyncio
import json
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestLLMTimeout:
    """Verifica que LLM_TIMEOUT existe e é razoável."""
    
    def test_timeout_constant_exists(self):
        import server_ws
        assert hasattr(server_ws, 'LLM_TIMEOUT')
        assert server_ws.LLM_TIMEOUT >= 30  # mínimo razoável
        assert server_ws.LLM_TIMEOUT <= 300  # máximo razoável

    def test_timeout_is_120(self):
        import server_ws
        assert server_ws.LLM_TIMEOUT == 120


class TestStripMarkdownIntegration:
    """Verifica que generate_tts usa _strip_markdown."""
    
    def test_strip_is_called_in_generate(self):
        """_strip_markdown deve ser chamada dentro de generate_tts."""
        from core.tts import generate_tts, _strip_markdown
        # Verificar que a função existe e é importável
        assert callable(_strip_markdown)
    
    def test_code_block_not_spoken(self):
        from core.tts import _strip_markdown
        text = "Instale assim:\n```\npip install pacote\n```\nDepois configure."
        result = _strip_markdown(text)
        assert "```" not in result
        assert "Depois configure" in result


class TestProcessingLock:
    """Verifica que processing_lock existe no websocket_endpoint."""
    
    def test_asyncio_lock_importable(self):
        """asyncio.Lock deve estar disponível (usado pra race condition)."""
        lock = asyncio.Lock()
        assert not lock.locked()
```

---

## Resumo das mudanças

### `core/tts.py`
- Função nova: `_strip_markdown(text)` — remove markdown
- Modificada: `generate_tts(text)` — chama `_strip_markdown` antes do TTS

### `server_ws.py`
- Constante nova: `LLM_TIMEOUT = 120`
- Modificado: loop de streaming em `_llm_and_tts()` — timeout com aviso
- Novo: `processing_lock = asyncio.Lock()` + `pending_audio`
- Modificado: `process_speech()` e `process_text()` — usam lock
- Modificado: handler `speech_end` — acumula áudio se locked
- Melhorado: `except WebSocketDisconnect` — cleanup completo
- Handler novo: `clear_history`

### `static/index.html`
- Variáveis: `SESSION_WARN_MESSAGES`, `sessionWarningShown`
- Funções novas: `checkSessionLength()`, `clearHistory()`
- Chamada: `checkSessionLength()` após cada push em chatMessages

### `tests/` (novos)
- `test_tts_strip.py` — 18 testes de limpeza markdown
- `test_robustez.py` — 5 testes de timeout, integração, lock

---

## Testes manuais após implementar

1. **Markdown strip:** Perguntar algo que gere resposta com markdown (ex: "me dá uma lista de 5 itens") → voz NÃO deve ler "#", "**", "-", etc.
2. **Timeout LLM:** Desconectar da internet → falar algo → deve mostrar erro após 120s (ou menos se gateway cai rápido)
3. **Fala rápida:** Falar "olá" → pausa 0.5s → falar "como vai" → ambas devem ser processadas (não travar)
4. **Limpar histórico:** Conversar 15+ turnos → ver aviso amarelo → clicar "Limpar histórico" → conversa reseta
5. **Fechar aba:** Falar algo → enquanto responde, fechar aba → ver no terminal do server "[WS] Cliente desconectou. Cleanup completo."
6. **Rodar testes:** `python -m pytest tests/ -v` — todos devem passar
