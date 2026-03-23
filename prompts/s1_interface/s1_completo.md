# S1: Interface & Interação — PROMPT COMPLETO

> Prompt unificado. Leia e execute TUDO.
> Pré-requisito: Nenhum (primeiro subtítulo)
> Arquivos a modificar: `static/index.html`, `server_ws.py`, `core/stt.py`

---

## Visão geral

8 features de interface no frontend (`static/index.html`), com mudanças mínimas no backend. Implementar TODAS nesta ordem:

1. Botão Disconnect
2. Botão Interrupt manual
3. Input de texto via WebSocket (backend + frontend)
4. Timer "Pensando..."
5. Fix visual do mute
6. Esfera pulsante (CSS)
7. Markdown nas respostas (marked.js)
8. Painel de configuração (Gateway URL, Volume, Whisper model)

---

## FEATURE 1: Botão Disconnect

### Frontend (`static/index.html`):

Adicionar botão "Encerrar" na `div.controls` (ao lado do botão "Iniciar"):
- ID: `disconnectBtn`
- Invisível por padrão (`style="display:none"`)
- Aparece quando `started === true`
- Ao clicar: chama `disconnect()`

Implementar `disconnect()`:
```javascript
function disconnect() {
    // Parar reconnect
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    
    // Fechar WebSocket (sem reconectar)
    if (ws) { ws.onclose = null; ws.close(); ws = null; }
    
    // Parar microfone
    if (processor) { processor.disconnect(); processor = null; }
    if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
    if (audioContext) { audioContext.close(); audioContext = null; }
    
    // Parar playback
    stopPlayback();
    playbackContext = null;
    
    // Reset estado
    started = false; isMuted = false; isSpeechDetected = false;
    speechStartTime = 0; silenceStartTime = 0; serverSpeaking = false;
    
    // Reset UI
    startBtn.textContent = 'Iniciar'; startBtn.disabled = false; startBtn.style.display = '';
    document.getElementById('disconnectBtn').style.display = 'none';
    document.getElementById('interruptBtn').style.display = 'none';
    document.getElementById('textInputBar').style.display = 'none';
    document.getElementById('orbContainer').style.display = 'none';
    micBtn.classList.remove('active'); micBtn.textContent = '🎤';
    bottomStatus.textContent = 'Clique para iniciar';
    volumeBar.style.width = '0%'; volumeBar.classList.remove('muted');
    setStatus('disconnected', 'Desconectado');
    
    // Limpar timer
    if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
}
```

Modificar `start()`: após `started = true`:
```javascript
startBtn.style.display = 'none';
document.getElementById('disconnectBtn').style.display = '';
```

---

## FEATURE 2: Botão Interrupt Manual

### Frontend (`static/index.html`):

Adicionar botão na `div.controls`:
- ID: `interruptBtn`
- Texto: "⏹️"
- Invisível por padrão
- Aparece durante `thinking` e `speaking`

```javascript
function manualInterrupt() {
    stopPlayback();
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'interrupt'}));
    }
}
```

No `handleStatus()` ou `setStatus()`, mostrar/esconder:
```javascript
const interruptBtn = document.getElementById('interruptBtn');
if (interruptBtn) {
    interruptBtn.style.display = (status === 'thinking' || status === 'speaking') ? '' : 'none';
}
```

Backend: nenhuma mudança (handler de `{type: "interrupt"}` já existe).

---

## FEATURE 3: Input de Texto via WebSocket

### Backend (`server_ws.py`):

**Primeiro: refatorar** o bloco de LLM streaming + TTS de `process_speech()` pra uma função auxiliar:

```python
async def _llm_and_tts(user_text, ws, send_json_msg, send_status, chat_history, cancel_event, TOKEN):
    """LLM streaming + TTS por frase. Compartilhado entre voz e texto."""
    # Mover TODO o bloco desde "api_history = build_api_history..." até o final
    # do process_speech() pra cá. Retornar (full_response, chat_history atualizado).
    ...
```

Depois `process_speech()` faz: STT → chama `_llm_and_tts(transcript, ...)`

**Adicionar handler** no receive loop:
```python
elif data["type"] == "text_input":
    user_text = data.get("text", "").strip()
    if user_text and not processing:
        process_task = asyncio.create_task(process_text(user_text))
```

