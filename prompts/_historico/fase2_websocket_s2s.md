# FASE 2 — WebSocket + Web Audio API (S2S Real)

Leia estes arquivos nesta ordem antes de qualquer ação:
1. CLAUDE.md (contexto do projeto, arquitetura, partes frágeis)
2. core/config.py
3. core/llm.py (especialmente `ask_openclaw_stream` e `_find_sentence_end`)
4. core/tts.py (especialmente `generate_tts` — retorna path de arquivo .wav/.mp3)
5. core/stt.py (especialmente `transcribe_audio` — recebe path ou tuple numpy)
6. core/history.py

NÃO leia voice_assistant_app.py — ele vai continuar existindo como fallback Gradio, mas esta fase cria um servidor novo SEPARADO.

---

## CONTEXTO

Fase 1 otimizou latência dentro do Gradio (Sonnet 4.6, Whisper tiny, split agressivo). Mas o Gradio tem limitações fundamentais:
- `gr.Audio` não suporta streaming progressivo de output
- Audio input chega como arquivo completo (não chunks)
- Sem controle fino sobre quando tocar áudio
- HTTP request/response, não conexão persistente

**Esta fase cria um servidor WebSocket + frontend Web Audio API pra S2S real.**

O app Gradio (`voice_assistant_app.py`) continua existindo como fallback. NÃO modificar ele.

---

## ARQUITETURA ALVO

```
┌─────────────────────────────────────┐
│           BROWSER (Frontend)         │
│                                     │
│  Mic ──► VAD (RMS) ──► WebSocket   │
│                           │         │
│  Speaker ◄── AudioQueue ◄─┘         │
└──────────────┬──────────────────────┘
               │ WebSocket (ws://host:PORT/ws)
               │   ↑ binary: audio chunks (PCM 16-bit, 16kHz, mono)
               │   ↓ binary: audio response chunks (WAV/MP3)
               │   ↕ JSON: controle (status, transcript, text, errors)
┌──────────────┴──────────────────────┐
│           SERVER (FastAPI)           │
│                                     │
│  AudioBuffer ──► Whisper STT        │
│                     │               │
│               OpenClaw LLM          │
│              (streaming SSE)        │
│                     │               │
│            _find_sentence_end       │
│                     │               │
│              TTS por frase          │
│              (envia WAV/bytes)      │
└─────────────────────────────────────┘
```

### Protocolo WebSocket

**Cliente → Servidor:**
- `binary`: chunks de áudio (PCM 16-bit, 16kHz, mono) — mic do browser
- `{"type": "vad_event", "event": "speech_end"}` — cliente detectou fim de fala
- `{"type": "interrupt"}` — usuário começou a falar enquanto resposta toca (barge-in)
- `{"type": "config", ...}` — configurações opcionais (modelo, whisper, tts engine)

**Servidor → Cliente:**
- `{"type": "status", "status": "listening|thinking|speaking|idle"}` — estado do pipeline
- `{"type": "transcript", "text": "..."}` — transcrição do STT
- `{"type": "text", "text": "...", "done": false}` — texto parcial do LLM (streaming)
- `{"type": "text", "text": "...", "done": true}` — texto final do LLM
- `binary`: áudio TTS (WAV completo por frase — browser toca em fila)
- `{"type": "error", "message": "..."}` — erros

---

## TASK 1: Servidor WebSocket (server_ws.py — arquivo novo na raiz)

Criar `server_ws.py` usando FastAPI + uvicorn + websockets.

```python
"""
OpenClaw Voice Assistant — WebSocket S2S Server
Protocolo: binary (áudio PCM/WAV) + JSON (controle)
"""
import os
import io
import json
import wave
import asyncio
import tempfile
import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.config import load_token, MODEL, WHISPER_MODEL_SIZE
from core.stt import transcribe_audio
from core.tts import init_tts, generate_tts
from core.llm import ask_openclaw_stream, ask_openclaw, _find_sentence_end
from core.history import build_api_history, MAX_HISTORY
```

### Endpoints:
- `GET /` → serve `static/index.html`
- `WS /ws` → conexão WebSocket principal

### Lógica do WebSocket handler:

```python
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

TOKEN = load_token()
init_tts()

@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    
    chat_history = []  # [{"role": "user/assistant", "content": "..."}]
    audio_buffer = bytearray()  # PCM 16-bit, 16kHz, mono
    is_speaking = False  # servidor está gerando resposta?
    
    async def send_json(data):
        await ws.send_json(data)
    
    async def send_status(status):
        await send_json({"type": "status", "status": status})
    
    try:
        while True:
            message = await ws.receive()
            
            if "bytes" in message:
                # Áudio PCM do browser
                if is_speaking:
                    # Barge-in: ignorar áudio enquanto resposta toca
                    # (ou implementar interrupt — ver TASK 5)
                    continue
                audio_buffer.extend(message["bytes"])
            
            elif "text" in message:
                data = json.loads(message["text"])
                
                if data["type"] == "vad_event" and data["event"] == "speech_end":
                    if len(audio_buffer) < 1600:  # <50ms de áudio = ruído
                        audio_buffer.clear()
                        continue
                    
                    # Processar áudio acumulado
                    is_speaking = True
                    await send_status("thinking")
                    
                    # 1. Converter buffer PCM → WAV temporário pra Whisper
                    pcm_data = np.frombuffer(bytes(audio_buffer), dtype=np.int16)
                    audio_buffer.clear()
                    
                    # Salvar como WAV temp
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        wav_path = f.name
                        with wave.open(f, 'wb') as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)  # 16-bit
                            wf.setframerate(16000)
                            wf.writeframes(pcm_data.tobytes())
                    
                    try:
                        # 2. STT
                        transcript = transcribe_audio(wav_path)
                        if not transcript:
                            await send_json({"type": "transcript", "text": ""})
                            await send_status("listening")
                            is_speaking = False
                            continue
                        
                        await send_json({"type": "transcript", "text": transcript})
                        
                        # 3. Adicionar ao histórico
                        chat_history.append({"role": "user", "content": transcript})
                        if len(chat_history) > MAX_HISTORY * 2:
                            chat_history = chat_history[-(MAX_HISTORY * 2):]
                        
                        # 4. LLM streaming + TTS por frase
                        api_history = build_api_history(chat_history[:-1])
                        full_response = ""
                        last_tts_end = 0
                        
                        await send_status("speaking")
                        
                        # Rodar streaming em thread (ask_openclaw_stream é síncrono)
                        loop = asyncio.get_event_loop()
                        
                        # Coletar texto streamed
                        for partial in await loop.run_in_executor(
                            None, lambda: list(ask_openclaw_stream(transcript, TOKEN, api_history))
                        ):
                            full_response = partial
                            await send_json({"type": "text", "text": partial, "done": False})
                            
                            # Checar se tem frase completa pra TTS
                            remaining = partial[last_tts_end:]
                            end = _find_sentence_end(remaining)
                            if end > 0:
                                sentence = remaining[:end].strip()
                                if sentence:
                                    # Gerar TTS em thread
                                    tts_path = await loop.run_in_executor(
                                        None, generate_tts, sentence
                                    )
                                    if tts_path:
                                        with open(tts_path, "rb") as af:
                                            await ws.send_bytes(af.read())
                                        # Cleanup
                                        try:
                                            os.unlink(tts_path)
                                        except OSError:
                                            pass
                                    last_tts_end += end
                        
                        # TTS do texto restante
                        if full_response:
                            remaining = full_response[last_tts_end:].strip()
                            if remaining:
                                tts_path = await loop.run_in_executor(
                                    None, generate_tts, remaining
                                )
                                if tts_path:
                                    with open(tts_path, "rb") as af:
                                        await ws.send_bytes(af.read())
                                    try:
                                        os.unlink(tts_path)
                                    except OSError:
                                        pass
                            
                            await send_json({"type": "text", "text": full_response, "done": True})
                            chat_history.append({"role": "assistant", "content": full_response})
                    
                    finally:
                        # Cleanup WAV temp
                        try:
                            os.unlink(wav_path)
                        except OSError:
                            pass
                        is_speaking = False
                        await send_status("listening")
                
                elif data["type"] == "interrupt":
                    # TODO Fase 3: cancelar LLM + TTS em andamento
                    pass
                
                elif data["type"] == "config":
                    # TODO: permitir mudar modelo/whisper/tts via WS
                    pass
    
    except WebSocketDisconnect:
        pass
```

**ATENÇÃO — Problema no código acima:** O `for partial in await loop.run_in_executor(...)` converte TODO o streaming em lista antes de iterar — isso mata o propósito do streaming. Você PRECISA resolver isso. A solução correta é:

```python
# Usar asyncio.Queue pra bridge entre thread síncrona e async
text_queue = asyncio.Queue()

def _stream_worker():
    """Roda em thread — coloca textos parciais na queue."""
    try:
        for partial in ask_openclaw_stream(transcript, TOKEN, api_history):
            asyncio.run_coroutine_threadsafe(
                text_queue.put(partial), loop
            )
    finally:
        asyncio.run_coroutine_threadsafe(
            text_queue.put(None), loop  # Sentinel
        )

# Iniciar worker em thread
loop.run_in_executor(None, _stream_worker)

# Consumir async
while True:
    partial = await text_queue.get()
    if partial is None:
        break
    full_response = partial
    await send_json({"type": "text", "text": partial, "done": False})
    
    # Checar frase completa pra TTS...
    remaining = partial[last_tts_end:]
    end = _find_sentence_end(remaining)
    if end > 0:
        sentence = remaining[:end].strip()
        if sentence:
            tts_path = await loop.run_in_executor(None, generate_tts, sentence)
            if tts_path:
                with open(tts_path, "rb") as af:
                    await ws.send_bytes(af.read())
                try:
                    os.unlink(tts_path)
                except OSError:
                    pass
            last_tts_end += end
```

**Use a versão com Queue. A versão com `list()` é ERRADA pra streaming.**

### Rodar:

```python
if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "7860"))
    print(f"🚀 S2S WebSocket Server: http://{host}:{port}")
    print(f"   Modelo: {MODEL}")
    print(f"   Whisper: {WHISPER_MODEL_SIZE}")
    uvicorn.run(app, host=host, port=port)
```

---

## TASK 2: Frontend (static/index.html — arquivo novo)

Criar pasta `static/` e arquivo `static/index.html`. Frontend COMPLETO em um único HTML (HTML + CSS + JS inline). Sem frameworks, sem bundler.

### Requisitos funcionais:

1. **Conectar WebSocket** ao servidor (`ws://host:port/ws`)
2. **Capturar mic** via `navigator.mediaDevices.getUserMedia({audio: true})`
3. **Processar áudio** via AudioWorklet ou ScriptProcessorNode:
   - Capturar PCM 16-bit, 16kHz, mono
   - Se mic for 44.1kHz/48kHz, fazer downsample pra 16kHz
   - Enviar chunks de ~100ms (1600 samples) via WebSocket binary
4. **VAD (Voice Activity Detection):**
   - Calcular RMS de cada chunk
   - Threshold: 0.01 (mesmo do BrowserContinuousListener atual)
   - Se RMS > threshold por ≥200ms → fala detectada
   - Se RMS < threshold por ≥800ms após fala → fim de fala → enviar `{"type": "vad_event", "event": "speech_end"}`
   - Enquanto detecta fala, mostrar indicador visual
5. **Receber e tocar áudio:**
   - Mensagens binary do WebSocket = arquivos WAV/MP3 completos (uma frase cada)
   - Decodificar com `AudioContext.decodeAudioData()`
   - Fila de reprodução: tocar em sequência sem gaps
   - Quando fila esvazia e status volta pra "listening" → voltar a escutar
6. **Exibir texto:**
   - Transcrição do usuário (mensagem `transcript`)
   - Texto do assistente em streaming (mensagens `text` com `done: false/true`)
   - Histórico rolável (últimas 10 trocas)
7. **Indicadores de status:**
   - Baseado nas mensagens `status` do servidor
   - 🔴 Escutando | 🧠 Pensando | 🔊 Falando | ⏸️ Desconectado
8. **Reconexão automática:** se WebSocket desconectar, tentar reconectar a cada 3s

### Layout (CSS inline, dark mode):

```
┌─────────────────────────────────────┐
│  🦅 OpenClaw Voice Assistant        │
│  ● Conectado — 🔴 Escutando         │
├─────────────────────────────────────┤
│                                     │
│  [chat history scrollável]          │
│                                     │
│  Você: "Olá, como vai?"            │
│  🦅: "Tudo bem! Em que posso..."   │
│                                     │
├─────────────────────────────────────┤
│  [visualização de áudio - barras]   │
│  [botão mute/unmute do mic]         │
└─────────────────────────────────────┘
```

### Especificações CSS:
- Dark mode: `background: #1a1a2e`, texto: `#e0e0e0`
- Mobile-first, responsivo
- Mensagens do usuário: alinhadas à direita, fundo `#2d2d44`
- Mensagens do assistente: alinhadas à esquerda, fundo `#252540`
- Status bar fixa no topo
- Font: system-ui, -apple-system, sans-serif
- Scrollbar custom (fina, tema escuro)

### JavaScript — Estrutura:

