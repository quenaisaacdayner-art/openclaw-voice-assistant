# S2-C: Slider de Velocidade do TTS

> Prompt auto-contido. Leia e execute.
> Pré-requisito: S2-B executado (seletor de vozes existe)
> Arquivos a modificar: `core/tts.py`, `server_ws.py`, `static/index.html`

---

## Contexto

O TTS gera áudio com velocidade fixa (1.0x). Alguns usuários preferem respostas mais rápidas (1.2x-1.5x) pra economizar tempo, outros preferem mais devagar (0.8x) pra entender melhor. Vamos adicionar um slider de velocidade no config panel.

### Suporte por engine

| Engine | Suporta velocidade? | Como |
|--------|---------------------|------|
| Kokoro | ✅ Sim | Parâmetro `speed` no `create()` (0.5 a 2.0) |
| Edge | ✅ Sim | Parâmetro `rate` no `Communicate()` (ex: "+20%", "-10%") |
| Piper | ❌ Não | Sem controle nativo. Fica fixo 1.0x |

---

## Tarefa 1: Backend — velocidade configurável (`core/tts.py`)

### Adicionar variável mutável no topo (junto com `_kokoro_voice` e `_edge_voice`):

```python
_tts_speed = 1.0  # 0.5 a 2.0 (1.0 = normal)
```

### Adicionar funções:

```python
def get_speed():
    """Retorna velocidade atual do TTS."""
    return _tts_speed

def set_speed(speed):
    """Muda velocidade do TTS. Range: 0.5 a 2.0."""
    global _tts_speed
    speed = max(0.5, min(2.0, float(speed)))
    old = _tts_speed
    _tts_speed = speed
    if old != speed:
        print(f"[TTS] Velocidade: {old}x → {speed}x")
    return True
```

### Modificar `generate_tts_kokoro()`:

Trocar:
```python
samples, sample_rate = kokoro_instance.create(
    text, voice=_kokoro_voice, speed=1.0, lang=KOKORO_LANG
)
```
Por:
```python
samples, sample_rate = kokoro_instance.create(
    text, voice=_kokoro_voice, speed=_tts_speed, lang=KOKORO_LANG
)
```

### Modificar `generate_tts_edge()`:

Trocar:
```python
communicate = edge_tts.Communicate(text, _edge_voice)
```
Por:
```python
# Edge TTS usa rate como string percentual: "+20%" ou "-10%"
edge_rate = ""
if _tts_speed != 1.0:
    pct = round((_tts_speed - 1.0) * 100)
    edge_rate = f"+{pct}%" if pct > 0 else f"{pct}%"

communicate = edge_tts.Communicate(text, _edge_voice, rate=edge_rate)
```

**⚠️ Verificar:** o construtor `edge_tts.Communicate()` aceita `rate` como keyword argument. Se não, usar a abordagem com SSML. Testar antes de commitar. Se `rate` não funcionar, alternativa:
```python
communicate = edge_tts.Communicate(text, _edge_voice)
# rate fica empty string = velocidade padrão
# Se precisar SSML, é outra abordagem mais complexa — documentar e deixar pra depois
```

### Piper: sem mudança. Velocidade não se aplica.

---

## Tarefa 2: Backend — handler WebSocket (`server_ws.py`)

### Expandir `server_info` (S2-B já expandiu com vozes):

Adicionar `tts_speed`:
```python
from core.tts import get_speed

server_info = {
    "type": "server_info",
    "tts_engine": _tts_engine,
    "tts_voice": get_current_voice(),
    "tts_voices": get_available_voices(),
    "tts_speed": get_speed(),
    "whisper_model": get_current_model(),
}
```

### Expandir handler de `{type: "config"}`:

Adicionar após o bloco de `tts_voice`:
```python
    speed = data.get("tts_speed")
    if speed is not None:
        from core.tts import set_speed
        set_speed(float(speed))
```

---

## Tarefa 3: Frontend — slider de velocidade (`static/index.html`)

### HTML — adicionar no `#configPanel`, APÓS o grupo de voz (S2-B):

```html
<div class="config-group">
    <label for="cfgSpeed">Velocidade da fala</label>
    <div class="config-row">
        <input type="range" id="cfgSpeed" min="0.5" max="2.0" step="0.1" value="1.0">
        <span id="cfgSpeedLabel">1.0x</span>
    </div>
    <small>0.5x (lento) a 2.0x (rápido). Aplica na próxima frase. Piper ignora esta configuração.</small>
</div>
```

