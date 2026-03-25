# CLAUDE.md — Contexto para Claude Code

> Este é o único arquivo de contexto que você precisa ler.
> Última atualização: 2026-03-24 (S1-S9 completos)

## O que é este projeto

Voice assistant **Speech-to-Speech (S2S)** conectado ao OpenClaw Gateway. O usuário fala → VAD detecta silêncio → Whisper transcreve → OpenClaw responde em streaming → TTS gera áudio por frase → usuário ouve.

**Pipeline:**
```
VOZ → VAD (RMS) → STT (Whisper) → LLM streaming (OpenClaw SSE) → TTS → VOZ
```

## Arquitetura do código

```
run.sh                   ─ Script "faz tudo" Linux/Mac (setup + server + browser)
run.ps1                  ─ Script "faz tudo" Windows PowerShell
server_ws.py             ─ Servidor WebSocket S2S (FastAPI + uvicorn) — PRINCIPAL
static/index.html        ─ Frontend completo (HTML + CSS + JS inline, 39KB)
static/marked.min.js     ─ marked v15 (local, não CDN)
voice_assistant_cli.py   ─ CLI terminal (alternativa ao browser)
pyproject.toml           ─ Configuração do pacote Python (pip install, entry point `ova`)
package.json             ─ Manifesto npm (plugin OpenClaw)
openclaw.plugin.json     ─ Manifesto do plugin OpenClaw (config schema)
index.ts                 ─ Entry point do plugin (registra /ova, gerencia processo Python)

core/
  __init__.py            ─ Marca core/ como pacote Python
  __main__.py            ─ Entry point do comando `ova` (argparse + banner + uvicorn)
  config.py              ─ Env vars + constantes + load_token()
  history.py             ─ Chat history (MAX_HISTORY = 20 exchanges)
  llm.py                 ─ Cliente OpenClaw (streaming SSE + sync)
  stt.py                 ─ Whisper STT (lazy loading, thread-safe, model swap runtime)
  tts.py                 ─ TTS multi-engine (kokoro → piper → edge) + _strip_markdown()

scripts/                 ─ Scripts de execução (3 cenários × sh + ps1)
tests/                   ─ 111 testes (pytest)
docs/SECURITY.md         ─ Modelo de autenticação
arquivo/                 ─ Histórico (auditorias, prompts executados, testes antigos)
```

## Features implementadas (S1-S8)

| Área | Features |
|------|----------|
| **Interface** | Disconnect, Interrupt manual, Input de texto, Timer "Pensando", Esfera pulsante (CSS), Markdown (marked.js), Config panel |
| **Áudio** | Whisper small/tiny configurável, Seletor de vozes TTS, Velocidade TTS |
| **Latência** | Keep-alive HTTP (Session), Split agressivo de frases, VAD otimizado, Métricas TTFA no console |
| **Transporte** | Backoff exponencial (3→6→12→30s), Ping/pong keep-alive (25s), Session persistence (localStorage + restore) |
| **Robustez** | Markdown strip no TTS, Timeout LLM 120s, Race protection (processing flag), Cleanup no disconnect, Aviso sessão longa (30 msgs) |
| **Deploy** | setup.ps1 (Windows), setup.sh (Linux/Mac), CI GitHub Actions, .env.example |
| **Segurança** | Auth por token (.ova_token, só se SERVER_HOST ≠ localhost), XSS fix (marked renderer), Rate limit (2s texto, 1s speech), Buffer limit (10MB), Input validation (2000 chars), Erros genéricos (sem stack pro client) |
| **Conversação** | Timestamps (ISO + visual HH:MM), Export JSON (botão no config panel) |
| **Execução** | `run.sh`/`run.ps1` (1 comando faz tudo), `pyproject.toml`, comando `ova` via pip, `--help`, `--version` |

## Variáveis de ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `OPENCLAW_GATEWAY_URL` | `http://127.0.0.1:18789/v1/chat/completions` | Endpoint do gateway |
| `OPENCLAW_GATEWAY_TOKEN` | (auto de `~/.openclaw/openclaw.json`) | Override do token |
| `OPENCLAW_MODEL` | `anthropic/claude-sonnet-4-6` | Modelo LLM |
| `WHISPER_MODEL` | `tiny` | `tiny` (~1-2s) / `small` (~3-5s, mais preciso) |
| `TTS_ENGINE` | `edge` | `edge` (online) / `piper` (local) / `kokoro` (local, melhor) |
| `TTS_VOICE` | `pt-BR-AntonioNeural` | Voz Edge TTS |
| `SERVER_HOST` | `127.0.0.1` | `0.0.0.0` pra acesso remoto (ativa auth) |
| `PORT` | `7860` | Porta do servidor |

Token carregado automaticamente de `~/.openclaw/openclaw.json` (`gateway.auth.token`).

