# CLAUDE.md — Contexto para Claude Code

> Leia este arquivo antes de qualquer mudança no código.

## O que é

Plugin **OpenClaw** que adiciona o comando `/ova` — voice assistant Speech-to-Speech.
Usuário fala → Whisper transcreve → OpenClaw responde → TTS gera áudio → usuário ouve.

## Como funciona

1. Gateway carrega `index.ts` no startup (via `openclaw.plugin.json`)
2. `index.ts` registra o comando `/ova`
3. Ao executar `/ova`: detecta Python, cria `venv/` se necessário, instala deps, inicia servidor
4. Servidor Python (`core/`) serve frontend + WebSocket pra áudio bidirecional
5. Opcionalmente cria túnel Cloudflare HTTPS pra acesso mobile

## Estrutura do código

```
index.ts                 ─ Plugin OpenClaw (TypeScript). Registra /ova, gerencia processo Python + tunnel
package.json             ─ Metadata npm + peerDependencies (openclaw SDK)
openclaw.plugin.json     ─ Manifesto do plugin (config schema, id, display name)
setup.sh                 ─ Auto-setup Linux/Mac (called by index.ts if no venv)
setup.ps1                ─ Auto-setup Windows (called by index.ts if no venv)

core/                    ─ Servidor Python (FastAPI + WebSocket)
  __init__.py            ─ Package marker
  __main__.py            ─ Entry point: `python -m core` (argparse + uvicorn)
  config.py              ─ Constantes + env vars + load_token()
  history.py             ─ Chat history (MAX_HISTORY = 20 exchanges)
  llm.py                 ─ Cliente OpenClaw (streaming SSE)
  stt.py                 ─ Whisper STT (lazy loading, thread-safe)
  tts.py                 ─ TTS multi-engine (piper → edge) + strip markdown

static/
  index.html             ─ Frontend completo (HTML + CSS + JS inline)
  marked.min.js          ─ Marked v15 (local, sem CDN)

requirements.txt         ─ Dependências Python
pyproject.toml           ─ Config do pacote Python
tests/                   ─ 118 testes (pytest)
docs/SECURITY.md         ─ Modelo de autenticação
```

## Variáveis de ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `OPENCLAW_GATEWAY_URL` | auto-detectado de `~/.openclaw/openclaw.json` | Endpoint do gateway |
| `OPENCLAW_GATEWAY_TOKEN` | auto de `~/.openclaw/openclaw.json` | Override do token |
| `OPENCLAW_MODEL` | `openclaw` | Modelo LLM (gateway resolve pro modelo configurado) |
| `WHISPER_MODEL` | `tiny` | `tiny` (~1-2s) / `small` (~3-5s, mais preciso) |
| `TTS_ENGINE` | `piper` | `piper` (local) / `edge` (online) / `kokoro` (local, melhor) |
| `TTS_VOICE` | `pt-BR-AntonioNeural` | Voz Edge TTS |
| `SERVER_HOST` | `127.0.0.1` | `0.0.0.0` pra acesso remoto (ativa auth) |
| `PORT` | `7860` | Porta do servidor |

## Dependências entre arquivos

```
index.ts (Plugin)
  ├── openclaw.plugin.json  (manifesto — gateway lê no startup)
  ├── package.json          (peerDependencies: openclaw SDK)
  ├── core/__main__.py      (spawn do servidor Python)
  └── .ova_token            (lido pra incluir na URL)

core/__main__.py
  ├── core/config.py
  └── server_ws.py → NÃO EXISTE MAIS. O servidor é core/ inteiro via FastAPI.
      (uvicorn carrega core como app)

core/llm.py   ← core/config.py (GATEWAY_URL, MODEL, load_token)
core/stt.py   ← core/config.py (WHISPER_MODEL_SIZE)
core/tts.py   ← sem deps internas (só libs externas)
```

## Partes frágeis

1. **`ask_openclaw_stream` (llm.py)** — Parser SSE manual. Quebra se formato mudar.
2. **`_find_sentence_end` (llm.py)** — Split de frases pro TTS. Última frase sem pontuação pode atrasar.
3. **`load_token` (config.py)** — Lê `~/.openclaw/openclaw.json` → `gateway.auth.token`.
4. **`generate_tts` (tts.py)** — Edge TTS roda em ThreadPoolExecutor (event loop do FastAPI).
5. **`_strip_markdown` (tts.py)** — Regex chain. Ordem importa.
6. **Audio queue (index.html)** — `playNext()` encadeia via `onended`. Try/catch protege contra `decodeAudioData` failure.
7. **Auth (index.ts + core)** — Token em `.ova_token`. Só ativo quando `SERVER_HOST ≠ localhost`.
8. **Tunnel (index.ts)** — `cloudflared` baixado automaticamente em `bin/`. WebSocket usa `wss:` quando tunnel ativo.

## Convenções

- Python 3.10+ (testado em 3.13)
- TypeScript (index.ts) — usa OpenClaw Plugin SDK (`definePluginEntry`)
- Handlers do plugin retornam `{ text: string }`, NUNCA `string` direto
- Português nos comentários e UI
- Testes: `python -m pytest tests/ -v` (118 testes)
- Imports: stdlib → third-party → locais
- Sem type hints no Python

## Antes de rodar testes

```powershell
# Matar processos Python zumbis (Windows)
Get-Process -Name python* -ErrorAction SilentlyContinue | Stop-Process -Force

# Rodar testes
python -m pytest tests/ -v
```