**Implementar `process_text()`:**
```python
async def process_text(user_text):
    nonlocal processing, chat_history
    processing = True
    cancel_event.clear()
    try:
        await send_json_msg({"type": "transcript", "text": user_text, "source": "text"})
        await send_status("thinking")
        chat_history.append({"role": "user", "content": user_text})
        # Chamar o mesmo _llm_and_tts() que process_speech() usa
        await _llm_and_tts(user_text, ...)
    except Exception as e:
        traceback.print_exc()
        await send_json_msg({"type": "error", "message": f"Erro: {e}"})
    finally:
        processing = False
        if not cancel_event.is_set():
            await send_status("listening")
```

### Frontend (`static/index.html`):

HTML — abaixo da bottom-bar, antes do error-toast:
```html
<div class="text-input-bar" id="textInputBar" style="display:none">
    <input type="text" id="textInput" placeholder="Digite sua mensagem..."
           autocomplete="off" maxlength="2000">
    <button class="btn" id="textSendBtn" onclick="sendText()">Enviar</button>
</div>
```

CSS:
```css
.text-input-bar {
    background: #16162a; padding: 8px 16px; display: flex; gap: 8px;
    border-top: 1px solid #2d2d44; flex-shrink: 0;
}
.text-input-bar input {
    flex: 1; background: #2d2d44; border: 1px solid #3d3d54; color: #e0e0e0;
    padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; outline: none;
}
.text-input-bar input:focus { border-color: #4caf50; }
```

JavaScript:
```javascript
let pendingTextInput = false;

function sendText() {
    const input = document.getElementById('textInput');
    const text = input.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    addUserMessage(text);
    input.value = '';
    pendingTextInput = true;
    ws.send(JSON.stringify({type: 'text_input', text: text}));
}

// Enter pra enviar:
document.getElementById('textInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); }
});
```

Mostrar/esconder com conexão:
- `ws.onopen`: `document.getElementById('textInputBar').style.display = 'flex';`
- `disconnect()`: já incluído acima

No handler de `transcript`: se `pendingTextInput` é true, não duplicar a mensagem do user. Resetar flag quando receber `status: "listening"`.

Desabilitar input durante thinking/speaking:
```javascript
// Em handleStatus():
const textInput = document.getElementById('textInput');
if (textInput) {
    textInput.disabled = (status === 'thinking' || status === 'speaking');
    if (status === 'listening') { pendingTextInput = false; }
}
```

---

## FEATURE 4: Timer "Pensando..."

### Frontend (`static/index.html`):

```javascript
let thinkingTimer = null;
let thinkingStartTime = 0;
```

No `handleStatus()` quando status é `thinking`:
```javascript
thinkingStartTime = Date.now();
if (thinkingTimer) clearInterval(thinkingTimer);
thinkingTimer = setInterval(() => {
    const elapsed = ((Date.now() - thinkingStartTime) / 1000).toFixed(1);
    bottomStatus.textContent = `Pensando... ${elapsed}s`;
}, 100);
bottomStatus.textContent = 'Pensando... 0.0s';
```

Em TODOS os outros cases + no `disconnect()`:
```javascript
if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
```

---

## FEATURE 5: Fix Visual do Mute

### Frontend (`static/index.html`):

Em `processAudioChunk()`: mover atualização de `volumeBar` pra DEPOIS do check de mute. Barge-in fica ANTES (funciona mesmo mutado):

```javascript
function processAudioChunk(float32Array) {
    let sum = 0;
    for (let i = 0; i < float32Array.length; i++) sum += float32Array[i] * float32Array[i];
    const rms = Math.sqrt(sum / float32Array.length);

    // Barge-in: funciona mesmo mutado
    if (isPlaying && rms > VAD_THRESHOLD * 3) {
        stopPlayback();
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: 'interrupt'}));
    }

    // Se mutado: zerar barra
    if (isMuted) {
        volumeBar.style.width = '0%';
        return;
    }

    // Atualizar visualização (só quando não mutado)
    const pct = Math.min(rms / 0.1, 1) * 100;
    volumeBar.style.width = pct + '%';
    // ... resto do VAD inalterado
}
```

Em `toggleMute()`:
```javascript
function toggleMute() {
    isMuted = !isMuted;
    micBtn.classList.toggle('active', isMuted);
    micBtn.textContent = isMuted ? '🔇' : '🎤';
    if (isMuted) volumeBar.style.width = '0%';
    volumeBar.classList.toggle('muted', isMuted);
}
```

