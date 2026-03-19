# CLAUDE.md — Contexto para Claude Code

## O que é este projeto

Interface de conversação **Speech-to-Speech (S2S)** de baixa latência conectada ao OpenClaw Gateway. O objetivo é minimizar o tempo entre o fim da fala do usuário e o início do áudio de resposta (Time-to-First-Audio).

**Pipeline:**
```
VOZ → VAD → STT (Whisper) → LLM streaming (OpenClaw) → TTS streaming → VOZ
```

**Repo:** https://github.com/quenaisaacdayner-art/openclaw-voice-assistant
**Local:** `C:\Users\quena\projects\openclaw-voice-assistant`

## Objetivo e Roadmap

### Objetivo final
S2S com TTFA (Time-to-First-Audio) < 5 segundos. O OpenClaw é o cérebro — o LLM que processa e responde. O voice app é a interface que conecta voz humana ao OpenClaw.

### Fases
- **Fase 1 (atual):** Otimização de latência sem mudar arquitetura — modelo rápido (Sonnet 4.6), Whisper tiny, split agressivo de texto, cleanup de código
- **Fase 2:** Migrar pra WebSocket + Web Audio API — S2S real com streaming bidirecional de áudio
- **Fase 3:** Polish — TTS streaming nativo, streaming STT, UI, documentação dos 3 cenários

### Estado atual
Protótipo funcional com Gradio. Latência ~35s com Opus 4 → meta ~6-8s após Fase 1.

## 3 Cenários de Deploy

O código suporta 3 cenários. A diferença é infra (tunnels, onde rodar), NÃO código — o voice app sempre fala com `OPENCLAW_GATEWAY_URL` (default: `http://127.0.0.1:18789/v1/chat/completions`).

```
CENÁRIO 1: TUDO LOCAL (laptop com OpenClaw)
  Browser ↔ Voice App ↔ OpenClaw Gateway (tudo localhost)

CENÁRIO 2: TUDO VPS (voice app + OpenClaw na VPS)
  Browser ─(SSH tunnel :7860)─ Voice App ↔ OpenClaw Gateway (tudo na VPS)

CENÁRIO 3: APP LOCAL → OPENCLAW VPS
  Browser ↔ Voice App (local) ─(SSH tunnel :18789)─ OpenClaw Gateway (VPS)
```

Scripts de conexão em `scripts/run_local.sh`, `run_vps.sh`, `run_local_remote_gateway.sh` (+ versões .ps1 pra Windows).

## Arquitetura do código

```
core/                    — Módulos compartilhados (fonte única de verdade)
  config.py              — Configuração central (env vars, constantes)
  history.py             — Gerenciamento de histórico de chat
  llm.py                 — Cliente OpenClaw API (streaming SSE + sync)
  stt.py                 — Whisper STT wrapper (lazy loading thread-safe)
  tts.py                 — Multi-engine TTS (kokoro → piper → edge fallback)

voice_assistant_app.py   — App Gradio unificado (auto-detecta LOCAL vs BROWSER)
voice_assistant_cli.py   — CLI terminal

tests/                   — ~233 testes (pytest)
auditoria/               — Logs de auditoria das fases de upgrade
prompts/                 — Prompts auto-contidos pra cada fase
scripts/                 — Scripts de conexão (3 cenários × sh + ps1)
models/                  — Modelos TTS locais (download automático)
```

## Stack

| Componente | Ferramenta | Nota |
|-----------|-----------|------|
| **VAD (local)** | RealtimeSTT (Silero VAD + PyAudio) | Detecta fala/silêncio automaticamente |
| **VAD (browser)** | BrowserContinuousListener (RMS energy) | Streaming chunks do browser |
| **STT** | faster-whisper (default: `tiny`, ~75MB, CPU) | `WHISPER_MODEL=small` pra melhor precisão |
| **LLM** | OpenClaw Gateway (default: `anthropic/claude-sonnet-4-6`) | Streaming SSE |
| **TTS** | Kokoro → Piper → Edge TTS (fallback chain) | Edge = online, rápido; Kokoro/Piper = local |
| **UI** | Gradio 6.9 (dark mode, mobile) | Fase 2 migra pra WebSocket |

