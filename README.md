# OpenClaw Voice Assistant

Interface de conversação **Speech-to-Speech (S2S)** conectada ao [OpenClaw](https://github.com/openclaw/openclaw). Fale com seu agente de IA e receba respostas em voz — com VAD automático, streaming de texto e áudio. 100% open source.

> Construído por alguém aprendendo a programar — documentando tudo em público. [@preneurIAquem](https://x.com/preneurIAquem)

<!-- GIF de demo será adicionado em breve -->

## O que faz

Você fala → o sistema detecta silêncio (VAD) → transcreve (Whisper) → envia pro OpenClaw (LLM streaming) → converte em voz (TTS) → você ouve a resposta. Sem apertar botão, conversação contínua.

O **OpenClaw** é o cérebro — seu agente com memória, skills e contexto. Este projeto é a interface de voz que conecta a ele.

## Features

- **Speech-to-Speech** — Conversação por voz com detecção automática de fala (VAD)
- **Barge-in** — Interrompa a resposta falando por cima — o assistente para e escuta
- **WebSocket S2S** — Streaming bidirecional real, sem polling HTTP
- **Streaming** — LLM gera texto + TTS gera áudio simultaneamente (por frase)
- **3 cenários de deploy** — Tudo local, tudo VPS, ou app local + OpenClaw remoto
- **3 engines TTS** — Kokoro (qualidade alta, local) → Piper (local, leve) → Edge TTS (online)
- **Whisper local** — STT na CPU, sem API keys, sem custos
- **Escuta contínua** — VAD detecta quando você fala, sem clicar
- **CLI** — Modo terminal pra quem prefere
- **Mobile-friendly** — Layout responsivo, dark mode

## Início rápido

```bash
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git
cd openclaw-voice-assistant
bash run.sh
```

Pronto. O script detecta se é a primeira vez, instala tudo automaticamente, sobe o server e abre o browser. Um comando.

**Windows (PowerShell):**

```powershell
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git
cd openclaw-voice-assistant
.\run.ps1
```

**Via pip (alternativa):**

```bash
pip install openclaw-voice-assistant
ova
```

**Requisitos:** [OpenClaw](https://github.com/openclaw/openclaw) Gateway rodando. Python 3.10+ (instalado automaticamente pelo script em Ubuntu/Debian/Fedora/macOS).

## 3 Cenários de uso

A diferença entre cenários é **pra onde apontar**, não o código. O mesmo comando funciona pra todos.

### Cenário 1: Tudo local (laptop com OpenClaw)

```bash
bash run.sh          # Linux/Mac
.\run.ps1            # Windows
ova                  # via pip
```

Voice app + OpenClaw no mesmo computador. Mais simples — defaults funcionam.

### Cenário 2: Tudo na VPS

```bash
# Na VPS:
bash run.sh --host 0.0.0.0

# No seu PC (SSH tunnel pra acessar pelo browser):
ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>

# Abra: http://127.0.0.1:7860
```

### Cenário 3: App local → OpenClaw na VPS

```bash
# Primeiro, tunnel pro gateway da VPS:
ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>

# Depois, rodar normalmente (o tunnel faz o gateway parecer local):
bash run.sh
```

### Opções avançadas

```bash
bash run.sh --host 0.0.0.0 --port 8080 --model anthropic/claude-sonnet-4-6 --whisper small
ova --host 0.0.0.0 --gateway-url http://minha-vps:18789/v1/chat/completions --no-browser
ova --help        # ver todas as opções
```

### CLI (terminal, sem browser)

```bash
python voice_assistant_cli.py
```

## Configuração

Todas opcionais — defaults funcionam out of the box.

| Variável | Default | Descrição |
|----------|---------|-----------|
| `OPENCLAW_GATEWAY_URL` | `http://127.0.0.1:18789/v1/chat/completions` | Endpoint do gateway |
| `OPENCLAW_MODEL` | `anthropic/claude-sonnet-4-6` | Modelo LLM |
| `WHISPER_MODEL` | `tiny` | `tiny` (~1-2s, rápido) / `small` (~3-5s, preciso) |
| `TTS_ENGINE` | `edge` | `edge` (online) / `piper` (local) / `kokoro` (local, melhor) |
| `TTS_VOICE` | `pt-BR-AntonioNeural` | Voz do Edge TTS |
| `SERVER_HOST` | `127.0.0.1` | `0.0.0.0` pra acesso remoto |
| `PORT` | `7860` | Porta do servidor |

Token carregado automaticamente de `~/.openclaw/openclaw.json`.

## Arquitetura

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌───────────┐
│ Microfone │◄──▶│ WebSocket│◄──▶│   OpenClaw    │───▶│    TTS    │
│ (browser) │    │ (FastAPI) │    │  (streaming)  │    │ (por      │
└──────────┘    └──────────┘    └──────────────┘    │  frase)   │
   Bidirecional    ~50ms            ~2-4s Sonnet      └───────────┘
                                                       ~0.5-1s
```

~3-6s do fim da fala até início da resposta em áudio (com Sonnet 4.6 + Whisper tiny).

```
run.sh / run.ps1         ─── "Faz tudo" — setup + server + browser (1 comando)
server_ws.py             ─── Servidor WebSocket S2S (principal)
static/index.html        ─── Frontend Web Audio API + orbe visual
voice_assistant_cli.py   ─── CLI terminal
core/                    ─── Módulos compartilhados (STT, TTS, LLM, config, entry point `ova`)
setup.sh / setup.ps1     ─── Setup isolado (só instala, não roda)
scripts/                 ─── Scripts avançados (3 cenários separados)
tests/                   ─── 118 testes automatizados
pyproject.toml           ─── Configuração do pacote (pip install)
```

## Stack

| Camada | Ferramenta | Custo |
|--------|-----------|-------|
| **VAD** | RealtimeSTT / RMS energy | Grátis |
| **STT** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Grátis (CPU) |
| **LLM** | [OpenClaw](https://github.com/openclaw/openclaw) Gateway | Seu plano |
| **TTS** | [Kokoro](https://github.com/hexgrad/kokoro) / [Piper](https://github.com/rhasspy/piper) / [Edge TTS](https://github.com/rany2/edge-tts) | Grátis |
| **UI** | HTML + CSS + JS (WebSocket nativo) | Grátis |

## Roadmap

- [x] Protótipo funcional (VAD + STT + LLM + TTS)
- [x] Interface web + CLI
- [x] Escuta contínua (local + browser)
- [x] Buffer duplo TTS
- [x] 3 engines TTS com fallback
- [x] **Fase 1-3:** Latência, WebSocket S2S, Barge-in
- [x] **S1:** Interface & Interação — Disconnect, Interrupt, Input texto, Timer, Esfera pulsante, Markdown, Config panel
- [x] **S2:** Pipeline de Áudio — Whisper small, Seletor de vozes, Velocidade TTS
- [x] **S3:** Latência — Keep-alive LLM, Split agressivo, VAD otimizado, Métricas TTFA
- [x] **S4:** Transporte — Backoff exponencial, Keep-alive ping/pong, Session persistence
- [x] **S5:** Robustez — Markdown strip TTS, Timeout LLM 120s, Race protection, Cleanup disconnect, Aviso sessão longa
- [x] **S6:** Deploy — Setup Windows, CI GitHub Actions, Docs atualizados
- [x] **S7:** Segurança — Auth por token, XSS fix, Rate limit, Buffer limit, Input validation, Erros genéricos, marked.js local
- [x] **S8:** Conversação — Timestamps nas mensagens, Export conversa (.json)
- [x] **S9:** Simplificação — `run.sh`/`run.ps1` (1 comando), `pyproject.toml`, comando `ova` via pip

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para instruções de como rodar localmente, testes e guidelines de PR.

## Licença

MIT
