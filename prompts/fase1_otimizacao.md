# FASE 1 — Otimização de Latência + Cleanup

Leia estes arquivos nesta ordem antes de qualquer ação:
1. CLAUDE.md (se existir)
2. core/config.py
3. core/llm.py
4. core/tts.py
5. core/stt.py
6. voice_assistant_app.py (INTEIRO — é o arquivo principal, ~600 linhas)
7. BUGS_PENDENTES.md

NÃO leia os testes ainda. Primeiro entenda o código fonte.

## CONTEXTO

Voice assistant conectado ao OpenClaw Gateway. Pipeline atual:
```
VAD → Whisper STT → OpenClaw LLM (streaming) → TTS (buffer duplo por frase) → Gradio UI
```

Problema principal: latência de ~35s entre fala do usuário e primeira resposta em áudio.
- LLM (Opus 4): 31.4s TTFT ← 90% do bottleneck
- Whisper (small): 3-5s
- TTS: 1-3s
- Sentence split muito conservador (só .!?) → TTS espera frase inteira

Esta fase otimiza SEM mudar a arquitetura (Gradio se mantém).

---

## TASK 1: Modelo LLM mais rápido (core/config.py)

Mudar o default de `OPENCLAW_MODEL`:

```python
# ANTES:
MODEL = os.environ.get("OPENCLAW_MODEL", "openclaw:main")

# DEPOIS:
MODEL = os.environ.get("OPENCLAW_MODEL", "anthropic/claude-sonnet-4-6")
```

**Motivo:** `openclaw:main` usa Opus 4 (TTFT ~31s). Sonnet 4.6 tem TTFT ~2-4s.
O usuário pode sobrescrever com env var se quiser outro modelo.

---

## TASK 2: Whisper tiny como default (core/config.py)

```python
# ANTES:
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")

# DEPOIS:
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "tiny")
```

**Motivo:** `small` = 3-5s de transcrição. `tiny` = 1-2s. Pra conversação por voz, velocidade importa mais que precisão marginal. Quem quiser `small` usa env var.

---

## TASK 3: Split de texto mais agressivo (core/llm.py)

A função `_find_sentence_end` atual só procura `.!?…` — isso faz o TTS esperar frases inteiras (às vezes 2-3 linhas). Pra voice, queremos splits menores.

Reescrever `_find_sentence_end` para:

```python
def _find_sentence_end(text):
    """Encontra ponto de split pra TTS em texto parcial do LLM.
    
    Prioridade:
    1. Pontuação forte (.!?…) seguida de espaço ou fim
    2. Ponto-e-vírgula ou dois-pontos seguidos de espaço
    3. Vírgula seguida de espaço (só se texto > 80 chars — evita splits muito curtos)
    
    Retorna posição APÓS o separador (incluindo o espaço). 0 se não encontrou.
    """
    import re
    
    # Prioridade 1: pontuação forte
    m = re.search(r'[.!?…](\s|$)', text)
    if m:
        return m.end()
    
    # Prioridade 2: ponto-e-vírgula, dois-pontos
    m = re.search(r'[;:](\s|$)', text)
    if m:
        return m.end()
    
    # Prioridade 3: vírgula (só se texto longo o suficiente)
    if len(text) > 80:
        m = re.search(r',\s', text)
        if m:
            return m.end()
    
    return 0
```

**Motivo:** Com split na vírgula (texto >80 chars), o TTS começa a gerar áudio ~2-3s antes de esperar o ponto final. Reduz percepção de latência.

---

## TASK 4: Extrair buffer duplo TTS (voice_assistant_app.py)

BUGS_PENDENTES.md documenta: `respond_text()`, `respond_audio()` e `_process_voice_text()` têm ~30 linhas IDÊNTICAS de lógica de buffer duplo. Corrigir bug no buffer = editar em 3 lugares.

**Criar um generator compartilhado.** Identificar o padrão duplicado nos 3 métodos:

```python
def _stream_response_with_tts(text, token, chat_history):
    """Generator compartilhado: LLM streaming + buffer duplo TTS.
    
    Yields: (chat_history_updated, audio_path_or_None, status_html)
    
    Usado por respond_text, respond_audio e _process_voice_text.
    """
    api_history = build_api_history(chat_history[:-1])
    
    full_response = ""
    last_tts_end = 0
    audio = None
    tts_future = None
    tts_end_pos = 0
    
    try:
        for partial in ask_openclaw_stream(text, TOKEN, api_history):
            full_response = partial
            updated = chat_history + [{"role": "assistant", "content": partial}]
            
            # Se TTS em background ficou pronto, emitir áudio
            if tts_future and tts_future.done():
                result = tts_future.result()
                if result:
                    audio = result
                    last_tts_end = tts_end_pos
                tts_future = None
                yield updated, audio, STATUS_SPEAKING
                continue
            
            # Procurar nova frase pra gerar TTS em background
            if not tts_future:
                remaining = partial[last_tts_end:]
                end = _find_sentence_end(remaining)
                if end > 0:
                    sentence = remaining[:end].strip()
                    if sentence:
                        tts_future = _tts_executor.submit(generate_tts, sentence)
                        tts_end_pos = last_tts_end + end
            
            yield updated, audio, STATUS_THINKING
        
        # Aguardar TTS pendente
        if tts_future:
            try:
                result = tts_future.result(timeout=30)
                if result:
                    audio = result
                    last_tts_end = tts_end_pos
            except Exception:
                pass
            tts_future = None
        
        # TTS do resto do texto
        if full_response:
            final = chat_history + [{"role": "assistant", "content": full_response}]
            remaining = full_response[last_tts_end:].strip()
            if remaining:
                final_audio = generate_tts(remaining)
                if final_audio:
                    audio = final_audio
            yield final, audio, STATUS_IDLE
        else:
            # Streaming falhou silenciosamente — fallback síncrono
            response = ask_openclaw(text, TOKEN, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield final, audio, STATUS_IDLE
    
    except Exception:
        # Cancelar TTS pendente antes do fallback
        if tts_future:
            tts_future.cancel()
        
        response = ask_openclaw(text, TOKEN, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield final, audio, STATUS_IDLE
```

**Depois, simplificar os 3 métodos:**

`respond_text` fica:
```python
def respond_text(user_message, chat_history):
    if not user_message or not user_message.strip():
        yield "", chat_history, None, STATUS_IDLE
        return
    
    text = user_message.strip()
    chat_history = chat_history + [{"role": "user", "content": text}]
    
    yield "", chat_history, None, STATUS_THINKING
    
    for updated, audio, status in _stream_response_with_tts(text, TOKEN, chat_history):
        yield "", updated, audio, status
```

`respond_audio` fica:
```python
def respond_audio(audio_input, chat_history):
    if audio_input is None:
        yield chat_history, None, STATUS_IDLE
        return
    
    yield chat_history, None, STATUS_THINKING
    
    text = transcribe_audio(audio_input)
    if not text:
        yield chat_history + [
            {"role": "assistant", "content": "⚠️ Não captei áudio — tenta de novo"}
        ], None, STATUS_IDLE
        return
    
    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
    
    for updated, audio, status in _stream_response_with_tts(text, TOKEN, chat_history):
        yield updated, audio, status
```

`_process_voice_text` fica:
```python
def _process_voice_text(text, chat_history):
    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
    
    for updated, audio, status in _stream_response_with_tts(text, TOKEN, chat_history):
        yield updated, audio, status
```

**Verificação:** após refatorar, os 3 métodos NÃO devem ter NENHUMA lógica de `ask_openclaw_stream`, `_find_sentence_end`, `tts_future`, `_tts_executor` — tudo fica em `_stream_response_with_tts`.

---

## TASK 5: Fix tts_future em exceções (já incluído na Task 4)

A Task 4 já inclui `tts_future.cancel()` no bloco `except`. Verificar que NENHUM dos 3 métodos simplificados tem lógica de fallback própria — tudo delegado pro `_stream_response_with_tts`.

