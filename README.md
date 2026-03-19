# OpenClaw Voice Assistant

Interface de conversação **Speech-to-Speech (S2S)** conectada ao [OpenClaw](https://github.com/openclaw/openclaw). Fale com seu agente de IA e receba respostas em voz — com VAD automático, streaming de texto e áudio. 100% open source.

> Construído por alguém aprendendo a programar — documentando tudo em público. [@preneurIAquem](https://x.com/preneurIAquem)

<!-- TODO: substituir por GIF de demo -->
![Demo placeholder](https://via.placeholder.com/800x400?text=Demo+GIF+aqui)

## O que faz

Você fala → o sistema detecta silêncio (VAD) → transcreve (Whisper) → envia pro OpenClaw (LLM streaming) → converte em voz (TTS) → você ouve a resposta. Sem apertar botão, conversação contínua.

O **OpenClaw** é o cérebro — seu agente com memória, skills e contexto. Este projeto é a interface de voz que conecta a ele.

## Features

- **Speech-to-Speech** — Conversação por voz com detecção automática de fala (VAD)
- **Streaming** — LLM gera texto + TTS gera áudio simultaneamente (buffer duplo)
- **3 cenários de deploy** — Tudo local, tudo VPS, ou app local + OpenClaw remoto
- **3 engines TTS** — Kokoro (qualidade alta, local) → Piper (local, leve) → Edge TTS (online)
- **Whisper local** — STT na CPU, sem API keys, sem custos
- **Escuta contínua** — VAD detecta quando você fala, sem clicar
- **CLI** — Modo terminal pra quem prefere
- **Mobile-friendly** — Layout responsivo, dark mode

## Instalação

```bash
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git
cd openclaw-voice-assistant
pip install -r requirements.txt
```

Para TTS local (Kokoro/Piper) e mic direto no server:

```bash
pip install -r requirements-local.txt
```

**Requisitos:** Python 3.10+, OpenClaw Gateway rodando com `chatCompletions` habilitado.

## 3 Cenários de uso

### Cenário 1: Tudo local (laptop com OpenClaw)

```bash
# Linux/Mac
bash scripts/run_local.sh

# Windows PowerShell
.\scripts\run_local.ps1
```

Voice app + OpenClaw no mesmo computador. Mais simples.

### Cenário 2: Tudo na VPS

```bash
# Na VPS:
bash scripts/run_vps.sh

# No seu PC (SSH tunnel):
ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>

# Abra: http://127.0.0.1:7860
```

Voice app + OpenClaw na VPS. Acessa pelo browser via tunnel.

### Cenário 3: App local → OpenClaw na VPS

```bash
# Primeiro, tunnel pro gateway:
ssh -N -L 18789:127.0.0.1:18789 root@<VPS_IP>

# Depois:
bash scripts/run_local_remote_gateway.sh
```

Voice app roda no seu laptop, mas usa o OpenClaw da VPS como cérebro.

### Modo rápido (sem scripts)

```bash
python voice_assistant_app.py      # Web/Gradio (auto-detecta modo)
python voice_assistant_cli.py      # Terminal
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
│ Microfone │───▶│ VAD+STT  │───▶│   OpenClaw    │───▶│    TTS    │
│ (browser) │    │ (Whisper) │    │  (streaming)  │    │ (buffer   │
└──────────┘    └──────────┘    └──────────────┘    │  duplo)   │
   Você fala      ~1-2s CPU       ~2-4s Sonnet      └───────────┘
                                                       ~0.5-2s
                                                          │
                                                          ▼
                                                     🔊 Autoplay
```

```
core/
  config.py     — Configuração (env vars)
  stt.py        — Whisper STT
  tts.py        — Kokoro + Piper + Edge (fallback chain)
  llm.py        — OpenClaw API (streaming SSE)
  history.py    — Histórico de conversa

voice_assistant_app.py   — Interface web (Gradio)
voice_assistant_cli.py   — Interface terminal
scripts/                 — Scripts de conexão (3 cenários)
```

## Stack

| Camada | Ferramenta | Custo |
|--------|-----------|-------|
| **VAD** | RealtimeSTT / RMS energy | Grátis |
| **STT** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Grátis (CPU) |
| **LLM** | [OpenClaw](https://github.com/openclaw/openclaw) Gateway | Seu plano |
| **TTS** | [Kokoro](https://github.com/hexgrad/kokoro) / [Piper](https://github.com/rhasspy/piper) / [Edge TTS](https://github.com/rany2/edge-tts) | Grátis |
| **UI** | [Gradio 6.x](https://gradio.app/) | Grátis |

## Roadmap

- [x] Protótipo funcional (VAD + STT + LLM + TTS)
- [x] Interface web + CLI
- [x] Escuta contínua (local + browser)
- [x] Buffer duplo TTS
- [x] 3 engines TTS com fallback
- [ ] **Fase 1:** Otimização de latência (modelo rápido, Whisper tiny, split agressivo)
- [ ] **Fase 2:** WebSocket + Web Audio API (S2S real, streaming bidirecional)
- [ ] **Fase 3:** TTS streaming nativo, STT streaming, polish

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para instruções de como rodar localmente, testes e guidelines de PR.

## Licença

MIT
