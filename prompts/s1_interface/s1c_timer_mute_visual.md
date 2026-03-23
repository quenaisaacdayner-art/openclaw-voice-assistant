# S1-C: Timer "Pensando" + Fix Visual do Mute

> Prompt auto-contido. Leia e execute.
> Pré-requisito: S1-A e S1-B executados
> Arquivos a modificar: `static/index.html` (SOMENTE frontend)

---

## Contexto

O frontend já tem indicadores de status (dot com cor + texto). Faltam 2 melhorias visuais:

1. **Timer "Pensando"** — quando o LLM está processando, mostrar quanto tempo está levando (ex: "Pensando... 3.2s"). Ajuda o usuário a saber que não travou.
2. **Fix visual do mute** — quando o mic está mutado, a barra de volume continua atualizando (RMS é calculado mesmo mutado). Deve mostrar visual claro de "muted".

---

## Tarefa 1: Timer "Pensando"

### JavaScript:

1. Adicionar variáveis de estado:
   ```javascript
   let thinkingTimer = null;
   let thinkingStartTime = 0;
   ```

2. Modificar `handleStatus()`:

   Quando status muda pra `thinking`:
   ```javascript
   case 'thinking':
       setStatus('thinking', 'Pensando...');
       thinkingStartTime = Date.now();
       // Atualizar texto a cada 100ms
       if (thinkingTimer) clearInterval(thinkingTimer);
       thinkingTimer = setInterval(() => {
           const elapsed = ((Date.now() - thinkingStartTime) / 1000).toFixed(1);
           bottomStatus.textContent = `Pensando... ${elapsed}s`;
       }, 100);
       bottomStatus.textContent = 'Pensando... 0.0s';
       break;
   ```

   Em TODOS os outros cases (`listening`, `speaking`, `default`), limpar o timer:
   ```javascript
   if (thinkingTimer) {
       clearInterval(thinkingTimer);
       thinkingTimer = null;
   }
   ```

3. Também limpar o timer na função `disconnect()` (adicionada no S1-A):
   ```javascript
   if (thinkingTimer) {
       clearInterval(thinkingTimer);
       thinkingTimer = null;
   }
   ```

---

## Tarefa 2: Fix Visual do Mute

### Problema atual:
`processAudioChunk()` atualiza `volumeBar.style.width` ANTES do check `if (isMuted) return;`. Isso significa que a barra de volume mostra atividade mesmo quando mutado.

### Fix no JavaScript:

1. Em `processAudioChunk()`, mover a atualização visual pra DEPOIS do check de mute:

   ```javascript
   function processAudioChunk(float32Array) {
       let sum = 0;
       for (let i = 0; i < float32Array.length; i++) {
           sum += float32Array[i] * float32Array[i];
       }
       const rms = Math.sqrt(sum / float32Array.length);

       // Barge-in: detectou fala durante playback (funciona mesmo mutado)
       if (isPlaying && rms > VAD_THRESHOLD * 3) {
           stopPlayback();
           if (ws && ws.readyState === WebSocket.OPEN) {
               ws.send(JSON.stringify({type: 'interrupt'}));
           }
       }

       // Se mutado: zerar barra e não processar VAD
       if (isMuted) {
           volumeBar.style.width = '0%';
           return;
       }

       // Atualizar visualização (só quando não mutado)
       const pct = Math.min(rms / 0.1, 1) * 100;
       volumeBar.style.width = pct + '%';
       volumeBar.classList.toggle('speaking', isSpeechDetected);

       // ... resto do VAD (inalterado)
   ```

2. Em `toggleMute()`, adicionar feedback visual imediato:
   ```javascript
   function toggleMute() {
       isMuted = !isMuted;
       micBtn.classList.toggle('active', isMuted);
       micBtn.textContent = isMuted ? '🔇' : '🎤';
       // Zerar barra imediatamente ao mutar
       if (isMuted) {
           volumeBar.style.width = '0%';
       }
   }
   ```

### CSS — adicionar estilo visual de muted na barra:

```css
.volume-bar.muted {
    background: #666 !important;
    width: 100% !important;
    opacity: 0.3;
}
```

E no `toggleMute()`:
```javascript
volumeBar.classList.toggle('muted', isMuted);
```

**Decisão:** quando mutado, a barra fica cinza 100% opaca 30% = visual claro de "desligado" sem parecer bugado.

---

## O que NÃO fazer

- NÃO mudar a lógica de barge-in (deve funcionar mesmo mutado — mantém o check ANTES do `if (isMuted)`)
- NÃO mexer em `server_ws.py`
- NÃO mexer em `core/`
- NÃO mudar a lógica de VAD (só reordenar visual antes de mute check)
- NÃO remover nenhuma funcionalidade existente

---

## Critério de sucesso

1. [ ] Quando LLM está processando: bottomStatus mostra "Pensando... X.Xs" atualizando em tempo real
2. [ ] Quando resposta começa (status speaking): timer para e texto muda pra "Falando..."
3. [ ] Quando mutado: barra de volume fica cinza e não atualiza
4. [ ] Quando desmuta: barra volta a funcionar normalmente (verde)
5. [ ] Barge-in funciona mesmo com mic mutado (se o áudio atinge threshold alto)
6. [ ] Timer não continua rodando após disconnect
7. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

1. Iniciar → falar algo → observar timer ("Pensando... 0.0s → 1.2s → 2.5s...")
2. Quando resposta chega → timer para, muda pra "Falando..."
3. Mutar mic → barra fica cinza
4. Desmutar → barra volta verde, mostra volume
5. Desconectar → reconectar → tudo funciona normal
