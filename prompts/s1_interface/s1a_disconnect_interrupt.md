# S1-A: Botão Disconnect + Botão Interrupt Manual

> Prompt auto-contido. Leia e execute.
> Pré-requisito: Nenhum (primeiro prompt do subtítulo 1)
> Arquivos a modificar: `static/index.html`, `server_ws.py`

---

## Contexto

O voice assistant tem WebSocket S2S funcional. O frontend (`static/index.html`) já tem:
- Botão "Iniciar" que abre WebSocket + pede permissão de mic
- Barge-in automático (detecta fala durante playback → envia `{type: "interrupt"}`)
- Mute/Unmute
- Auto-reconnect em 3s

**Faltam 2 controles:**
1. **Botão Disconnect** — encerrar sessão limpa (fechar WS, parar mic, limpar buffers, voltar ao estado inicial)
2. **Botão Interrupt manual** — parar a resposta da IA com um clique/tap (não apenas por voz)

---

## Tarefa 1: Botão Disconnect

### No frontend (`static/index.html`):

1. Adicionar botão "Encerrar" na `div.controls` (ao lado do botão "Iniciar"):
   - Classe: `btn`
   - Texto inicial: "Encerrar"
   - Invisível por padrão (`style="display:none"`)
   - Aparece quando `started === true`
   - Ao clicar: chama nova função `disconnect()`

2. Implementar função `disconnect()`:
   ```javascript
   function disconnect() {
       // 1. Fechar WebSocket
       if (reconnectTimer) {
           clearTimeout(reconnectTimer);
           reconnectTimer = null;
       }
       if (ws) {
           ws.onclose = null;  // Não reconectar
           ws.close();
           ws = null;
       }

       // 2. Parar microfone
       if (processor) {
           processor.disconnect();
           processor = null;
       }
       if (mediaStream) {
           mediaStream.getTracks().forEach(t => t.stop());
           mediaStream = null;
       }
       if (audioContext) {
           audioContext.close();
           audioContext = null;
       }

       // 3. Parar playback
       stopPlayback();
       if (playbackContext && playbackContext !== audioContext) {
           // Não fechar se é o mesmo context
       }
       playbackContext = null;

       // 4. Reset estado
       started = false;
       isMuted = false;
       isSpeechDetected = false;
       speechStartTime = 0;
       silenceStartTime = 0;
       serverSpeaking = false;

       // 5. Reset UI
       startBtn.textContent = 'Iniciar';
       startBtn.disabled = false;
       micBtn.classList.remove('active');
       micBtn.textContent = '🎤';
       bottomStatus.textContent = 'Clique para iniciar';
       volumeBar.style.width = '0%';
       setStatus('disconnected', 'Desconectado');

       // 6. Esconder botão Encerrar, mostrar Iniciar
       document.getElementById('disconnectBtn').style.display = 'none';
       startBtn.style.display = '';
   }
   ```

3. Modificar `start()`:
   - Após `started = true`, esconder botão "Iniciar" e mostrar botão "Encerrar"
   ```javascript
   startBtn.style.display = 'none';
   document.getElementById('disconnectBtn').style.display = '';
   ```

4. **IMPORTANTE:** `playbackContext` e `audioContext` são o mesmo objeto no código atual (`playbackContext = audioContext` no `startMic()`). O `disconnect()` deve fechar apenas `audioContext` e setar ambos pra `null`.

### No backend (`server_ws.py`):

Nenhuma mudança necessária. O `WebSocketDisconnect` exception handler já existe e cancela tasks pendentes.

---

## Tarefa 2: Botão Interrupt Manual

### No frontend (`static/index.html`):

1. Adicionar botão de interrupt na `div.controls`:
   - Classe: `btn`
   - ID: `interruptBtn`
   - Texto: "⏹️"
   - Invisível por padrão (`style="display:none"`)
   - Aparece quando servidor está no estado `thinking` ou `speaking`
   - Desaparece quando volta pra `listening`

2. Ao clicar: chama nova função `manualInterrupt()`:
   ```javascript
   function manualInterrupt() {
       stopPlayback();
       if (ws && ws.readyState === WebSocket.OPEN) {
           ws.send(JSON.stringify({type: 'interrupt'}));
       }
   }
   ```

3. Modificar `handleStatus()` pra mostrar/esconder o botão:
   ```javascript
   const interruptBtn = document.getElementById('interruptBtn');
   // Mostrar durante thinking e speaking:
   interruptBtn.style.display = (status === 'thinking' || status === 'speaking') ? '' : 'none';
   ```

### No backend (`server_ws.py`):

Nenhuma mudança necessária. O handler de `{type: "interrupt"}` já existe e funciona (cancela LLM + TTS via `cancel_event`).

---

## O que NÃO fazer

- NÃO mudar a lógica de barge-in automático (deve continuar funcionando)
- NÃO mudar a lógica de reconnect (agora controlada: `disconnect()` desliga reconnect, `ws.onclose` normal mantém reconnect)
- NÃO mexer em `server_ws.py` (tudo é frontend neste prompt)
- NÃO mexer em `core/` (nenhum módulo core é afetado)
- NÃO remover nenhum botão ou função existente

---

## Critério de sucesso

1. [ ] Botão "Iniciar" aparece no load. Ao clicar, some e aparece "Encerrar"
2. [ ] Botão "Encerrar" fecha WS, para mic, para playback, volta ao estado "Desconectado"
3. [ ] Após "Encerrar", pode clicar "Iniciar" de novo e funciona normalmente
4. [ ] Botão "⏹️" aparece durante thinking/speaking
5. [ ] Clicar "⏹️" para a resposta (mesmo efeito do barge-in por voz)
6. [ ] Botão "⏹️" some quando volta pra listening
7. [ ] Barge-in automático por voz continua funcionando
8. [ ] Auto-reconnect funciona quando WS cai (não quando usuário clica "Encerrar")
9. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

1. Iniciar → verificar que "Encerrar" apareceu
2. Falar algo → esperar resposta → durante a resposta, clicar "⏹️" → resposta para
3. Falar de novo → verificar que funciona normal após interrupt
4. Clicar "Encerrar" → verificar que tudo parou e voltou ao estado inicial
5. Clicar "Iniciar" de novo → verificar que conecta normalmente
6. Fechar e reabrir a aba → verificar que auto-reconnect NÃO acontece (deve começar desconectado)
