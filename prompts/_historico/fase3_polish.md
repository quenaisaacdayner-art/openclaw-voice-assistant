# FASE 3 — Polish (TTS Pipeline, UI, Testes, Documentação)

Leia estes arquivos nesta ordem antes de qualquer ação:
1. CLAUDE.md (contexto do projeto, arquitetura, roadmap)
2. server_ws.py (INTEIRO — servidor WebSocket criado na Fase 2)
3. static/index.html (INTEIRO — frontend Web Audio criado na Fase 2)
4. core/tts.py
5. core/stt.py
6. core/llm.py

---

## CONTEXTO

Fase 1 otimizou latência (Sonnet 4.6, Whisper tiny, split agressivo).
Fase 2 criou servidor WebSocket + frontend Web Audio API.

O sistema funciona mas tem rough edges:
- TTS gera arquivo completo por frase → envia WAV inteiro → browser toca. Funciona mas tem delay entre frases
- Frontend funcional mas sem polish visual
- Zero testes pro server_ws.py e frontend
- Sem barge-in (usuário interromper resposta falando)
- Documentação não reflete o estado final

---

## TASK 1: Pipeline TTS mais eficiente (server_ws.py)

O fluxo atual de TTS no server é:
```
frase → generate_tts(frase) → retorna path de arquivo → lê arquivo → envia bytes → deleta arquivo
```

Isso cria/deleta um arquivo temporário POR FRASE. Otimizar:

### 1a. Criar helper `_tts_to_bytes` no server_ws.py:

```python
async def _tts_to_bytes(text, loop):
    """Gera TTS e retorna bytes do áudio (sem arquivo intermediário se possível)."""
    tts_path = await loop.run_in_executor(None, generate_tts, text)
    if not tts_path:
        return None
    try:
        with open(tts_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tts_path)
        except OSError:
            pass
```

### 1b. Usar `_tts_to_bytes` em todos os pontos do WebSocket handler que chamam generate_tts

Substituir o padrão repetido:
```python
# ANTES (repetido 2x no handler):
tts_path = await loop.run_in_executor(None, generate_tts, sentence)
if tts_path:
    with open(tts_path, "rb") as af:
        await ws.send_bytes(af.read())
    try:
        os.unlink(tts_path)
    except OSError:
        pass

# DEPOIS:
audio_bytes = await _tts_to_bytes(sentence, loop)
if audio_bytes:
    await ws.send_bytes(audio_bytes)
```

### 1c. TTS em paralelo com LLM streaming

Atualmente o servidor espera o TTS terminar antes de continuar consumindo o stream do LLM. Isso é ok pra frases curtas mas suboptimal. Melhorar com uma task asyncio separada pra TTS:

```python
# Dentro do handler, após detectar frase completa:
tts_tasks = []

# Quando frase detectada:
async def tts_and_send(sentence_text):
    audio_bytes = await _tts_to_bytes(sentence_text, loop)
    if audio_bytes:
        try:
            await ws.send_bytes(audio_bytes)
        except Exception:
            pass

task = asyncio.create_task(tts_and_send(sentence))
tts_tasks.append(task)

# No final (após loop de streaming):
# Aguardar todas as TTS tasks pendentes
if tts_tasks:
    await asyncio.gather(*tts_tasks, return_exceptions=True)
```

**ATENÇÃO:** Isso pode causar áudio fora de ordem se uma frase curta terminar TTS antes de uma longa anterior. Pra garantir ordem, usar um `asyncio.Lock` ou sequenciar:

```python
tts_lock = asyncio.Lock()

async def tts_and_send_ordered(sentence_text):
    audio_bytes = await _tts_to_bytes(sentence_text, loop)
    if audio_bytes:
        async with tts_lock:
            try:
                await ws.send_bytes(audio_bytes)
            except Exception:
                pass
```

Na verdade o lock não garante ordem (quem pega primeiro ganha). A solução correta é simples: **manter sequencial** — o TTS de cada frase é rápido (~0.5-1s) e a fila de playback do frontend já lida com gaps. Não vale a complexidade de paralelizar.

**Decisão final: manter TTS sequencial, só extrair pra `_tts_to_bytes`.**

---

## TASK 2: Barge-in (interrupção por voz)

Quando o usuário fala enquanto o servidor está gerando resposta, o sistema deve:

### 2a. No frontend (static/index.html):

1. Durante playback (`isPlaying === true`), continuar processando VAD
2. Se detectar fala durante playback → parar playback imediatamente + enviar interrupt:

```javascript
function processAudioChunk(downsampled) {
    // ... cálculo RMS existente ...
    
    // Barge-in: detectou fala durante playback
    if (isPlaying && rms > VAD_THRESHOLD) {
        // Parar playback
        stopPlayback();
        // Notificar servidor
        ws.send(JSON.stringify({type: "interrupt"}));
    }
    
    // ... resto do VAD existente ...
}

function stopPlayback() {
    // Parar source atual se existir
    if (currentSource) {
        try { currentSource.stop(); } catch(e) {}
        currentSource = null;
    }
    // Limpar fila
    playbackQueue = [];
    isPlaying = false;
}
```

**IMPORTANTE:** Precisa guardar referência ao `AudioBufferSourceNode` atual:

```javascript
let currentSource = null;

function playNext() {
    if (playbackQueue.length === 0) {
        isPlaying = false;
        currentSource = null;
        return;
    }
    isPlaying = true;
    const buffer = playbackQueue.shift();
    const source = playbackContext.createBufferSource();
    currentSource = source;  // ← GUARDAR REFERÊNCIA
    source.buffer = buffer;
    source.connect(playbackContext.destination);
    source.onended = () => playNext();
    source.start();
}
```

2. Remover o `if (serverSpeaking || isMuted) return;` do processAudioChunk — agora queremos processar áudio MESMO durante playback (pro barge-in funcionar). O mute do mic durante server speaking era proteção contra eco, mas com barge-in precisamos ouvir. Manter APENAS o check de `isMuted`:

```javascript
// ANTES:
if (serverSpeaking || isMuted) return;

// DEPOIS:
if (isMuted) return;
```

3. Mas ainda precisamos evitar eco. Solução: elevar o threshold de VAD durante playback:

```javascript
function getVadThreshold() {
    // Durante playback, threshold mais alto pra ignorar eco do speaker
    return isPlaying ? VAD_THRESHOLD * 3 : VAD_THRESHOLD;
}

// No processAudioChunk:
if (rms > getVadThreshold()) { ... }
```

### 2b. No servidor (server_ws.py):

Quando receber `{"type": "interrupt"}`:
1. Parar de consumir o stream do LLM (cancelar)
2. Não enviar mais áudio TTS
3. Guardar o texto parcial no histórico
4. Voltar pra estado "listening"

Implementação: usar uma flag `interrupted` que o loop de streaming checa:

```python
interrupted = False

# No handler de mensagens, ANTES do loop de streaming:
# Precisamos processar mensagens enquanto streaming...

# Problema: o loop de streaming bloqueia o receive.
# Solução: mover o streaming pra uma task separada e continuar ouvindo mensagens.
```

**ATENÇÃO — Este é o desafio principal da Task 2.**

O handler atual faz `await ws.receive()` num loop, e quando recebe `speech_end`, processa tudo (STT → LLM → TTS) antes de voltar a ouvir. Durante esse processamento, NÃO recebe novas mensagens (incluindo interrupt).

