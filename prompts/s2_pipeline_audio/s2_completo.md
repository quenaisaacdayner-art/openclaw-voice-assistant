# S2: Pipeline de Áudio — PROMPT COMPLETO

> Prompt unificado. Leia e execute TUDO.
> Pré-requisito: S1 completo (config panel, server_info handler, etc. já existem)
> Arquivos a modificar: `core/config.py`, `core/stt.py`, `core/tts.py`, `server_ws.py`, `static/index.html`

---

## Visão geral

3 features de pipeline de áudio:

1. Whisper tiny → small (melhor transcrição) + banner TTS no startup + server_info via WS
2. Seletor de vozes TTS (masculina/feminina, por engine)
3. Slider de velocidade TTS (0.5x a 2.0x)

---

## FEATURE 1: Whisper small + Banner + server_info

### `core/config.py` — mudar default:

```python
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
```

### `core/stt.py` — variável mutável + set/get:

Adicionar no topo (após imports):
```python
_whisper_model_size = WHISPER_MODEL_SIZE  # cópia mutável
```

Modificar `_get_whisper()` pra usar `_whisper_model_size` em vez de `WHISPER_MODEL_SIZE`:
```python
def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                print(f"⏳ Carregando Whisper ({_whisper_model_size})...")
                _whisper_model = WhisperModel(_whisper_model_size, device="cpu", compute_type="int8")
                print("✅ Whisper pronto")
    return _whisper_model
```

Modificar `init_stt()` pra usar `_whisper_model_size`.

Adicionar funções (se S1 não as criou — verificar antes de duplicar):
```python
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

### `server_ws.py` — banner TTS + server_info:

**Banner:** após `init_tts()` e `warmup_tts()`, ANTES do "servidor pronto":
```python
from core.tts import _tts_engine, kokoro_instance, piper_voice, KOKORO_VOICE
from core.stt import get_current_model

if _tts_engine == "kokoro" and kokoro_instance is not None:
    tts_info = f"Kokoro (voz: {KOKORO_VOICE}, local)"
elif _tts_engine == "piper" and piper_voice is not None:
    tts_info = "Piper (faber-medium, local)"
elif _tts_engine == "edge":
    from core.tts import _edge_voice
    tts_info = f"Edge TTS ({_edge_voice}, online)"
else:
    tts_info = f"{_tts_engine} (desconhecido)"
print(f"🔊 TTS Engine: {tts_info}")
```

**server_info:** no WebSocket handler, após `accept()`:
```python
from core.tts import _tts_engine, get_available_voices, get_current_voice, get_speed
from core.stt import get_current_model