### JavaScript:

1. **Atualizar valor do slider quando receber `server_info`:**

   No handler de `server_info` (S2-B já tem um):
   ```javascript
   // Dentro do if (data.type === 'server_info') {
   const speedSlider = document.getElementById('cfgSpeed');
   const speedLabel = document.getElementById('cfgSpeedLabel');
   if (speedSlider && data.tts_speed !== undefined) {
       speedSlider.value = data.tts_speed;
       speedLabel.textContent = data.tts_speed.toFixed(1) + 'x';
   }
   ```

2. **Enviar mudança de velocidade ao mover o slider:**

   ```javascript
   document.getElementById('cfgSpeed').addEventListener('input', (e) => {
       const speed = parseFloat(e.target.value);
       document.getElementById('cfgSpeedLabel').textContent = speed.toFixed(1) + 'x';
   });

   document.getElementById('cfgSpeed').addEventListener('change', (e) => {
       const speed = parseFloat(e.target.value);
       if (ws && ws.readyState === WebSocket.OPEN) {
           ws.send(JSON.stringify({type: 'config', tts_speed: speed}));
           console.log('Velocidade TTS:', speed + 'x');
       }
   });
   ```

   **Nota:** `input` atualiza o label em tempo real (enquanto arrasta). `change` envia pro server só quando solta o slider (evita spam de mensagens WS).

3. **NÃO salvar no localStorage** — velocidade é preferência de sessão. Valor default 1.0x é seguro.

   Se quiser persistir (opcional): salvar no localStorage e aplicar no connect:
   ```javascript
   // Em saveConfig():
   localStorage.setItem('ova_tts_speed', document.getElementById('cfgSpeed').value);
   
   // Em loadConfig():
   const speed = localStorage.getItem('ova_tts_speed');
   if (speed) {
       document.getElementById('cfgSpeed').value = speed;
       document.getElementById('cfgSpeedLabel').textContent = parseFloat(speed).toFixed(1) + 'x';
   }
   
   // No ws.onopen, após enviar config:
   const savedSpeed = localStorage.getItem('ova_tts_speed');
   if (savedSpeed) {
       ws.send(JSON.stringify({type: 'config', tts_speed: parseFloat(savedSpeed)}));
   }
   ```

   **Decisão do implementador:** se o saveConfig() do S1-E já existe e persiste outras configs, adicionar speed ali. Se não, implementar a versão SEM persistência (mais simples, valor reseta pra 1.0x no reload).

---

## O que NÃO fazer

- NÃO mudar a fallback chain do TTS
- NÃO tentar implementar velocidade pra Piper (não é suportado)
- NÃO usar SSML pra Edge (rate como parâmetro direto é mais simples; se não funcionar, documentar e deixar pra depois)
- NÃO permitir valores fora de 0.5-2.0 (clampar no `set_speed`)
- NÃO mexer em `voice_assistant_app.py` ou `voice_assistant_cli.py`
- NÃO mudar nenhuma lógica de streaming, barge-in, ou VAD

---

## Critério de sucesso

1. [ ] Slider de velocidade aparece no config panel
2. [ ] Label mostra valor em tempo real (ex: "1.3x")
3. [ ] Mudar pra 1.5x → próxima resposta sai mais rápida (Kokoro ou Edge)
4. [ ] Mudar pra 0.7x → próxima resposta sai mais devagar
5. [ ] Se engine é Piper → velocidade não muda (esperado, documentado no small text)
6. [ ] Server log mostra `[TTS] Velocidade: 1.0x → 1.5x`
7. [ ] Reconectar → slider mostra valor do server (via server_info)
8. [ ] Valores extremos (0.5, 2.0) não quebram o TTS
9. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

1. Iniciar → conectar → verificar slider em 1.0x
2. Mover pra 1.5x → falar algo → resposta sai mais rápida
3. Mover pra 0.7x → falar algo → resposta sai mais devagar
4. Voltar pra 1.0x → velocidade normal
5. Verificar log do server: `[TTS] Velocidade: 1.0x → 1.5x`
6. Desconectar → reconectar → slider mostra valor correto