**Solução: split em duas coroutines:**

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    
    chat_history = []
    audio_buffer = bytearray()
    processing = False
    cancel_event = asyncio.Event()
    
    TOKEN = load_token()
    
    async def process_speech():
        """Processa áudio acumulado: STT → LLM → TTS"""
        nonlocal processing, chat_history
        processing = True
        cancel_event.clear()
        
        try:
            await ws.send_json({"type": "status", "status": "thinking"})
            
            # 1. Converter PCM → WAV temp
            pcm_data = np.frombuffer(bytes(audio_buffer), dtype=np.int16)
            audio_buffer.clear()
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
                with wave.open(f, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(pcm_data.tobytes())
            
            try:
                # 2. STT
                loop = asyncio.get_event_loop()
                transcript = await loop.run_in_executor(None, transcribe_audio, wav_path)
                
                if not transcript or cancel_event.is_set():
                    await ws.send_json({"type": "transcript", "text": ""})
                    return
                
                await ws.send_json({"type": "transcript", "text": transcript})
                chat_history.append({"role": "user", "content": transcript})
                if len(chat_history) > MAX_HISTORY * 2:
                    chat_history = chat_history[-(MAX_HISTORY * 2):]
                
                # 3. LLM streaming + TTS
                api_history = build_api_history(chat_history[:-1])
                
                await ws.send_json({"type": "status", "status": "speaking"})
                
                text_queue = asyncio.Queue()
                
                def _stream_worker():
                    try:
                        for partial in ask_openclaw_stream(transcript, TOKEN, api_history):
                            asyncio.run_coroutine_threadsafe(text_queue.put(partial), loop)
                    except Exception as e:
                        asyncio.run_coroutine_threadsafe(text_queue.put(("error", str(e))), loop)
                    finally:
                        asyncio.run_coroutine_threadsafe(text_queue.put(None), loop)
                
                loop.run_in_executor(None, _stream_worker)
                
                full_response = ""
                last_tts_end = 0
                
                while True:
                    if cancel_event.is_set():
                        break
                    
                    try:
                        partial = await asyncio.wait_for(text_queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue
                    
                    if partial is None:
                        break
                    if isinstance(partial, tuple) and partial[0] == "error":
                        await ws.send_json({"type": "error", "message": partial[1]})
                        break
                    
                    full_response = partial
                    await ws.send_json({"type": "text", "text": partial, "done": False})
                    
                    remaining = partial[last_tts_end:]
                    end = _find_sentence_end(remaining)
                    if end > 0:
                        sentence = remaining[:end].strip()
                        if sentence and not cancel_event.is_set():
                            audio_bytes = await _tts_to_bytes(sentence, loop)
                            if audio_bytes and not cancel_event.is_set():
                                await ws.send_bytes(audio_bytes)
                            last_tts_end += end
                
                # TTS do resto (se não foi interrompido)
                if full_response and not cancel_event.is_set():
                    remaining_text = full_response[last_tts_end:].strip()
                    if remaining_text:
                        audio_bytes = await _tts_to_bytes(remaining_text, loop)
                        if audio_bytes and not cancel_event.is_set():
                            await ws.send_bytes(audio_bytes)
                    
                    await ws.send_json({"type": "text", "text": full_response, "done": True})
                    chat_history.append({"role": "assistant", "content": full_response})
                elif full_response:
                    # Interrompido — salvar texto parcial
                    await ws.send_json({"type": "text", "text": full_response, "done": True})
                    chat_history.append({"role": "assistant", "content": full_response + " [interrompido]"})
            
            finally:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
        
        finally:
            processing = False
            if not cancel_event.is_set():
                await ws.send_json({"type": "status", "status": "listening"})
    
    # ─── Main receive loop ────────────────────────────────
    process_task = None
    
    try:
        while True:
            message = await ws.receive()
            
            if "bytes" in message:
                if not processing:
                    audio_buffer.extend(message["bytes"])
                # Se processing, ainda acumula pra possível novo turno após interrupt
                # (mas só se cancel_event foi set — senão ignora)
                elif cancel_event.is_set():
                    audio_buffer.extend(message["bytes"])
            
            elif "text" in message:
                data = json.loads(message["text"])
                
                if data["type"] == "vad_event" and data["event"] == "speech_end":
                    if processing:
                        # Já processando — ignorar ou tratar como barge-in
                        continue
                    if len(audio_buffer) < 1600:
                        audio_buffer.clear()
                        continue
                    
                    process_task = asyncio.create_task(process_speech())
                
                elif data["type"] == "interrupt":
                    if processing:
                        cancel_event.set()
                        # process_speech vai parar no próximo check
                        # Aguardar cleanup
                        if process_task:
                            try:
                                await asyncio.wait_for(process_task, timeout=5.0)
                            except asyncio.TimeoutError:
                                pass
                        await ws.send_json({"type": "status", "status": "listening"})
    
    except WebSocketDisconnect:
        if process_task and not process_task.done():
            cancel_event.set()
            process_task.cancel()
```

**Este é o handler COMPLETO que substitui o existente em server_ws.py.** Preserva toda a lógica existente (STT, LLM streaming, TTS, error handling) e adiciona barge-in via `cancel_event`.

---

## TASK 3: Indicador visual de volume no frontend

Adicionar uma barra de volume animada que mostra o nível de áudio do microfone em tempo real.

### HTML (adicionar dentro do container existente, após o status bar):

```html
<div id="volume-container">
    <div id="volume-bar"></div>
</div>
```

### CSS:

```css
#volume-container {
    width: 100%;
    height: 4px;
    background: #2d2d44;
    border-radius: 2px;
    overflow: hidden;
    margin: 8px 0;
}
#volume-bar {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #38a169, #d69e2e, #e53e3e);
    border-radius: 2px;
    transition: width 50ms ease-out;
}
```

### JavaScript:

```javascript
function updateVolumeBar(rms) {
    const bar = document.getElementById('volume-bar');
    // Normalizar RMS (0-0.1 → 0-100%)
    const percent = Math.min(100, (rms / 0.1) * 100);
    bar.style.width = percent + '%';
}