```javascript
// ─── Config ──────────────────────────────────────────
const WS_URL = `ws://${window.location.host}/ws`;
const SAMPLE_RATE = 16000;
const CHUNK_SIZE = 1600;  // 100ms de áudio
const VAD_THRESHOLD = 0.01;
const SPEECH_MIN_MS = 200;
const SILENCE_MS = 800;

// ─── State ───────────────────────────────────────────
let ws = null;
let audioContext = null;
let mediaStream = null;
let processor = null;
let isMuted = false;

// VAD state
let isSpeaking = false;
let speechStart = 0;
let silenceStart = 0;

// Audio playback queue
let playbackQueue = [];
let isPlaying = false;

// ─── WebSocket ───────────────────────────────────────
function connect() { ... }
function onMessage(event) {
    if (event.data instanceof Blob) {
        // Áudio do servidor → adicionar à fila
        enqueueAudio(event.data);
    } else {
        const data = JSON.parse(event.data);
        switch (data.type) {
            case "status": updateStatus(data.status); break;
            case "transcript": addUserMessage(data.text); break;
            case "text": updateAssistantMessage(data.text, data.done); break;
            case "error": showError(data.message); break;
        }
    }
}

// ─── Audio Capture ───────────────────────────────────
async function startMic() {
    mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: SAMPLE_RATE, channelCount: 1, echoCancellation: true }
    });
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
    // ... ScriptProcessorNode ou AudioWorklet
    // Downsample se necessário
    // Enviar chunks PCM 16-bit via ws.send(buffer)
}

// ─── VAD ─────────────────────────────────────────────
function processAudioChunk(float32Array) {
    // Calcular RMS
    let sum = 0;
    for (let i = 0; i < float32Array.length; i++) {
        sum += float32Array[i] * float32Array[i];
    }
    const rms = Math.sqrt(sum / float32Array.length);
    
    // Atualizar visualização
    updateVolumeBar(rms);
    
    if (rms > VAD_THRESHOLD) {
        if (!isSpeaking) {
            if (Date.now() - speechStart < SPEECH_MIN_MS) return;
            isSpeaking = true;
            speechStart = Date.now();
        }
        silenceStart = 0;
    } else if (isSpeaking) {
        if (silenceStart === 0) silenceStart = Date.now();
        if (Date.now() - silenceStart > SILENCE_MS) {
            // Fim de fala detectado
            isSpeaking = false;
            ws.send(JSON.stringify({type: "vad_event", event: "speech_end"}));
        }
    }
    
    // Converter float32 → int16 e enviar
    if (!isMuted && ws && ws.readyState === WebSocket.OPEN) {
        const int16 = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, float32Array[i] * 32768));
        }
        ws.send(int16.buffer);
    }
}

// ─── Audio Playback ──────────────────────────────────
async function enqueueAudio(blob) {
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    playbackQueue.push(audioBuffer);
    if (!isPlaying) playNext();
}

function playNext() {
    if (playbackQueue.length === 0) {
        isPlaying = false;
        return;
    }
    isPlaying = true;
    const buffer = playbackQueue.shift();
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.onended = () => playNext();
    source.start();
}
```

**IMPORTANTE sobre Audio Capture:**

O browser pode NÃO respeitar `sampleRate: 16000` no getUserMedia — muitos retornam 44100 ou 48000. O código PRECISA verificar `audioContext.sampleRate` e fazer downsample se necessário:

```javascript
function downsample(float32Array, fromRate, toRate) {
    if (fromRate === toRate) return float32Array;
    const ratio = fromRate / toRate;
    const newLength = Math.round(float32Array.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
        result[i] = float32Array[Math.round(i * ratio)];
    }
    return result;
}
```

**IMPORTANTE sobre ScriptProcessorNode:**

`ScriptProcessorNode` é deprecated mas funciona em TODOS os browsers. `AudioWorklet` é melhor mas mais complexo (precisa de arquivo separado). **Usar ScriptProcessorNode** nesta fase — migrar pra AudioWorklet na Fase 3 se necessário.

```javascript
const source = audioContext.createMediaStreamSource(mediaStream);
processor = audioContext.createScriptProcessor(4096, 1, 1);
processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    const downsampled = downsample(input, audioContext.sampleRate, SAMPLE_RATE);
    processAudioChunk(downsampled);
};
source.connect(processor);
processor.connect(audioContext.destination);  // Necessário pra funcionar
```

---

## TASK 3: Dependências (requirements.txt)

Adicionar ao `requirements.txt` existente (NÃO substituir, ADICIONAR):

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
```

Verificar que não conflita com dependências existentes.

---

## TASK 4: Atualizar scripts de conexão