CSS:
```css
.volume-bar.muted {
    background: #666 !important; width: 100% !important; opacity: 0.3;
}
```

---

## FEATURE 6: Esfera Pulsante (CSS)

### Frontend (`static/index.html`):

HTML — entre `.status-bar` e `.chat-container`:
```html
<div class="orb-container" id="orbContainer" style="display:none">
    <div class="orb" id="orb"><div class="orb-inner"></div></div>
</div>
```

CSS:
```css
.orb-container {
    display: flex; justify-content: center; align-items: center;
    padding: 24px 0; flex-shrink: 0;
}
.orb {
    width: 80px; height: 80px; border-radius: 50%; position: relative;
    display: flex; justify-content: center; align-items: center;
    transition: box-shadow 0.3s, transform 0.3s;
}
.orb-inner {
    width: 60px; height: 60px; border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #4a4a6a, #2d2d44);
    transition: background 0.3s;
}
.orb.disconnected { box-shadow: 0 0 20px rgba(100,100,100,0.3); }
.orb.disconnected .orb-inner { background: radial-gradient(circle at 35% 35%, #3a3a4a, #2d2d44); }

.orb.listening { box-shadow: 0 0 20px rgba(76,175,80,0.4); animation: orb-breathe 3s ease-in-out infinite; }
.orb.listening .orb-inner { background: radial-gradient(circle at 35% 35%, #4caf50, #2d6b30); }

.orb.thinking { box-shadow: 0 0 25px rgba(255,152,0,0.5); animation: orb-think 1.2s ease-in-out infinite; }
.orb.thinking .orb-inner { background: radial-gradient(circle at 35% 35%, #ff9800, #b36b00); }

.orb.speaking { box-shadow: 0 0 30px rgba(33,150,243,0.5); animation: orb-speak 0.8s ease-in-out infinite; }
.orb.speaking .orb-inner { background: radial-gradient(circle at 35% 35%, #2196f3, #1565c0); }

@keyframes orb-breathe {
    0%, 100% { transform: scale(1); box-shadow: 0 0 20px rgba(76,175,80,0.3); }
    50% { transform: scale(1.05); box-shadow: 0 0 35px rgba(76,175,80,0.5); }
}
@keyframes orb-think {
    0%, 100% { transform: scale(1); box-shadow: 0 0 25px rgba(255,152,0,0.4); }
    50% { transform: scale(1.08); box-shadow: 0 0 40px rgba(255,152,0,0.7); }
}
@keyframes orb-speak {
    0%, 100% { transform: scale(1); box-shadow: 0 0 30px rgba(33,150,243,0.4); }
    50% { transform: scale(1.1); box-shadow: 0 0 45px rgba(33,150,243,0.7); }
}

.orb.listening.vol-low { transform: scale(1.02); }
.orb.listening.vol-mid { transform: scale(1.08); }
.orb.listening.vol-high { transform: scale(1.15); box-shadow: 0 0 50px rgba(76,175,80,0.7); }

@media (max-width: 600px) {
    .orb { width: 60px; height: 60px; }
    .orb-inner { width: 45px; height: 45px; }
    .orb-container { padding: 16px 0; }
}
```

JavaScript:

Na função `setStatus()`:
```javascript
const orb = document.getElementById('orb');
if (orb) orb.className = 'orb ' + cls;
```

Na `processAudioChunk()`, após calcular `pct` (antes do mute check):
```javascript
const orb = document.getElementById('orb');
if (orb && orb.classList.contains('listening') && !isMuted) {
    orb.classList.remove('vol-low', 'vol-mid', 'vol-high');
    if (pct > 60) orb.classList.add('vol-high');
    else if (pct > 25) orb.classList.add('vol-mid');
    else if (pct > 5) orb.classList.add('vol-low');
}
```

Mostrar: `ws.onopen` → `orbContainer.style.display = 'flex'`
Esconder: `disconnect()` → já incluído acima

---

## FEATURE 7: Markdown nas Respostas

### Frontend (`static/index.html`):

Adicionar no `<head>`:
```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
```

