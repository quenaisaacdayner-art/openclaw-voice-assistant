# S1-B: Input de Texto via WebSocket

> Prompt auto-contido. Leia e execute.
> Pré-requisito: S1-A executado (botões Disconnect e Interrupt já existem)
> Arquivos a modificar: `static/index.html`, `server_ws.py`

---

## Contexto

O voice assistant funciona 100% por voz: o usuário fala → WebSocket envia PCM → server transcreve com Whisper → envia pro LLM → responde com TTS.

**Problema:** se o mic não funciona, ou o usuário está em ambiente barulhento, ou simplesmente prefere digitar — não tem opção. Precisamos de um campo de texto que envia mensagens pelo mesmo WebSocket.

---

## Tarefa 1: Backend — novo tipo de mensagem no WebSocket (`server_ws.py`)

### No receive loop (`while True: message = await ws.receive()`):

Adicionar handler pra mensagem de texto do usuário. Dentro do bloco `elif "text" in message:`, após o `elif data["type"] == "interrupt":`:

```python
elif data["type"] == "text_input":
    # Mensagem de texto digitada pelo usuário
    user_text = data.get("text", "").strip()
    if user_text and not processing:
        # Criar task pra processar texto (mesmo fluxo, sem STT)
        process_task = asyncio.create_task(process_text(user_text))
```

### Nova função `process_text()` no `server_ws.py`:

Adicionar ANTES do receive loop (ao lado de `process_speech()`):

```python
async def process_text(user_text):
    """Processa texto digitado: LLM → TTS (sem STT)."""
    nonlocal processing, chat_history
    processing = True
    cancel_event.clear()

    try:
        t0 = time.time()
        print(f"\n[REQ] Texto digitado: \"{user_text[:50]}{'...' if len(user_text) > 50 else ''}\"")

        # Mostrar transcrição (o próprio texto digitado)
        await send_json_msg({"type": "transcript", "text": user_text})
        await send_status("thinking")

        # Adicionar ao histórico
        chat_history.append({"role": "user", "content": user_text})
        if len(chat_history) > MAX_HISTORY * 2:
            chat_history = chat_history[-(MAX_HISTORY * 2):]

        # LLM streaming + TTS por frase
        # (copiar exatamente o bloco de streaming do process_speech(),
        #  a partir de "api_history = build_api_history..." até o final
        #  incluindo o fallback síncrono e o logging)
        api_history = build_api_history(chat_history[:-1])
        await send_status("speaking")

        loop = asyncio.get_event_loop()
        text_queue = asyncio.Queue()
        t_llm_start = time.time()
        t_ttft = None

        def _stream_worker():
            try:
                for partial in ask_openclaw_stream(user_text, TOKEN, api_history):
                    asyncio.run_coroutine_threadsafe(
                        text_queue.put(partial), loop
                    )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    text_queue.put(("__error__", str(e))), loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(
                    text_queue.put(None), loop
                )

        loop.run_in_executor(None, _stream_worker)

        full_response = ""
        last_tts_end = 0
        stream_error = False
        tts_count = 0
        t_tts_first = None

        while True:
            if cancel_event.is_set():
                break
            try:
                partial = await asyncio.wait_for(text_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            if partial is None:
                break
            if isinstance(partial, tuple) and partial[0] == "__error__":
                stream_error = True
                break

            if t_ttft is None:
                t_ttft = time.time()
                print(f"[LLM] TTFT: {t_ttft - t_llm_start:.1f}s")

            full_response = partial
            await send_json_msg({"type": "text", "text": partial, "done": False})

            remaining = partial[last_tts_end:]
            end = _find_sentence_end(remaining)
            if end > 0:
                sentence = remaining[:end].strip()
                if sentence and not cancel_event.is_set():
                    t_tts_s = time.time()
                    audio_bytes = await _tts_to_bytes(sentence, loop)
                    if audio_bytes and not cancel_event.is_set():
                        await ws.send_bytes(audio_bytes)
                        tts_count += 1
                        if t_tts_first is None:
                            t_tts_first = time.time()
                            print(f"[TTS] 1ª frase: \"{sentence[:40]}\" ({t_tts_first - t_tts_s:.1f}s)")
                    last_tts_end += end

        t_llm_end = time.time()
        if full_response:
            print(f"[LLM] Resposta: {len(full_response)} chars em {t_llm_end - t_llm_start:.1f}s")

        if stream_error and not full_response and not cancel_event.is_set():
            try:
                full_response = await loop.run_in_executor(
                    None, ask_openclaw, user_text, TOKEN, api_history
                )
            except Exception:
                await send_json_msg({"type": "error", "message": "Erro ao processar resposta."})
                return

        if full_response and not cancel_event.is_set():
            remaining_text = full_response[last_tts_end:].strip()
            if remaining_text:
                audio_bytes = await _tts_to_bytes(remaining_text, loop)
                if audio_bytes and not cancel_event.is_set():
                    await ws.send_bytes(audio_bytes)
                    tts_count += 1

            await send_json_msg({"type": "text", "text": full_response, "done": True})
            chat_history.append({"role": "assistant", "content": full_response})
        elif full_response:
            await send_json_msg({"type": "text", "text": full_response, "done": True})
            chat_history.append({"role": "assistant", "content": full_response + " [interrompido]"})

        t_total = time.time() - t0
        if tts_count > 0:
            print(f"[TTS] Total: {tts_count} frases")
        print(f"[TOTAL] Texto→Resposta: {t_total:.1f}s")

    except Exception as e:
        traceback.print_exc()
        await send_json_msg({"type": "error", "message": f"Erro interno: {e}"})
    finally:
        processing = False
        if not cancel_event.is_set():
            await send_status("listening")
```