// Chamar no processAudioChunk, ANTES dos checks de isMuted:
updateVolumeBar(rms);
```

---

## TASK 4: Indicador de conexão WebSocket no frontend

Mostrar claramente se o WebSocket está conectado.

### No connect():

```javascript
function connect() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        updateConnectionStatus(true);
        startMic();
    };
    
    ws.onclose = () => {
        updateConnectionStatus(false);
        setTimeout(connect, 3000);  // Reconexão
    };
    
    ws.onerror = () => {
        updateConnectionStatus(false);
    };
    
    ws.onmessage = onMessage;
}

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connection-status');
    indicator.innerHTML = connected 
        ? '<span style="color:#38a169">● Conectado</span>'
        : '<span style="color:#e53e3e">● Desconectado</span>';
}
```

Verificar se o frontend já tem isso. Se sim, garantir que funciona com reconexão.

---

## TASK 5: Testes pro server_ws.py

Criar `tests/test_server_ws.py` com testes unitários. Usar `httpx` + `pytest-asyncio` pra testar WebSocket endpoints.

### Adicionar dependências de teste:

```bash
pip install httpx pytest-asyncio
```

Adicionar em `requirements.txt` (ou criar `requirements-test.txt`):
```
httpx>=0.25.0
pytest-asyncio>=0.23.0
```

### Testes mínimos:

```python
"""Testes para server_ws.py"""
import pytest
import json
import wave
import struct
import tempfile
import os
from unittest.mock import patch, MagicMock

# Testar imports e syntax
def test_server_ws_imports():
    """Verifica que server_ws.py importa sem erros."""
    # Não importar diretamente (inicia uvicorn)
    import ast
    with open("server_ws.py") as f:
        tree = ast.parse(f.read())
    assert tree is not None

def test_static_index_exists():
    """Verifica que static/index.html existe."""
    assert os.path.exists("static/index.html")

def test_static_index_has_websocket():
    """Verifica que o frontend tem código WebSocket."""
    with open("static/index.html") as f:
        content = f.read()
    assert "WebSocket" in content
    assert "processAudioChunk" in content
    assert "playNext" in content
    assert "downsample" in content

def test_static_index_has_vad():
    """Verifica que o frontend tem VAD."""
    with open("static/index.html") as f:
        content = f.read()
    assert "VAD_THRESHOLD" in content
    assert "speech_end" in content
    assert "SILENCE_MS" in content

def test_static_index_has_barge_in():
    """Verifica que o frontend tem barge-in."""
    with open("static/index.html") as f:
        content = f.read()
    assert "interrupt" in content
    assert "stopPlayback" in content

def test_static_index_dark_mode():
    """Verifica dark mode."""
    with open("static/index.html") as f:
        content = f.read()
    assert "#1a1a2e" in content or "dark" in content.lower()

# Testes de integração com FastAPI TestClient
@pytest.fixture
def app():
    """Importa o app FastAPI sem iniciar uvicorn."""
    import importlib
    import sys
    
    # Mock uvicorn.run pra não iniciar servidor
    with patch.dict(sys.modules, {"uvicorn": MagicMock()}):
        # Precisa re-importar sem executar if __name__ == "__main__"
        spec = importlib.util.spec_from_file_location("server_ws", "server_ws.py")
        mod = importlib.util.module_from_spec(spec)
        # Não executar — só parsear
        pass
    # Se não der pra importar sem side effects, skip
    pytest.skip("server_ws tem side effects no import")

def test_tts_to_bytes_helper():
    """Verifica que _tts_to_bytes limpa arquivos temporários."""
    # Este teste verifica o conceito — a implementação real depende de generate_tts
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Criar WAV fake
        with wave.open(f, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack('<' + 'h' * 100, *([1000] * 100)))
        path = f.name
    
    assert os.path.exists(path)
    
    # Simular o que _tts_to_bytes faz
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    
    assert len(data) > 0
    assert not os.path.exists(path)  # Cleanup funcionou

def test_pcm_to_wav_conversion():
    """Verifica conversão PCM → WAV (usado no handler)."""
    import numpy as np
    
    # Simular 1s de áudio PCM 16-bit mono 16kHz
    pcm_data = np.random.randint(-32768, 32767, size=16000, dtype=np.int16)
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
        with wave.open(f, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_data.tobytes())
    
    # Verificar que o WAV é válido
    with wave.open(wav_path, 'rb') as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 16000
    
    os.unlink(wav_path)