## ⚠️ GESTÃO DE PROCESSOS — OBRIGATÓRIO

**Cada `python app.py` que não é parado com Ctrl+C fica como processo zumbi. Processos acumulados já travaram o WSL inteiro (19/03).**

### Regras INEGOCIÁVEIS:

1. **ANTES de rodar qualquer teste ou server:**
   ```bash
   lsof -ti:7860 | xargs kill -9 2>/dev/null
   ```

2. **Pra parar um servidor:** Ctrl+C (NUNCA fechar a aba)

3. **Limpeza se suspeitar de acumulação:**
   ```bash
   ps aux | grep python
   killall python3
   ```

4. **Antes de pytest:** matar server primeiro
   ```bash
   lsof -ti:7860 | xargs kill -9 2>/dev/null
   python -m pytest tests/ -v
   ```

5. **Nunca deixar processos python em background sem propósito.**

## Partes frágeis (entender antes de mexer)

1. **`ask_openclaw_stream` (core/llm.py)** — parser SSE (delta.content, [DONE]). Quebra silenciosamente se formato mudar.
2. **`gr.skip()` no app** — race condition Gradio. Sem `gr.skip()`, Timer sobrescreve outputs de outros handlers. OBRIGATÓRIO em retornos sem mudança.
3. **`load_token` (core/config.py)** — lê de `~/.openclaw/openclaw.json`. Estrutura: `gateway.auth.token`.
4. **`generate_tts` (core/tts.py)** — Edge TTS roda em ThreadPoolExecutor separado porque Gradio 6.x já tem event loop. `asyncio.run()` direto crasharia.
5. **`_detect_mode()` (app)** — Thread com timeout 15s pra importar RealtimeSTT. Startup lento mas funciona.
6. **`ContinuousListener` (modo LOCAL)** — RealtimeSTT com Silero VAD em thread daemon.
7. **`BrowserContinuousListener` (modo BROWSER)** — VAD manual por RMS. `audio_input.stream()` → `feed_chunk()`.

## Variáveis de ambiente

Definidas em `.env` (ver `.env.example`):

| Variável | Default | Descrição |
|----------|---------|-----------|
| `OPENCLAW_GATEWAY_URL` | `http://127.0.0.1:18789/v1/chat/completions` | Endpoint do gateway |
| `OPENCLAW_GATEWAY_TOKEN` | (auto de `~/.openclaw/openclaw.json`) | Override do token |
| `OPENCLAW_MODEL` | `anthropic/claude-sonnet-4-6` | Modelo LLM (Sonnet = rápido pra voz) |
| `WHISPER_MODEL` | `tiny` | STT: `tiny` (~1-2s) / `small` (~3-5s) |
| `TTS_ENGINE` | `edge` | `edge` (online) / `piper` (local) / `kokoro` (local, melhor) |
| `TTS_VOICE` | `pt-BR-AntonioNeural` | Voz Edge TTS |
| `SERVER_HOST` | `127.0.0.1` | `0.0.0.0` pra acesso remoto |
| `PORT` | `7860` | Porta Gradio |

## Convenções

- Python 3.10+ (roda em 3.13 localmente)
- Português nos comentários e UI
- Testes com pytest + unittest.mock
- Sem type hints (manter)
- Imports: stdlib → third-party → locais
- `gr.skip()` obrigatório pra retornos sem mudança em streaming handlers
- `gr.Audio` NÃO suporta streaming progressivo de output (limitação Gradio)

## Testes

```bash
lsof -ti:7860 | xargs kill -9 2>/dev/null
python -m pytest tests/ -v
```

~233 testes (215-219 pass, 14-18 skip). Skips por `_detect_mode` timeout — threading não-determinístico.
