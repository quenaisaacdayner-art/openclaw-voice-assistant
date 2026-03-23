# S1-E: Markdown nas Respostas + Painel de Configuração

> Prompt auto-contido. Leia e execute.
> Pré-requisito: S1-A, S1-B, S1-C, S1-D executados
> Arquivos a modificar: `static/index.html`, `server_ws.py` (minor)

---

## Contexto

O frontend mostra respostas do LLM como texto puro (`.textContent`). O LLM frequentemente responde com markdown (bold, listas, code blocks). Precisamos renderizar isso.

Também precisamos de um painel de configuração simples pra que pessoas que não sabem código possam ajustar o essencial: Gateway URL (quando auto-detect falha), volume do áudio, modelo do Whisper.

---

## Tarefa 1: Markdown nas Respostas

### Abordagem: marked.js (CDN)

`marked` é uma lib leve (~35KB) que converte markdown em HTML. Segura com sanitização.

### HTML — adicionar no `<head>`, antes do `<style>`:

```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
```

### CSS — adicionar estilos pra markdown dentro de mensagens:

```css
.message.assistant .text {
    line-height: 1.6;
}
.message.assistant .text p {
    margin: 0 0 8px 0;
}
.message.assistant .text p:last-child {
    margin-bottom: 0;
}
.message.assistant .text code {
    background: #1a1a2e;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 0.85em;
}
.message.assistant .text pre {
    background: #1a1a2e;
    padding: 10px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 8px 0;
}
.message.assistant .text pre code {
    background: none;
    padding: 0;
}
.message.assistant .text ul, .message.assistant .text ol {
    margin: 4px 0;
    padding-left: 20px;
}
.message.assistant .text strong {
    color: #fff;
}
.message.assistant .text a {
    color: #4caf50;
    text-decoration: none;
}
.message.assistant .text a:hover {
    text-decoration: underline;
}
```

### JavaScript:

1. Configurar marked (seguro):
   ```javascript
   // No início do <script>, após as variáveis de estado
   if (typeof marked !== 'undefined') {
       marked.setOptions({
           breaks: true,      // \n vira <br>
           gfm: true,         // GitHub Flavored Markdown
           sanitize: false,   // marked v5+ usa DOMPurify se quiser — não tem sanitize option nativa
       });
   }
   ```

2. Modificar `updateAssistantMessage()`:

   Trocar `.textContent` por markdown renderizado:
   ```javascript
   function updateAssistantMessage(text, done) {
       if (!currentAssistantEl) {
           currentAssistantEl = document.createElement('div');
           currentAssistantEl.className = 'message assistant';
           currentAssistantEl.innerHTML = `<div class="label">OpenClaw</div><span class="text"></span>`;
           chat.appendChild(currentAssistantEl);
       }
       const textEl = currentAssistantEl.querySelector('.text');
       if (typeof marked !== 'undefined') {
           textEl.innerHTML = marked.parse(text);
       } else {
           textEl.textContent = text;  // Fallback se marked não carregou (offline)
       }
       scrollChat();
       if (done) {
           currentAssistantEl = null;
       }
   }
   ```

3. **⚠️ XSS:** `marked.parse()` converte markdown em HTML que é inserido via `innerHTML`. O texto vem do LLM (nosso server), não de input externo. Risco baixo. Se quiser sanitizar, adicionar DOMPurify (CDN), mas é overkill pra este caso.

4. Mensagens do user continuam como `.textContent` (não renderizar markdown no que o usuário digitou — manter `escapeHtml()`).

---

## Tarefa 2: Painel de Configuração

### Conceito

Um painel colapsável (accordion) que fica ACIMA do chat. Fechado por padrão. Toggle via ícone ⚙️ no header.

**Configs:**
1. **Gateway URL** — input text. Valor default: auto-detect. Salva em localStorage. Aplicado no próximo reload.
2. **Volume do áudio** — slider (0-100%). Aplicado em tempo real via Web Audio gain.
3. **Modelo Whisper** — select (tiny/small/medium). Salva em localStorage. Enviado pro server via WS `{type: "config"}` no connect.

### HTML — botão de config no header:

Adicionar no `.status-bar`, ANTES do `.status-indicator`:
```html
<button class="btn config-toggle" id="configToggle" onclick="toggleConfig()" title="Configurações">⚙️</button>
```

