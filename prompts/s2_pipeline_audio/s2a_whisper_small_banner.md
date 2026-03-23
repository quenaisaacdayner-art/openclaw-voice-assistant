# S2-A: Whisper Small Default + Banner TTS no Startup

> Prompt auto-contido. Leia e execute.
> Pré-requisito: S1-A executado (mínimo). Não depende de S1-B~E.
> Arquivos a modificar: `core/config.py`, `core/stt.py`, `server_ws.py`

---

## Contexto

O voice assistant usa Whisper `tiny` por default. O modelo tiny erra frequentemente com sotaque, pronúncia informal, e palavras mal articuladas. O modelo `small` é 6x maior (244MB vs 75MB) e significativamente mais preciso para português brasileiro informal, com tempo de transcrição aceitável em CPU (~3-5s vs ~1-2s do tiny).

Além disso, o startup do server NÃO mostra qual engine TTS está ativa. O usuário não sabe se está usando Kokoro (natural), Piper (robótico), ou Edge (online). Isso dificulta diagnóstico.

---

## Tarefa 1: Mudar default do Whisper de tiny → small

### Em `core/config.py`:

Mudar a linha:
```python
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "tiny")
```
Para:
```python
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
```

Isso é tudo. O `faster-whisper` baixa o modelo automaticamente no primeiro uso se não existir localmente. O download de ~244MB acontece 1 vez.

### Em `core/stt.py`:

Adicionar uma variável mutável pra permitir troca em runtime (preparação pro config panel do S1-E):

```python
_whisper_model_size = WHISPER_MODEL_SIZE  # cópia mutável
```

Modificar `_get_whisper()` pra usar a variável mutável:
```python
def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                print(f"⏳ Carregando Whisper ({_whisper_model_size})...")
                _whisper_model = WhisperModel(
                    _whisper_model_size, device="cpu", compute_type="int8"
                )
                print("✅ Whisper pronto")
    return _whisper_model
```

Adicionar função `set_whisper_model()`:
```python
def set_whisper_model(model_name):
    """Muda o modelo Whisper. Próxima transcrição usará o novo modelo."""
    global _whisper_model, _whisper_model_size
    if model_name in ("tiny", "small", "medium") and model_name != _whisper_model_size:
        old = _whisper_model_size
        _whisper_model_size = model_name
        _whisper_model = None  # Força recarregar no próximo uso (lazy loading)
        print(f"[STT] Whisper: {old} → {model_name} (recarrega na próxima transcrição)")
```

Modificar `init_stt()` pra usar a variável mutável:
```python
def init_stt():
    import time
    t0 = time.time()
    _get_whisper()
    elapsed = time.time() - t0
    print(f"[WARMUP] Whisper ({_whisper_model_size}) carregado em {elapsed:.1f}s")
```

Adicionar função `get_current_model()`:
```python
def get_current_model():
    """Retorna o nome do modelo Whisper atual."""
    return _whisper_model_size
```

---

## Tarefa 2: Banner TTS no startup do server

### Em `server_ws.py`:

Encontrar o bloco de startup que imprime o banner (linhas com `print` no início, antes do `uvicorn.run()`). Adicionar APÓS a inicialização do TTS:

```python
# Após init_tts() e warmup_tts():
from core.tts import _tts_engine, kokoro_instance, piper_voice, TTS_VOICE, KOKORO_VOICE

# Banner de TTS
if _tts_engine == "kokoro" and kokoro_instance is not None:
    tts_info = f"Kokoro (voz: {KOKORO_VOICE}, local)"
elif _tts_engine == "piper" and piper_voice is not None:
    tts_info = f"Piper (faber-medium, local)"
elif _tts_engine == "edge":
    tts_info = f"Edge TTS ({TTS_VOICE}, online)"
else:
    tts_info = f"{_tts_engine} (estado desconhecido)"

print(f"🔊 TTS Engine: {tts_info}")
```

**Posicionamento:** deve aparecer ANTES da mensagem "Servidor pronto" ou equivalente, junto com as outras linhas de info do startup.

### Resultado esperado no terminal:

```
⏳ Carregando Whisper (small)...
✅ Whisper pronto
[WARMUP] Whisper (small) carregado em 4.2s
⏳ Carregando Kokoro TTS...
✅ Kokoro TTS pronto (voz: pm_alex, lang: pt-br)
[WARMUP] TTS (kokoro) pronto em 0.3s
🔊 TTS Engine: Kokoro (voz: pm_alex, local)
```

Ou se Kokoro não estiver instalado:
```
⚠️ Kokoro indisponível (kokoro-onnx não instalado) — tentando Piper
⏳ Carregando Piper TTS (pt_BR-faber-medium.onnx)...
✅ Piper TTS pronto
[WARMUP] TTS (piper) pronto em 0.5s
🔊 TTS Engine: Piper (faber-medium, local)
```

---

## Tarefa 3: Adicionar info de TTS engine no WebSocket handshake

Quando o frontend conecta via WebSocket, enviar info do engine TTS como parte da mensagem inicial. Isso permite que o frontend (futuro S2-B) saiba qual engine está ativa.

### Em `server_ws.py`, no `@app.websocket("/ws")` handler:

Após aceitar a conexão WebSocket, enviar mensagem de info:

```python
await websocket.accept()

# Enviar info do server pro frontend
from core.tts import _tts_engine
from core.stt import get_current_model
server_info = {
    "type": "server_info",
    "tts_engine": _tts_engine,
    "whisper_model": get_current_model(),
}
await websocket.send_json(server_info)
```

### No frontend (`static/index.html`):

Adicionar handler pra `server_info` no `ws.onmessage`:

```javascript
if (data.type === 'server_info') {
    console.log('Server info:', data);
    // Armazenar pra uso futuro (S2-B vai usar pra mostrar no config panel)
    window._serverInfo = data;
    return;
}
```

---

## O que NÃO fazer

- NÃO mudar `language="pt"` no transcribe (já está correto)
- NÃO mudar a lógica de fallback chain do TTS (kokoro → piper → edge)
- NÃO mexer no config panel (isso é S1-E → S2-B)
- NÃO instalar PyTorch ou distil-whisper (CPU-only, ficamos com faster-whisper)
- NÃO mudar `voice_assistant_app.py` ou `voice_assistant_cli.py`
- NÃO remover suporte ao modelo tiny (usuário pode escolher via env var ou futuro config panel)

---

## Critério de sucesso

1. [ ] Startup mostra `Whisper (small)` em vez de `Whisper (tiny)`
2. [ ] Startup mostra `🔊 TTS Engine: ...` com o engine ativo
3. [ ] Primeiro uso baixa modelo `small` automaticamente (~244MB download)
4. [ ] Transcrição funciona normalmente após troca
5. [ ] `set_whisper_model()` existe e funciona (testar: chamar com "tiny", verificar que próxima transcrição usa tiny)
6. [ ] WebSocket envia `server_info` ao conectar
7. [ ] Frontend loga `server_info` no console
8. [ ] `WHISPER_MODEL=tiny python server_ws.py` ainda funciona (env var override)
9. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

1. Iniciar server → verificar que terminal mostra qual TTS engine e Whisper small
2. Falar algo com pronúncia informal → verificar se transcrição melhorou vs tiny
3. Abrir DevTools no browser → verificar que console mostra `Server info: {tts_engine: "...", whisper_model: "small"}`
4. Parar server → `WHISPER_MODEL=tiny python server_ws.py` → verificar que usa tiny (env var funciona)