CSS para markdown dentro de mensagens assistant:
```css
.message.assistant .text { line-height: 1.6; }
.message.assistant .text p { margin: 0 0 8px 0; }
.message.assistant .text p:last-child { margin-bottom: 0; }
.message.assistant .text code {
    background: #1a1a2e; padding: 2px 6px; border-radius: 4px;
    font-family: 'Courier New', monospace; font-size: 0.85em;
}
.message.assistant .text pre {
    background: #1a1a2e; padding: 10px; border-radius: 6px;
    overflow-x: auto; margin: 8px 0;
}
.message.assistant .text pre code { background: none; padding: 0; }
.message.assistant .text ul, .message.assistant .text ol { margin: 4px 0; padding-left: 20px; }
.message.assistant .text strong { color: #fff; }
.message.assistant .text a { color: #4caf50; text-decoration: none; }
.message.assistant .text a:hover { text-decoration: underline; }
```

Configurar marked no início do script:
```javascript
if (typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true });
}
```

Modificar `updateAssistantMessage()` — trocar `.textContent` por markdown:
```javascript
const textEl = currentAssistantEl.querySelector('.text');
if (typeof marked !== 'undefined') {
    textEl.innerHTML = marked.parse(text);
} else {
    textEl.textContent = text;
}
```

Mensagens do user continuam `.textContent` (não renderizar markdown do input).

---

## FEATURE 8: Painel de Configuração

### Frontend (`static/index.html`):

Botão ⚙️ no `.status-bar`:
```html
<button class="btn config-toggle" id="configToggle" onclick="toggleConfig()" title="Configurações">⚙️</button>
```

Painel (entre `.status-bar` e `.orb-container`):
```html
<div class="config-panel" id="configPanel" style="display:none">
    <div class="config-group">
        <label for="cfgGateway">Gateway URL</label>
        <input type="text" id="cfgGateway" placeholder="http://127.0.0.1:18789/v1/chat/completions">
        <small>Deixe vazio para auto-detectar. Aplica no próximo reload.</small>
    </div>
    <div class="config-group">
        <label for="cfgVolume">Volume da resposta</label>
        <div class="config-row">
            <input type="range" id="cfgVolume" min="0" max="100" value="100">
            <span id="cfgVolumeLabel">100%</span>
        </div>
    </div>
    <div class="config-group">
        <label for="cfgWhisper">Modelo de transcrição</label>
        <select id="cfgWhisper">
            <option value="tiny">Tiny — rápido, menos preciso</option>
            <option value="small" selected>Small — equilibrado</option>
            <option value="medium">Medium — lento, mais preciso</option>
        </select>
        <small>Aplica na reconexão.</small>
    </div>
    <button class="btn" onclick="saveConfig()">Salvar</button>
</div>
```

CSS:
```css
.config-toggle { font-size: 1.2rem; padding: 4px 8px; background: transparent; }
.config-toggle:hover { background: #2d2d44; }
.config-panel {
    background: #16162a; border-bottom: 1px solid #2d2d44; padding: 16px; flex-shrink: 0;
}
.config-group { margin-bottom: 12px; }
.config-group label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; color: #ccc; }
.config-group small { display: block; font-size: 0.75rem; color: #888; margin-top: 2px; }
.config-row { display: flex; align-items: center; gap: 8px; }
.config-panel input[type="text"] {
    width: 100%; background: #2d2d44; border: 1px solid #3d3d54; color: #e0e0e0;
    padding: 6px 10px; border-radius: 6px; font-size: 0.85rem;
}
.config-panel input[type="text"]:focus { border-color: #4caf50; outline: none; }
.config-panel select {
    width: 100%; background: #2d2d44; border: 1px solid #3d3d54; color: #e0e0e0;
    padding: 6px 10px; border-radius: 6px; font-size: 0.85rem;
}
```

JavaScript:
```javascript
function toggleConfig() {
    const panel = document.getElementById('configPanel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

function loadConfig() {
    const gw = localStorage.getItem('ova_gateway_url');
    const vol = localStorage.getItem('ova_volume');
    const whisper = localStorage.getItem('ova_whisper_model');
    if (gw) document.getElementById('cfgGateway').value = gw;
    if (vol) {
        document.getElementById('cfgVolume').value = vol;
        document.getElementById('cfgVolumeLabel').textContent = vol + '%';
    }
    if (whisper) document.getElementById('cfgWhisper').value = whisper;
}

function saveConfig() {
    const gw = document.getElementById('cfgGateway').value.trim();
    const vol = document.getElementById('cfgVolume').value;
    const whisper = document.getElementById('cfgWhisper').value;
    if (gw) localStorage.setItem('ova_gateway_url', gw);
    else localStorage.removeItem('ova_gateway_url');
    localStorage.setItem('ova_volume', vol);
    localStorage.setItem('ova_whisper_model', whisper);
    // Enviar whisper pro server
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'config', whisper_model: whisper}));
    }
}

// Volume em tempo real via GainNode
document.getElementById('cfgVolume').addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    document.getElementById('cfgVolumeLabel').textContent = val + '%';
    if (window._playbackGain) window._playbackGain.gain.value = val / 100;
});

loadConfig();
```