## 3 Cenários de Deploy

A diferença é infra (tunnels), NÃO código.

```
CENÁRIO 1: TUDO LOCAL      → Browser ↔ Voice App ↔ OpenClaw (tudo localhost)
CENÁRIO 2: TUDO VPS        → Browser ─(SSH :7860)─ Voice App ↔ OpenClaw (VPS)
CENÁRIO 3: LOCAL → VPS     → Browser ↔ Voice App (local) ─(SSH :18789)─ OpenClaw (VPS)
```

## Dependências entre arquivos

```
server_ws.py
  ├── core/config.py      (GATEWAY_URL, MODEL, WHISPER_MODEL_SIZE, load_token)
  ├── core/stt.py          (transcribe_audio, init_stt, get_current_model, set_whisper_model)
  ├── core/tts.py          (generate_tts, init_tts, _strip_markdown, set_tts_speed, get_tts_speed, list_edge_voices)
  ├── core/llm.py          (ask_openclaw_stream, ask_openclaw, _find_sentence_end, _session)
  ├── core/history.py      (build_api_history, MAX_HISTORY)
  └── static/index.html    (servido como FileResponse)

static/index.html
  └── static/marked.min.js (marked v15 — carregado via <script>)

voice_assistant_cli.py
  ├── core/config.py
  ├── core/stt.py
  ├── core/tts.py
  └── core/llm.py

core/config.py            ─ Sem dependências internas (só os, json)
core/history.py           ─ Sem dependências internas
core/llm.py               ─ core/config.py (GATEWAY_URL, MODEL, load_token)
core/stt.py               ─ core/config.py (WHISPER_MODEL_SIZE)
core/tts.py               ─ Sem dependências internas (só libs externas)

index.ts (Plugin OpenClaw)
  ├── package.json           (metadados npm + openclaw.extensions)
  ├── openclaw.plugin.json   (config schema + plugin id)
  ├── setup.ps1 / setup.sh   (setup automático do Python, chamado se venv não existe)
  ├── core/__main__.py        (entry point `ova`, chamado via spawn)
  ├── .ova_token              (lido para incluir na URL, gerado pelo server_ws.py)
  └── venv/                   (verificado antes de iniciar, criado pelo setup se ausente)
```

## Partes frágeis (entender antes de mexer)

1. **`ask_openclaw_stream` (core/llm.py)** — Parser SSE manual (delta.content, [DONE]). Quebra se formato mudar.
2. **`_find_sentence_end` (core/llm.py)** — Detecta fim de frase pra split TTS. NÃO detecta `\n` ainda — última frase sem pontuação pode atrasar TTS.
3. **`load_token` (core/config.py)** — Lê `~/.openclaw/openclaw.json`. Estrutura: `gateway.auth.token`.
4. **`generate_tts` (core/tts.py)** — Edge TTS roda em ThreadPoolExecutor (event loop do FastAPI). `asyncio.run()` direto crasharia.
5. **`_strip_markdown` (core/tts.py)** — Regex chain pra limpar markdown antes do TTS. Ordem dos regex importa (bold+italic antes de bold antes de italic).
6. **Barge-in (server_ws.py)** — `cancel_event` + `asyncio.create_task`. Task precisa checar `cancel_event` frequentemente.
7. **Audio playback queue (index.html)** — `playNext()` encadeia via `onended`. Se `decodeAudioData` falhar, fila trava — tem try/catch (S5 fix).
8. **Session persistence (index.html)** — `chatMessages[]` no localStorage. Frontend envia `restore_history` ao reconectar. Server valida e aceita até 20 msgs × 5000 chars.
9. **Auth (server_ws.py)** — Token em `.ova_token`. Só ativo se `SERVER_HOST ≠ localhost`. WebSocket fecha com 4003 se token errado.
10. **Rate limit (server_ws.py)** — `_last_text_time` (2s cooldown) e `_last_speech_time` (1s cooldown). Per-connection, não global.
11. **Entry point `ova` (core/__main__.py)** — Seta env vars ANTES de importar core/config.py. Usa `importlib.import_module` pra importar `server_ws` (está na raiz, não em core/). `sys.path.insert(0, project_root)` resolve o import.

## ⚠️ Gestão de processos

```powershell
# Windows — antes de rodar server ou testes:
Get-Process -Name python* -ErrorAction SilentlyContinue | Stop-Process -Force

# Testes:
python -m pytest tests/ -v
```

**NUNCA deixar processos python em background.** Cada `python server_ws.py` que não é parado fica como zumbi.

## Convenções

- Python 3.10+ (roda em 3.13 localmente)
- Português nos comentários e UI
- Testes com pytest + unittest.mock (111 testes)
- Sem type hints
- Imports: stdlib → third-party → locais