### ⚠️ IMPORTANTE — Refactoring da duplicação

Olhando o código acima, `process_text()` e `process_speech()` compartilham ~90% do código (tudo após a transcrição STT). **ANTES de adicionar `process_text()`**, refatorar:

1. Extrair o bloco de LLM streaming + TTS do `process_speech()` pra uma função auxiliar:
   ```python
   async def _llm_and_tts(user_text, ws, chat_history, cancel_event):
       """LLM streaming + TTS por frase. Retorna (full_response, chat_history)."""
       # ... todo o bloco de streaming daqui
   ```

2. `process_speech()` fica: STT → chama `_llm_and_tts(transcript, ...)`
3. `process_text()` fica: chama `_llm_and_tts(user_text, ...)`

Isso evita duplicação no `server_ws.py`.

---

## Tarefa 2: Frontend — campo de texto (`static/index.html`)

### HTML — adicionar abaixo da `div.bottom-bar`, ANTES do error-toast:

```html
<div class="text-input-bar" id="textInputBar" style="display:none">
    <input type="text" id="textInput" placeholder="Digite sua mensagem..."
           autocomplete="off" maxlength="2000">
    <button class="btn" id="textSendBtn" onclick="sendText()">Enviar</button>
</div>
```

### CSS — adicionar:

```css
.text-input-bar {
    background: #16162a;
    padding: 8px 16px;
    display: flex;
    gap: 8px;
    border-top: 1px solid #2d2d44;
    flex-shrink: 0;
}
.text-input-bar input {
    flex: 1;
    background: #2d2d44;
    border: 1px solid #3d3d54;
    color: #e0e0e0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 0.9rem;
    outline: none;
}
.text-input-bar input:focus {
    border-color: #4caf50;
}
```

### JavaScript:

1. Mostrar campo de texto quando conectado:
   - No `ws.onopen`: `document.getElementById('textInputBar').style.display = 'flex';`
   - No `disconnect()` (do S1-A): `document.getElementById('textInputBar').style.display = 'none';`

2. Implementar `sendText()`:
   ```javascript
   function sendText() {
       const input = document.getElementById('textInput');
       const text = input.value.trim();
       if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

       // Mostrar na UI imediatamente
       addUserMessage(text);
       input.value = '';

       // Enviar via WebSocket
       ws.send(JSON.stringify({type: 'text_input', text: text}));
   }
   ```

3. Enter pra enviar:
   ```javascript
   document.getElementById('textInput').addEventListener('keydown', (e) => {
       if (e.key === 'Enter' && !e.shiftKey) {
           e.preventDefault();
           sendText();
       }
   });
   ```
   Adicionar este listener DEPOIS do DOM carregar — pode ir no final do `<script>`, ou dentro de um `DOMContentLoaded`.

4. Desabilitar input durante processing:
   - Quando `handleStatus('thinking')` ou `handleStatus('speaking')`: `textInput.disabled = true`
   - Quando `handleStatus('listening')`: `textInput.disabled = false; textInput.focus();`

### Comportamento quando texto é enviado:

- Mensagem do user aparece no chat imediatamente (antes da resposta)
- Server processa: LLM → TTS (mesmo fluxo de voz, sem STT)
- Resposta aparece no chat + áudio toca normalmente
- O `{type: "transcript", text: "..."}` que o server envia de volta NÃO deve duplicar a mensagem (o frontend já adicionou). Opções:
  - **Opção A (recomendada):** No frontend, quando `text_input` é enviado, setar flag `pendingTextInput = true`. No handler de `transcript`, se `pendingTextInput` é true, ignorar (não adicionar de novo). Resetar flag quando receber próximo `status: "listening"`.
  - **Opção B:** No server, `process_text()` NÃO envia `{type: "transcript"}`. Mas isso quebra simetria com `process_speech()`.

Implementar **Opção A**.

---

## O que NÃO fazer

- NÃO remover nenhum controle de voz existente (mic, mute, start, etc.)
- NÃO mudar a lógica de VAD ou barge-in
- NÃO duplicar lógica de LLM+TTS — extrair pra função compartilhada
- NÃO mexer em `core/` (nenhum módulo core é afetado)
- NÃO mexer em `voice_assistant_app.py` ou `voice_assistant_cli.py`

---

## Critério de sucesso

1. [ ] Campo de texto aparece quando WebSocket conecta
2. [ ] Digitar + Enter envia mensagem
3. [ ] Botão "Enviar" envia mensagem
4. [ ] Mensagem aparece no chat imediatamente
5. [ ] Resposta aparece no chat + áudio toca
6. [ ] Mensagem NÃO aparece duplicada (flag pendingTextInput)
7. [ ] Input desabilita durante thinking/speaking
8. [ ] Voz continua funcionando normalmente junto com texto
9. [ ] Interrupt manual (S1-A) funciona durante resposta de texto também
10. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

1. Iniciar → verificar que campo de texto apareceu
2. Digitar "Olá, tudo bem?" + Enter → resposta aparece + áudio toca
3. Falar por voz → resposta aparece + áudio toca (voz continua funcionando)
4. Durante resposta de texto, clicar "⏹️" → resposta para
5. Desconectar → campo de texto some
6. Reconectar → campo de texto volta