Volume GainNode: no `startMic()`, após criar `audioContext`:
```javascript
const gainNode = audioContext.createGain();
gainNode.connect(audioContext.destination);
window._playbackGain = gainNode;
const savedVol = localStorage.getItem('ova_volume');
if (savedVol) gainNode.gain.value = parseInt(savedVol) / 100;
```

Modificar `playNext()` — conectar ao gainNode:
```javascript
if (window._playbackGain) source.connect(window._playbackGain);
else source.connect(playbackContext.destination);
```

### Backend (`server_ws.py`) — handler de config:

Substituir `elif data["type"] == "config": pass` por:
```python
elif data["type"] == "config":
    whisper_model = data.get("whisper_model")
    if whisper_model and whisper_model in ("tiny", "small", "medium"):
        from core.stt import set_whisper_model
        set_whisper_model(whisper_model)
        print(f"[CONFIG] Whisper → {whisper_model}")
```

### Backend (`core/stt.py`) — adicionar `set_whisper_model()`:

```python
_whisper_model_size = WHISPER_MODEL_SIZE  # cópia mutável

def set_whisper_model(model_name):
    global _whisper_model, _whisper_model_size
    if model_name in ("tiny", "small", "medium") and model_name != _whisper_model_size:
        old = _whisper_model_size
        _whisper_model_size = model_name
        _whisper_model = None
        print(f"[STT] Whisper: {old} → {model_name}")

def get_current_model():
    return _whisper_model_size
```

Atualizar `_get_whisper()` e `init_stt()` pra usar `_whisper_model_size` em vez de `WHISPER_MODEL_SIZE`.

---

## O que NÃO fazer

- NÃO usar framework JS (React, Vue) — tudo JS puro
- NÃO mudar lógica de VAD, barge-in automático, ou streaming LLM
- NÃO mudar fallback chain do TTS
- NÃO mexer em `voice_assistant_app.py` ou `voice_assistant_cli.py`
- NÃO duplicar lógica LLM+TTS — EXTRAIR pra função compartilhada
- NÃO fazer a esfera clicável (é feedback visual, não botão)
- NÃO remover nenhum botão ou função existente

---

## Critérios de sucesso (todos devem passar)

### Disconnect + Interrupt:
- [ ] "Iniciar" → some, aparece "Encerrar"
- [ ] "Encerrar" → fecha WS, para mic, para playback, volta ao estado inicial
- [ ] Após encerrar, "Iniciar" funciona de novo
- [ ] "⏹️" aparece durante thinking/speaking, some em listening
- [ ] Clicar "⏹️" para a resposta
- [ ] Auto-reconnect funciona quando WS cai (mas NÃO quando clica Encerrar)

### Input de texto:
- [ ] Campo de texto aparece quando conectado
- [ ] Enter ou botão Enviar → mensagem vai pro server
- [ ] Resposta aparece no chat + áudio toca
- [ ] Mensagem não duplica
- [ ] Voz continua funcionando junto

### Timer + Mute:
- [ ] "Pensando... X.Xs" atualiza em tempo real
- [ ] Quando mutado: barra cinza, sem atualização
- [ ] Desmutado: barra volta verde

### Esfera:
- [ ] Verde respirando (listening), laranja pulsando (thinking), azul pulsando (speaking)
- [ ] Reage ao volume do mic
- [ ] Some ao desconectar, aparece ao conectar

### Markdown:
- [ ] Bold, listas, code blocks renderizam
- [ ] Fallback pra texto puro se marked.js não carregar

### Config:
- [ ] ⚙️ abre/fecha painel
- [ ] Volume muda em tempo real
- [ ] Whisper model envia pro server
- [ ] Gateway URL salva no localStorage

### Geral:
- [ ] `python -m pytest tests/ -v` — todos os testes passam