server_info = {
    "type": "server_info",
    "tts_engine": _tts_engine,
    "tts_voice": get_current_voice(),
    "tts_voices": get_available_voices(),
    "tts_speed": get_speed(),
    "whisper_model": get_current_model(),
}
await websocket.send_json(server_info)
```

### Frontend (`static/index.html`) — handler server_info:

No `ws.onmessage`, adicionar handler:
```javascript
if (data.type === 'server_info') {
    console.log('Server info:', data);
    window._serverInfo = data;
    
    // Engine label
    const engineLabel = document.getElementById('cfgEngineLabel');
    if (engineLabel) {
        const names = {kokoro: 'Kokoro (local, neural)', edge: 'Edge TTS (online)', piper: 'Piper (local)'};
        engineLabel.textContent = 'Engine: ' + (names[data.tts_engine] || data.tts_engine);
    }
    
    // Popular vozes
    const voiceSelect = document.getElementById('cfgVoice');
    if (voiceSelect && data.tts_voices) {
        voiceSelect.innerHTML = '';
        data.tts_voices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.name;
            if (v.id === data.tts_voice) opt.selected = true;
            voiceSelect.appendChild(opt);
        });
        voiceSelect.disabled = data.tts_voices.length <= 1;
    }
    
    // Velocidade
    const speedSlider = document.getElementById('cfgSpeed');
    const speedLabel = document.getElementById('cfgSpeedLabel');
    if (speedSlider && data.tts_speed !== undefined) {
        speedSlider.value = data.tts_speed;
        speedLabel.textContent = data.tts_speed.toFixed(1) + 'x';
    }
    
    return;
}
```

---

## FEATURE 2: Seletor de Vozes TTS

### `core/tts.py` — vozes configuráveis:

Adicionar constantes (após imports e constantes existentes):
```python
AVAILABLE_VOICES = {
    "kokoro": [
        {"id": "pm_alex", "name": "Alex (Masculino)", "gender": "M"},
        {"id": "pf_dora", "name": "Dora (Feminino)", "gender": "F"},
    ],
    "edge": [
        {"id": "pt-BR-AntonioNeural", "name": "Antonio (Masculino)", "gender": "M"},
        {"id": "pt-BR-FranciscaNeural", "name": "Francisca (Feminino)", "gender": "F"},
        {"id": "pt-BR-ThalitaNeural", "name": "Thalita (Feminino)", "gender": "F"},
        {"id": "pt-BR-BrendaNeural", "name": "Brenda (Feminino)", "gender": "F"},
        {"id": "pt-BR-DonatoNeural", "name": "Donato (Masculino)", "gender": "M"},
        {"id": "pt-BR-ElzaNeural", "name": "Elza (Feminino)", "gender": "F"},
    ],
    "piper": [
        {"id": "pt_BR-faber-medium", "name": "Faber (Masculino)", "gender": "M"},
    ],
}
```

Adicionar variáveis mutáveis:
```python
_kokoro_voice = KOKORO_VOICE   # default: "pm_alex"
_edge_voice = TTS_VOICE        # default: "pt-BR-AntonioNeural"
_tts_speed = 1.0               # 0.5 a 2.0
```

Adicionar funções:
```python
def get_available_voices():
    return AVAILABLE_VOICES.get(_tts_engine, [])

def get_current_voice():
    if _tts_engine == "kokoro": return _kokoro_voice
    elif _tts_engine == "edge": return _edge_voice
    elif _tts_engine == "piper": return "pt_BR-faber-medium"
    return ""

def set_voice(voice_id):
    global _kokoro_voice, _edge_voice
    available = AVAILABLE_VOICES.get(_tts_engine, [])
    valid_ids = [v["id"] for v in available]
    if voice_id not in valid_ids:
        print(f"[TTS] Voz '{voice_id}' inválida. Disponíveis: {valid_ids}")
        return False
    if _tts_engine == "kokoro":
        old = _kokoro_voice; _kokoro_voice = voice_id
        print(f"[TTS] Voz: {old} → {voice_id}")
    elif _tts_engine == "edge":
        old = _edge_voice; _edge_voice = voice_id
        print(f"[TTS] Voz: {old} → {voice_id}")
    else:
        return False
    return True

def get_speed():
    return _tts_speed

def set_speed(speed):
    global _tts_speed
    speed = max(0.5, min(2.0, float(speed)))
    old = _tts_speed
    _tts_speed = speed
    if old != speed: print(f"[TTS] Velocidade: {old}x → {speed}x")
    return True
```

Modificar `generate_tts_kokoro()`:
```python
samples, sample_rate = kokoro_instance.create(
    text, voice=_kokoro_voice, speed=_tts_speed, lang=KOKORO_LANG
)
```

Modificar `generate_tts_edge()`:
```python
edge_rate = ""
if _tts_speed != 1.0:
    pct = round((_tts_speed - 1.0) * 100)
    edge_rate = f"+{pct}%" if pct > 0 else f"{pct}%"
communicate = edge_tts.Communicate(text, _edge_voice, rate=edge_rate)
```

**⚠️ Verificar:** se `edge_tts.Communicate()` aceita `rate` como kwarg. Se não, documentar e ignorar velocidade pra Edge (não quebrar).

---

## FEATURE 3: Slider de Velocidade + Dropdown de Vozes no Config Panel

### Frontend (`static/index.html`) — adicionar ao config panel (S1 já criou a estrutura):

Adicionar APÓS o grupo do Whisper model:

```html
<div class="config-group">
    <label>Voz da resposta</label>
    <span class="config-engine" id="cfgEngineLabel">Engine: —</span>
    <select id="cfgVoice"><option value="">Conecte para ver vozes</option></select>
    <small>Muda imediatamente na próxima resposta.</small>
