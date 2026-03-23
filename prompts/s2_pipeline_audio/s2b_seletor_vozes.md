# S2-B: Seletor de Vozes TTS

> Prompt auto-contido. Leia e execute.
> Pré-requisito: S1-E (config panel existe) + S2-A (server_info existe) executados
> Arquivos a modificar: `core/tts.py`, `server_ws.py`, `static/index.html`

---

## Contexto

O voice assistant tem 3 engines TTS com fallback automático (Kokoro → Piper → Edge). Cada engine tem vozes PT-BR disponíveis, mas hoje está hardcoded em 1 voz por engine. O usuário não pode escolher.

O S1-E já criou um config panel no `static/index.html`. O S2-A já envia `server_info` via WebSocket no connect (com `tts_engine` ativo). Agora vamos usar essas bases pra adicionar seleção de voz.

---

## Vozes disponíveis por engine

### Kokoro (local, neural — melhor qualidade)
| ID | Gênero | Descrição |
|----|--------|-----------|
| `pm_alex` | Masculino | Voz padrão PT-BR |
| `pf_dora` | Feminino | Voz feminina PT-BR |

### Edge TTS (online, Microsoft — boa qualidade)
| ID | Gênero | Nome amigável |
|----|--------|---------------|
| `pt-BR-AntonioNeural` | Masculino | Antonio |
| `pt-BR-FranciscaNeural` | Feminino | Francisca |
| `pt-BR-ThalitaNeural` | Feminino | Thalita |
| `pt-BR-BrendaNeural` | Feminino | Brenda |
| `pt-BR-DonatoNeural` | Masculino | Donato |
| `pt-BR-ElzaNeural` | Feminino | Elza |

### Piper (local, sintético — qualidade inferior)
| ID | Gênero | Descrição |
|----|--------|-----------|
| `pt_BR-faber-medium` | Masculino | Única voz disponível |

Piper NÃO tem seleção de voz (só 1 modelo instalado). O dropdown fica desabilitado se engine for Piper.

---

## Tarefa 1: Backend — voz configurável em runtime (`core/tts.py`)

### Adicionar variáveis mutáveis no topo do módulo (junto com as existentes):

```python
_kokoro_voice = KOKORO_VOICE  # cópia mutável (default: "pm_alex")
_edge_voice = TTS_VOICE       # cópia mutável (default: "pt-BR-AntonioNeural")
```

### Adicionar constantes com vozes disponíveis:

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

### Adicionar funções de query e set:

```python
def get_available_voices():
    """Retorna vozes disponíveis pro engine TTS atual."""
    return AVAILABLE_VOICES.get(_tts_engine, [])

def get_current_voice():
    """Retorna o ID da voz atual."""
    if _tts_engine == "kokoro":
        return _kokoro_voice
    elif _tts_engine == "edge":
        return _edge_voice
    elif _tts_engine == "piper":
        return "pt_BR-faber-medium"
    return ""

def set_voice(voice_id):
    """Muda a voz TTS em runtime. Retorna True se mudou, False se inválido."""
    global _kokoro_voice, _edge_voice
    
    available = AVAILABLE_VOICES.get(_tts_engine, [])
    valid_ids = [v["id"] for v in available]
    
    if voice_id not in valid_ids:
        print(f"[TTS] Voz '{voice_id}' inválida para engine '{_tts_engine}'. Disponíveis: {valid_ids}")
        return False
    
    if _tts_engine == "kokoro":
        old = _kokoro_voice
        _kokoro_voice = voice_id
        print(f"[TTS] Voz Kokoro: {old} → {voice_id}")
    elif _tts_engine == "edge":
        old = _edge_voice
        _edge_voice = voice_id
        print(f"[TTS] Voz Edge: {old} → {voice_id}")
    elif _tts_engine == "piper":
        print(f"[TTS] Piper só tem 1 voz (faber-medium)")
        return False
    
    return True
```

### Modificar `generate_tts_kokoro()` pra usar a variável mutável:

Trocar:
```python
samples, sample_rate = kokoro_instance.create(
    text, voice=KOKORO_VOICE, speed=1.0, lang=KOKORO_LANG
)
```
Por:
```python
samples, sample_rate = kokoro_instance.create(
    text, voice=_kokoro_voice, speed=1.0, lang=KOKORO_LANG
)
```

### Modificar `generate_tts_edge()` pra usar a variável mutável:

Trocar:
```python
communicate = edge_tts.Communicate(text, TTS_VOICE)
```
Por:
```python
communicate = edge_tts.Communicate(text, _edge_voice)
```

---