Nos 6 scripts de conexão (`scripts/run_*.sh` e `scripts/run_*.ps1`), mudar o comando de `python voice_assistant_app.py` pra `python server_ws.py`.

Adicionar uma variável `APP_MODE` com fallback:

**Exemplo (run_local.sh):**
```bash
APP_MODE="${APP_MODE:-websocket}"

if [ "$APP_MODE" = "gradio" ]; then
    echo "📻 Modo: Gradio (fallback)"
    python voice_assistant_app.py
else
    echo "🔌 Modo: WebSocket S2S"
    python server_ws.py
fi
```

Fazer o mesmo nos 6 scripts. Default = `websocket`. `APP_MODE=gradio` pra fallback.

---

## TASK 5: Mute do mic durante playback (echo cancellation extra)

No frontend, quando o servidor envia status `"speaking"`:
1. Parar de enviar chunks de áudio pro servidor (evita eco)
2. Manter VAD ativo mas não enviar `speech_end`
3. Quando status volta pra `"listening"`, retomar envio

```javascript
let serverSpeaking = false;

function updateStatus(status) {
    serverSpeaking = (status === "speaking");
    // Atualizar UI...
}

// No processAudioChunk:
if (serverSpeaking || isMuted) return;  // Não enviar áudio
```

---

## TASK 6: Atualizar .env.example

Adicionar ao `.env.example`:

```env
# App mode
APP_MODE=websocket  # websocket (S2S real) | gradio (fallback)
```

---

## TASK 7: Tratamento de erros robusto no servidor

No WebSocket handler, garantir que:

1. **STT falha** → enviar `{"type": "error", "message": "Não captei o áudio"}` + voltar pra listening
2. **LLM falha** → fallback pra `ask_openclaw` síncrono. Se também falhar → enviar error
3. **TTS falha** → enviar texto sem áudio (degradação graciosa)
4. **WebSocket fecha durante processamento** → cleanup graceful (não crashar servidor)
5. **Áudio muito curto** (< 50ms / < 1600 bytes) → ignorar silenciosamente
6. **Token inválido** → enviar error com mensagem clara na conexão

---

## Verificação final

1. **Instalar deps novas:**
   ```bash
   pip install fastapi uvicorn[standard] websockets
   ```

2. **Syntax check:**
   ```bash
   python -c "import server_ws"
   ```

3. **Verificar que Gradio app ainda funciona:**
   ```bash
   python -c "import voice_assistant_app"
   ```

4. **Verificar estrutura:**
   ```
   ls static/index.html    # Deve existir
   ls server_ws.py          # Deve existir
   ```

5. **Testes existentes devem continuar passando:**
   ```bash
   lsof -ti:7860 | xargs kill -9 2>/dev/null
   python -m pytest tests/ -v
   ```
   Os testes testam core/ e voice_assistant_app.py — nada deve quebrar.

6. **Teste manual (se possível):**
   ```bash
   lsof -ti:7860 | xargs kill -9 2>/dev/null
   python server_ws.py
   ```
   Abrir `http://127.0.0.1:7860` no browser e verificar que:
   - Página carrega (dark mode)
   - Pede permissão de microfone
   - WebSocket conecta (indicador verde)
   - Status mostra "Escutando"

7. **Commit:**
   ```bash
   git add -A && git commit -m "feat: fase 2 - WebSocket S2S server + Web Audio frontend"
   ```

8. **NÃO fazer git push**

---

## Arquivos que DEVEM ser criados/modificados

### Criados:
- `server_ws.py` — servidor WebSocket (FastAPI + uvicorn)
- `static/index.html` — frontend completo (HTML + CSS + JS inline)

### Modificados:
- `requirements.txt` — adicionar fastapi, uvicorn, websockets
- `scripts/run_local.sh` — APP_MODE + fallback
- `scripts/run_vps.sh` — APP_MODE + fallback
- `scripts/run_local_remote_gateway.sh` — APP_MODE + fallback
- `scripts/run_local.ps1` — APP_MODE + fallback
- `scripts/run_vps.ps1` — APP_MODE + fallback
- `scripts/run_local_remote_gateway.ps1` — APP_MODE + fallback
- `.env.example` — adicionar APP_MODE

### NÃO modificar:
- `voice_assistant_app.py` — continua como fallback Gradio
- `voice_assistant_cli.py` — CLI separado
- `core/*` — módulos compartilhados ficam intactos
- `tests/*` — testes existentes continuam passando
- `CLAUDE.md` — já atualizado
- `README.md` — já atualizado