</div>
<div class="config-group">
    <label for="cfgSpeed">Velocidade da fala</label>
    <div class="config-row">
        <input type="range" id="cfgSpeed" min="0.5" max="2.0" step="0.1" value="1.0">
        <span id="cfgSpeedLabel">1.0x</span>
    </div>
    <small>0.5x (lento) a 2.0x (rápido). Piper ignora esta configuração.</small>
</div>
```

CSS adicional:
```css
.config-engine { font-size: 0.8rem; color: #4caf50; font-weight: 600; display: block; margin-bottom: 4px; }
```

### JavaScript — listeners:

```javascript
// Voz
document.getElementById('cfgVoice').addEventListener('change', (e) => {
    if (e.target.value && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'config', tts_voice: e.target.value}));
    }
});

// Velocidade: label em tempo real
document.getElementById('cfgSpeed').addEventListener('input', (e) => {
    document.getElementById('cfgSpeedLabel').textContent = parseFloat(e.target.value).toFixed(1) + 'x';
});
// Velocidade: enviar ao server ao soltar
document.getElementById('cfgSpeed').addEventListener('change', (e) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'config', tts_speed: parseFloat(e.target.value)}));
    }
});
```

### Backend (`server_ws.py`) — expandir handler de config:

```python
elif data["type"] == "config":
    whisper_model = data.get("whisper_model")
    if whisper_model and whisper_model in ("tiny", "small", "medium"):
        from core.stt import set_whisper_model
        set_whisper_model(whisper_model)
    
    voice = data.get("tts_voice")
    if voice:
        from core.tts import set_voice
        set_voice(voice)
    
    speed = data.get("tts_speed")
    if speed is not None:
        from core.tts import set_speed
        set_speed(float(speed))
```

---

## O que NÃO fazer

- NÃO instalar PyTorch ou distil-whisper (CPU-only, small é suficiente)
- NÃO mudar fallback chain TTS (kokoro → piper → edge)
- NÃO mudar `language="pt"` no transcribe (já está correto em stt.py)
- NÃO permitir trocar ENGINE via UI (só voz dentro do engine ativo)
- NÃO mexer em `voice_assistant_app.py` ou `voice_assistant_cli.py`
- NÃO duplicar funções — se S1 já criou `set_whisper_model` e `get_current_model` em stt.py, NÃO recriar
- NÃO mexer na lógica de streaming, barge-in, VAD, ou history

---

## Critérios de sucesso

### Whisper + Banner:
- [ ] Default mudou pra small (verificar startup: "Carregando Whisper (small)")
- [ ] Startup mostra "🔊 TTS Engine: ..." com engine ativo
- [ ] `WHISPER_MODEL=tiny` env var override funciona
- [ ] `server_info` é enviado via WS ao conectar (verificar DevTools console)

### Vozes:
- [ ] Dropdown populado com vozes do engine ativo ao conectar
- [ ] Mudar voz → próxima resposta usa voz nova
- [ ] Piper → dropdown desabilitado (1 voz)
- [ ] Kokoro → Alex e Dora disponíveis
- [ ] Edge → 6 vozes disponíveis
- [ ] Engine label mostra qual engine

### Velocidade:
- [ ] Slider 0.5x-2.0x no config panel
- [ ] Label atualiza em tempo real
- [ ] 1.5x → resposta mais rápida
- [ ] 0.7x → resposta mais devagar
- [ ] Server log: "[TTS] Velocidade: 1.0x → 1.5x"

### Geral:
- [ ] `python -m pytest tests/ -v` — todos os testes passam
- [ ] Reconectar → dropdown + slider re-populados via server_info