### HTML — painel de config, ENTRE `.status-bar` e `.orb-container`:

```html
<div class="config-panel" id="configPanel" style="display:none">
    <div class="config-group">
        <label for="cfgGateway">Gateway URL</label>
        <div class="config-row">
            <input type="text" id="cfgGateway" placeholder="http://127.0.0.1:18789/v1/chat/completions">
            <span class="config-status" id="cfgGatewayStatus"></span>
        </div>
        <small>Deixe vazio para auto-detectar. Mude se a conexão automática falhar. Aplica no próximo reload.</small>
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
            <option value="small">Small — equilibrado</option>
            <option value="medium">Medium — lento, mais preciso</option>
        </select>
        <small>Aplica na próxima sessão (requer reconexão).</small>
    </div>

    <button class="btn" onclick="saveConfig()">Salvar configurações</button>
</div>
```

### CSS:

```css
.config-toggle {
    font-size: 1.2rem;
    padding: 4px 8px;
    background: transparent;
}
.config-toggle:hover {
    background: #2d2d44;
}

.config-panel {
    background: #16162a;
    border-bottom: 1px solid #2d2d44;
    padding: 16px;
    flex-shrink: 0;
}
.config-group {
    margin-bottom: 12px;
}
.config-group label {
    display: block;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 4px;
    color: #ccc;
}
.config-group small {
    display: block;
    font-size: 0.75rem;
    color: #888;
    margin-top: 2px;
}
.config-row {
    display: flex;
    align-items: center;
    gap: 8px;
}
.config-panel input[type="text"] {
    flex: 1;
    background: #2d2d44;
    border: 1px solid #3d3d54;
    color: #e0e0e0;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.85rem;
}
.config-panel input[type="text"]:focus {
    border-color: #4caf50;
    outline: none;
}
.config-panel input[type="range"] {
    flex: 1;
}
.config-panel select {
    width: 100%;
    background: #2d2d44;
    border: 1px solid #3d3d54;
    color: #e0e0e0;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.85rem;
}
.config-status {
    font-size: 0.8rem;
}
```

### JavaScript:

1. **Toggle do painel:**
   ```javascript
   function toggleConfig() {
       const panel = document.getElementById('configPanel');
       panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
   }
   ```

2. **Carregar configs do localStorage no load:**
   ```javascript
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
   // Chamar no final do script:
   loadConfig();
   ```

3. **Salvar configs:**
   ```javascript
   function saveConfig() {
       const gw = document.getElementById('cfgGateway').value.trim();
       const vol = document.getElementById('cfgVolume').value;
       const whisper = document.getElementById('cfgWhisper').value;

       if (gw) {
           localStorage.setItem('ova_gateway_url', gw);
       } else {
           localStorage.removeItem('ova_gateway_url');
       }
       localStorage.setItem('ova_volume', vol);
       localStorage.setItem('ova_whisper_model', whisper);

       // Feedback visual
       showError('✅ Configurações salvas. Recarregue para aplicar Gateway/Whisper.');
       // Nota: showError é reaproveitado aqui — o toast funciona pra qualquer mensagem.
       // Se quiser, criar um toast de sucesso separado (verde em vez de vermelho).
       // Por ora, funciona.
   }
   ```

4. **Volume em tempo real (Web Audio GainNode):**

   No `startMic()`, após criar `audioContext`:
   ```javascript
   // Criar gain node pra controlar volume do playback
   const gainNode = audioContext.createGain();
   gainNode.connect(audioContext.destination);
   // Armazenar referência global
   window._playbackGain = gainNode;

   // Aplicar volume salvo
   const savedVol = localStorage.getItem('ova_volume');
   if (savedVol) {
       gainNode.gain.value = parseInt(savedVol) / 100;
   }
   ```

   Modificar `playNext()` — conectar ao gainNode em vez de direto ao destination:
   ```javascript
   function playNext() {
       if (playbackQueue.length === 0) { isPlaying = false; currentSource = null; return; }
       isPlaying = true;
       const buffer = playbackQueue.shift();
       const source = playbackContext.createBufferSource();
       currentSource = source;
       source.buffer = buffer;
       // Conectar ao gain node pra controle de volume
       if (window._playbackGain) {
           source.connect(window._playbackGain);
       } else {
           source.connect(playbackContext.destination);
       }
       source.onended = () => playNext();
       source.start();
   }
   ```

   Slider de volume atualiza em tempo real:
   ```javascript
   document.getElementById('cfgVolume').addEventListener('input', (e) => {
       const val = parseInt(e.target.value);
       document.getElementById('cfgVolumeLabel').textContent = val + '%';
       if (window._playbackGain) {
           window._playbackGain.gain.value = val / 100;
       }
   });
   ```