```

---

## TASK 6: Atualizar CLAUDE.md

Adicionar ao CLAUDE.md, na seção "Arquitetura do código":

```
server_ws.py             — Servidor WebSocket S2S (FastAPI + uvicorn) — PRINCIPAL
static/index.html        — Frontend Web Audio API (HTML + CSS + JS inline)
```

Atualizar a seção "Variáveis de ambiente" pra incluir `APP_MODE`.

Atualizar seção "Testes":
```
~240+ testes (pytest). Inclui testes de estrutura do frontend e conversão PCM→WAV.
```

Na seção de "Partes frágeis", adicionar:
```
8. **Barge-in (server_ws.py)** — cancel_event + asyncio.create_task. Se a task não checa cancel_event frequentemente, pode demorar a parar.
9. **Audio playback queue (index.html)** — playNext() encadeia via onended. Se decodeAudioData falhar num chunk, a fila trava. Precisa de try/catch.
10. **Downsample (index.html)** — Nearest-neighbor simples. Pode ter aliasing em áudio com frequências altas. Aceitável pra voz.
```

---

## TASK 7: Atualizar README.md

### Seção "O que faz" — atualizar tempos:
```
~3-6s do fim da fala até início da resposta em áudio (com Sonnet 4.6 + Whisper tiny).
```

### Seção "Features" — adicionar:
```
- **Barge-in** — Interrompa a resposta falando por cima — o assistente para e escuta
- **WebSocket S2S** — Streaming bidirecional real, sem polling HTTP
```

### Seção "Roadmap" — marcar Fase 2 e 3:
```
- [x] **Fase 1:** Otimização de latência (modelo rápido, Whisper tiny, split agressivo)
- [x] **Fase 2:** WebSocket + Web Audio API (S2S real, streaming bidirecional)
- [x] **Fase 3:** Barge-in, TTS pipeline, testes, polish
```

### Seção "Arquitetura" — atualizar diagrama:
```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌───────────┐
│ Microfone │◄──▶│ WebSocket│◄──▶│   OpenClaw    │───▶│    TTS    │
│ (browser) │    │ (FastAPI) │    │  (streaming)  │    │ (por      │
└──────────┘    └──────────┘    └──────────────┘    │  frase)   │
   Bidirecional    ~50ms            ~2-4s Sonnet      └───────────┘
                                                       ~0.5-1s
```

```
server_ws.py             ─── Servidor WebSocket S2S (principal)
static/index.html        ─── Frontend Web Audio API
voice_assistant_app.py   ─── Fallback Gradio (APP_MODE=gradio)
voice_assistant_cli.py   ─── CLI terminal
core/                    ─── Módulos compartilhados
```

---

## Verificação final

1. **Syntax check:**
   ```bash
   python -c "import ast; ast.parse(open('server_ws.py').read()); print('OK')"
   ```

2. **Frontend tem barge-in:**
   ```bash
   grep -c "interrupt\|stopPlayback\|currentSource" static/index.html
   ```
   Deve retornar ≥ 3.

3. **Testes:**
   ```bash
   lsof -ti:7860 | xargs kill -9 2>/dev/null
   python -m pytest tests/ -v
   ```
   Todos os testes existentes + novos devem passar.

4. **Sem regressions no Gradio app:**
   ```bash
   python -c "import voice_assistant_app; print('Gradio OK')"
   ```

5. **Commit:**
   ```bash
   git add -A && git commit -m "feat: fase 3 - barge-in, TTS pipeline, testes, polish"
   ```

6. **NÃO fazer git push**

---

## Arquivos que DEVEM ser criados/modificados

### Criados:
- `tests/test_server_ws.py` — testes pro server WebSocket e frontend

### Modificados:
- `server_ws.py` — `_tts_to_bytes` helper + barge-in com cancel_event + handler refatorado
- `static/index.html` — barge-in (stopPlayback, currentSource, interrupt), volume bar, connection indicator
- `CLAUDE.md` — refletir estado final
- `README.md` — refletir estado final

### NÃO modificar:
- `core/*` — módulos compartilhados intactos
- `voice_assistant_app.py` — fallback Gradio intacto
- `voice_assistant_cli.py` — CLI intacto
- `tests/` existentes — não quebrar