---

## TASK 6: CSS duplicado (voice_assistant_app.py)

Procurar onde `CUSTOM_CSS` aparece. Se aparece em AMBOS `gr.Blocks(css=...)` e `app.launch(css=...)`, remover de `app.launch()`. Manter só em `gr.Blocks(css=CUSTOM_CSS)`.

---

## TASK 7: Scripts de conexão (3 cenários)

Criar pasta `scripts/` (se não existir) com 3 scripts:

### scripts/run_local.sh
```bash
#!/bin/bash
# Cenário 1: Tudo local (laptop com OpenClaw)
# Requisitos: OpenClaw Gateway rodando local em :18789

export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1/chat/completions"
export OPENCLAW_MODEL="${OPENCLAW_MODEL:-anthropic/claude-sonnet-4-6}"
export WHISPER_MODEL="${WHISPER_MODEL:-tiny}"
export TTS_ENGINE="${TTS_ENGINE:-edge}"
export SERVER_HOST="127.0.0.1"

echo "🚀 Cenário: LOCAL (tudo no laptop)"
echo "   Gateway: $OPENCLAW_GATEWAY_URL"
echo "   Modelo: $OPENCLAW_MODEL"
echo "   Whisper: $WHISPER_MODEL"
echo "   TTS: $TTS_ENGINE"
echo ""

python voice_assistant_app.py
```

### scripts/run_vps.sh
```bash
#!/bin/bash
# Cenário 2: Tudo na VPS (voice app + OpenClaw na VPS)
# Requisitos: OpenClaw Gateway rodando na VPS em :18789
# Acesso: ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>

export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1/chat/completions"
export OPENCLAW_MODEL="${OPENCLAW_MODEL:-anthropic/claude-sonnet-4-6}"
export WHISPER_MODEL="${WHISPER_MODEL:-tiny}"
export TTS_ENGINE="${TTS_ENGINE:-edge}"
export SERVER_HOST="0.0.0.0"

echo "🚀 Cenário: VPS (tudo remoto)"
echo "   Gateway: $OPENCLAW_GATEWAY_URL"
echo "   Modelo: $OPENCLAW_MODEL"
echo "   Whisper: $WHISPER_MODEL"
echo "   TTS: $TTS_ENGINE"
echo ""
echo "📡 Acesse via: ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>"
echo "   Depois abra: http://127.0.0.1:7860"
echo ""

python voice_assistant_app.py
```

### scripts/run_local_remote_gateway.sh
```bash
#!/bin/bash
# Cenário 3: Voice app local → OpenClaw na VPS
# Requisitos: Tunnel SSH para gateway da VPS
# Setup: ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>

export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1/chat/completions"
export OPENCLAW_MODEL="${OPENCLAW_MODEL:-anthropic/claude-sonnet-4-6}"
export WHISPER_MODEL="${WHISPER_MODEL:-tiny}"
export TTS_ENGINE="${TTS_ENGINE:-edge}"
export SERVER_HOST="127.0.0.1"

echo "🚀 Cenário: LOCAL → VPS (voice app local, OpenClaw remoto)"
echo "   Gateway: $OPENCLAW_GATEWAY_URL (via SSH tunnel)"
echo "   Modelo: $OPENCLAW_MODEL"
echo "   Whisper: $WHISPER_MODEL"
echo "   TTS: $TTS_ENGINE"
echo ""
echo "⚠️  Certifique-se de que o tunnel SSH está ativo:"
echo "    ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>"
echo ""

python voice_assistant_app.py
```

**Importante:** `chmod +x scripts/run_*.sh` após criar.

Também criar versões `.ps1` (PowerShell) dos 3 scripts para Windows:

### scripts/run_local.ps1
```powershell
# Cenário 1: Tudo local (laptop com OpenClaw)
$env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
if (-not $env:OPENCLAW_MODEL) { $env:OPENCLAW_MODEL = "anthropic/claude-sonnet-4-6" }
if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = "tiny" }
if (-not $env:TTS_ENGINE) { $env:TTS_ENGINE = "edge" }
$env:SERVER_HOST = "127.0.0.1"

Write-Host "🚀 Cenário: LOCAL (tudo no laptop)"
Write-Host "   Gateway: $env:OPENCLAW_GATEWAY_URL"
Write-Host "   Modelo: $env:OPENCLAW_MODEL"
Write-Host "   Whisper: $env:WHISPER_MODEL"
Write-Host "   TTS: $env:TTS_ENGINE"

python voice_assistant_app.py
```

### scripts/run_vps.ps1
```powershell
# Cenário 2: Tudo na VPS
$env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
if (-not $env:OPENCLAW_MODEL) { $env:OPENCLAW_MODEL = "anthropic/claude-sonnet-4-6" }
if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = "tiny" }
if (-not $env:TTS_ENGINE) { $env:TTS_ENGINE = "edge" }
$env:SERVER_HOST = "0.0.0.0"

Write-Host "🚀 Cenário: VPS (tudo remoto)"
Write-Host "   Gateway: $env:OPENCLAW_GATEWAY_URL"
Write-Host "   Modelo: $env:OPENCLAW_MODEL"
Write-Host "📡 Acesse via: ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>"

python voice_assistant_app.py
```

### scripts/run_local_remote_gateway.ps1
```powershell
# Cenário 3: Voice app local → OpenClaw na VPS
$env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
if (-not $env:OPENCLAW_MODEL) { $env:OPENCLAW_MODEL = "anthropic/claude-sonnet-4-6" }
if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = "tiny" }
if (-not $env:TTS_ENGINE) { $env:TTS_ENGINE = "edge" }
$env:SERVER_HOST = "127.0.0.1"

Write-Host "🚀 Cenário: LOCAL → VPS (voice app local, OpenClaw remoto)"
Write-Host "⚠️  Tunnel SSH necessário: ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>"

python voice_assistant_app.py
```

---

## TASK 8: Atualizar .env.example

Atualizar `.env.example` na raiz do projeto com os novos defaults:

```env
# OpenClaw Gateway
OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789/v1/chat/completions
OPENCLAW_GATEWAY_TOKEN=  # auto-detectado de ~/.openclaw/openclaw.json se vazio
OPENCLAW_MODEL=anthropic/claude-sonnet-4-6  # modelo LLM (Sonnet = rápido pra voz)

# Speech-to-Text (Whisper)
WHISPER_MODEL=tiny  # tiny (~1-2s) | small (~3-5s) | medium (~5-8s)

# Text-to-Speech
TTS_ENGINE=edge  # edge (online, rápido) | piper (local) | kokoro (local, melhor qualidade)
TTS_VOICE=pt-BR-AntonioNeural  # voz Edge TTS

# Server
SERVER_HOST=127.0.0.1  # 0.0.0.0 pra acesso remoto (VPS)
PORT=7860
```

---

## Verificação final

Após TODAS as tasks:

1. **Syntax check:** `python -c "import voice_assistant_app"`
2. **Testes:** `python -m pytest tests/ -v`
   - Se testes falharem por causa do novo default de MODEL ou WHISPER_MODEL, corrigir os mocks nos testes pra usar os novos valores
   - Se testes falharem por causa do refactor de `_stream_response_with_tts`, adaptar os mocks
3. **Verificar que NÃO existe mais lógica de buffer duplo duplicada:**
   ```
   grep -n "tts_future" voice_assistant_app.py
   ```
   Deve aparecer APENAS dentro de `_stream_response_with_tts`. ZERO nos 3 métodos simplificados.
4. **Verificar CSS:**
   ```
   grep -n "CUSTOM_CSS" voice_assistant_app.py
   ```
   Deve aparecer em `gr.Blocks(css=CUSTOM_CSS)` e na definição. NÃO em `app.launch()`.

5. **Commit:** `git add -A && git commit -m "perf: fase 1 - otimização latência (Sonnet 4.6, Whisper tiny, split agressivo, cleanup)"`
6. **NÃO fazer git push**