5. **Enviar Whisper model pro server no connect:**

   Modificar `connect()` — após `ws.onopen`:
   ```javascript
   ws.onopen = () => {
       setStatus('connected', 'Conectado');
       bottomStatus.textContent = 'Escutando...';

       // Enviar config pro server
       const whisper = localStorage.getItem('ova_whisper_model');
       if (whisper) {
           ws.send(JSON.stringify({type: 'config', whisper_model: whisper}));
       }
   };
   ```

### Backend — handler de config (`server_ws.py`):

Substituir o `elif data["type"] == "config": pass` existente por:

```python
elif data["type"] == "config":
    # Atualizar configurações em tempo real
    whisper_model = data.get("whisper_model")
    if whisper_model and whisper_model in ("tiny", "small", "medium"):
        from core.stt import set_whisper_model
        set_whisper_model(whisper_model)
        print(f"[CONFIG] Whisper model → {whisper_model}")
```

### Backend — nova função em `core/stt.py`:

Adicionar função `set_whisper_model()` que permite trocar o modelo em runtime:

```python
def set_whisper_model(model_name):
    """Muda o modelo Whisper em runtime. O próximo transcribe_audio() usará o novo modelo."""
    global _whisper_model, _whisper_model_size
    # Só recarregar se mudou
    if model_name != _whisper_model_size:
        _whisper_model_size = model_name
        _whisper_model = None  # Força recarregar no próximo uso (lazy loading)
        print(f"[STT] Modelo Whisper será alterado para '{model_name}' na próxima transcrição")
```

**⚠️ Verificar:** `core/stt.py` pode ter nomes de variáveis diferentes pro modelo global. Ler o arquivo antes de implementar e usar os nomes corretos. O conceito é: setar a variável do modelo pra `None` → no próximo `transcribe_audio()`, o lazy loading recarrega com o novo tamanho.

---

## O que NÃO fazer

- NÃO usar framework JS (React, Vue) — tudo em JS puro
- NÃO adicionar DOMPurify por enquanto (risco XSS baixo — texto vem do nosso LLM)
- NÃO permitir mudar Gateway URL em tempo real (só no reload — evita bugs de reconexão)
- NÃO colocar opções técnicas demais no painel (TTS engine, VAD params, sample rate ficam em env var)
- NÃO mexer na lógica de VAD, barge-in, ou streaming
- NÃO modificar `voice_assistant_app.py` ou `voice_assistant_cli.py`

---

## Critério de sucesso

### Markdown:
1. [ ] Resposta com **bold** renderiza como bold
2. [ ] Resposta com `code` renderiza com fundo escuro
3. [ ] Resposta com lista renderiza como lista
4. [ ] Resposta com código multilinha renderiza em bloco
5. [ ] Se marked.js não carrega (offline), texto puro como fallback
6. [ ] Mensagens do user continuam como texto puro (não renderizar markdown)

### Config:
7. [ ] Botão ⚙️ no header abre/fecha painel
8. [ ] Gateway URL salva no localStorage
9. [ ] Volume slider muda volume em tempo real
10. [ ] Modelo Whisper salva e é enviado pro server na conexão
11. [ ] Reload da página mantém as configs salvas
12. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

### Markdown:
1. Digitar "me explica o que é Python em 3 pontos" → resposta com lista renderizada
2. Digitar "mostra um exemplo de código Python" → code block renderizado
3. Verificar que texto do user NÃO renderiza markdown

### Config:
4. Clicar ⚙️ → painel abre
5. Mudar volume pra 50% → áudio da próxima resposta mais baixo
6. Colocar Gateway URL errada → salvar → recarregar → conexão falha (esperado)
7. Limpar Gateway URL → salvar → recarregar → auto-detect funciona
8. Mudar Whisper pra small → reconectar → verificar log do server "[CONFIG] Whisper model → small"