## Tarefa 2: Backend — handler WebSocket (`server_ws.py`)

### Expandir o `server_info` enviado no connect (S2-A já adicionou):

```python
from core.tts import _tts_engine, get_available_voices, get_current_voice
from core.stt import get_current_model

server_info = {
    "type": "server_info",
    "tts_engine": _tts_engine,
    "tts_voice": get_current_voice(),
    "tts_voices": get_available_voices(),
    "whisper_model": get_current_model(),
}
await websocket.send_json(server_info)
```

### Expandir o handler de `{type: "config"}`:

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
```

---

## Tarefa 3: Frontend — dropdown de voz no config panel (`static/index.html`)

### HTML — adicionar no `#configPanel`, APÓS o grupo de Whisper model:

```html
<div class="config-group">
    <label for="cfgVoice">Voz da resposta</label>
    <div class="config-row">
        <span class="config-engine" id="cfgEngineLabel">Engine: —</span>
    </div>
    <select id="cfgVoice">
        <option value="">Carregando...</option>
    </select>
    <small>Muda a voz imediatamente na próxima resposta.</small>
</div>
```

### CSS — adicionar:

```css
.config-engine {
    font-size: 0.8rem;
    color: #4caf50;
    font-weight: 600;
}
```

### JavaScript:

1. **Popular dropdown quando receber `server_info`:**

   Modificar o handler de `server_info` (S2-A criou um básico):
   ```javascript
   if (data.type === 'server_info') {
       console.log('Server info:', data);
       window._serverInfo = data;
       
       // Atualizar label do engine
       const engineLabel = document.getElementById('cfgEngineLabel');
       if (engineLabel) {
           const engineNames = {kokoro: 'Kokoro (local, neural)', edge: 'Edge TTS (online)', piper: 'Piper (local)'};
           engineLabel.textContent = 'Engine: ' + (engineNames[data.tts_engine] || data.tts_engine);
       }
       
       // Popular dropdown de vozes
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
           
           // Desabilitar se só tem 1 voz (Piper)
           voiceSelect.disabled = data.tts_voices.length <= 1;
       }
       return;
   }
   ```

2. **Enviar mudança de voz ao mudar o dropdown:**

   ```javascript
   document.getElementById('cfgVoice').addEventListener('change', (e) => {
       const voice = e.target.value;
       if (voice && ws && ws.readyState === WebSocket.OPEN) {
           ws.send(JSON.stringify({type: 'config', tts_voice: voice}));
           console.log('Voz alterada para:', voice);
       }
   });
   ```

   Adicionar este listener junto com os outros listeners do config panel (perto do listener de volume do S1-E).

3. **NÃO salvar voz no localStorage** — a voz depende do engine do server. Se o server mudar de Kokoro pra Edge, os IDs de voz são diferentes. Melhor: sempre popular do `server_info` no connect.

---

## O que NÃO fazer

- NÃO mudar a fallback chain (kokoro → piper → edge)
- NÃO baixar novos modelos Piper automaticamente (apenas 1 modelo suportado)
- NÃO adicionar mais vozes Kokoro além de pm_alex e pf_dora (são as PT-BR disponíveis)
- NÃO permitir mudar o ENGINE (kokoro/piper/edge) via UI — é configuração de instalação, não de runtime
- NÃO mexer em `voice_assistant_app.py` ou `voice_assistant_cli.py`
- NÃO mudar a lógica de warmup, download, ou init

---

## Critério de sucesso

1. [ ] Ao conectar, dropdown de voz é populado com vozes do engine ativo
2. [ ] Label mostra qual engine está ativo (ex: "Engine: Kokoro (local, neural)")
3. [ ] Mudar voz no dropdown → próxima resposta usa a voz nova
4. [ ] Se engine é Piper → dropdown desabilitado (só 1 voz)
5. [ ] Se engine é Kokoro → dropdown mostra Alex e Dora
6. [ ] Se engine é Edge → dropdown mostra 6 vozes
7. [ ] Voz muda imediatamente (não precisa reload)
8. [ ] Reconectar → dropdown re-populado corretamente
9. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

1. Iniciar server → conectar → verificar que dropdown mostra vozes e engine label
2. Se Kokoro: mudar pra pf_dora → falar algo → verificar que resposta é voz feminina
3. Se Edge: mudar pra Francisca → falar algo → verificar que resposta é voz feminina
4. Mudar de volta pra voz masculina → verificar
5. Desconectar → reconectar → dropdown re-popula corretamente
6. Verificar log do server: `[TTS] Voz Kokoro: pm_alex → pf_dora` (ou equivalente)
