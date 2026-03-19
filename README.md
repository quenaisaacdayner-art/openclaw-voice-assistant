# OpenClaw Voice Assistant

Assistente de voz open source conectado ao [OpenClaw](https://github.com/openclaw/openclaw). Fale com seu agente de IA usando a voz — Whisper transcreve, OpenClaw pensa, TTS fala a resposta. 100% grátis, roda localmente.

> Construído por alguém aprendendo a programar — documentando tudo em público. [@preneurIAquem](https://x.com/preneurIAquem)

<!-- TODO: substituir por GIF de demo -->
![Demo placeholder](https://via.placeholder.com/800x400?text=Demo+GIF+aqui)

## Features

- **Interface web** — Chat UI no browser com gravação de mic e autoplay de voz
- **CLI** — Modo terminal para uso sem browser
- **Auto-detecção** — Detecta automaticamente se roda local (PyAudio) ou remoto (browser streaming)
- **3 engines de TTS** — Kokoro (qualidade 8/10, local) → Piper (local, leve) → Edge TTS (online, fallback)
- **Buffer duplo de TTS** — Gera frase N+1 enquanto frase N toca, sem gaps
- **Whisper local** — STT roda na CPU, sem API keys
- **Escuta contínua** — VAD detecta quando você fala, sem apertar botão
- **Indicadores visuais** — Status em tempo real (gravando/pensando/falando)
- **Histórico** — Lembra últimas 10 trocas de conversa
- **Configurável via UI** — Muda gateway, mic, TTS e modelo Whisper sem reiniciar
- **Mobile-friendly** — Layout responsivo, funciona no celular
- **Theme escuro** — Padrão

## Instalação rápida

```bash
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git
cd openclaw-voice-assistant
pip install -r requirements.txt
```

Para TTS local de alta qualidade (Kokoro/Piper) e mic direto no server:

```bash
pip install -r requirements-local.txt
```

## Modos de uso

### Web/Gradio (recomendado)

```bash
python voice_assistant_app.py
```

Abre interface no browser. Auto-detecta:
- **Modo LOCAL** — se PyAudio está disponível, usa mic direto via RealtimeSTT
- **Modo BROWSER** — se não tem PyAudio, usa streaming de áudio do browser com VAD

### CLI (terminal)

```bash
python voice_assistant_cli.py
```

Modo terminal: ENTER para gravar, digite texto para enviar sem voz.

### VPS / Remoto

```bash
# Na VPS, rodar o app normalmente:
python voice_assistant_app.py

# No seu PC, criar túnel SSH:
bash scripts/connect.sh
```

O app detecta automaticamente modo BROWSER quando PyAudio não está disponível.

## Configuração

Todas as variáveis são opcionais — os defaults funcionam out of the box.

| Variável | Default | Descrição |
|----------|---------|-----------|
| `OPENCLAW_GATEWAY_URL` | `http://127.0.0.1:18789/v1/chat/completions` | Endpoint do gateway |
| `OPENCLAW_GATEWAY_TOKEN` | (de `~/.openclaw/openclaw.json`) | Override do token do gateway |
| `OPENCLAW_MODEL` | `openclaw:main` | Agente/modelo a usar |
| `TTS_VOICE` | `pt-BR-AntonioNeural` | Voz do Edge TTS |
| `TTS_ENGINE` | `piper` | Engine de TTS: `kokoro`, `piper` ou `edge` |
| `WHISPER_MODEL` | `small` | Modelo Whisper: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `SERVER_HOST` | `0.0.0.0` | Host do servidor Gradio |
| `PORT` | `7860` | Porta do servidor Gradio |

O token é carregado automaticamente de `~/.openclaw/openclaw.json`. Certifique-se de que o gateway OpenClaw tem `chatCompletions` habilitado.

## Arquitetura

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐     ┌─────────────┐
│  Microfone   │────▶│ faster-whisper │────▶│   OpenClaw    │────▶│  TTS Engine │
│ (browser/hw) │     │   (STT local)  │     │  Gateway API  │     │ Kokoro/Piper│
└──────────────┘     └───────────────┘     │  (streaming)  │     │  /Edge TTS  │
     Você fala         ~1-3s CPU           └──────────────┘     └─────────────┘
                                              ~2-5s LLM            ~0.5-2s
                                                                      │
                                                                      ▼
                                                                 🔊 Autoplay
```

```
voice_assistant_cli.py   ─── CLI (terminal, ENTER pra gravar)
voice_assistant_app.py   ─── Gradio (auto-detecta local vs browser)
core/
  config.py              ─── Constantes, load_token(), env vars
  stt.py                 ─── faster-whisper, transcribe_audio()
  tts.py                 ─── Kokoro + Piper + Edge TTS com fallback
  llm.py                 ─── ask_openclaw(), streaming SSE
  history.py             ─── build_api_history(), MAX_HISTORY
```

## Stack técnico

| Camada | Ferramenta | Custo | Roda em |
|--------|-----------|-------|---------|
| **STT** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Grátis | CPU local |
| **LLM** | [OpenClaw](https://github.com/openclaw/openclaw) Gateway API | Seu plano | Local/Remoto |
| **TTS** | [Kokoro](https://github.com/hexgrad/kokoro) / [Piper](https://github.com/rhasspy/piper) / [Edge TTS](https://github.com/rany2/edge-tts) | Grátis | Local / Cloud |
| **UI** | [Gradio 6.x](https://gradio.app/) | Grátis | Browser |
| **VAD** | RealtimeSTT (local) / RMS energy (browser) | Grátis | Local |

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para instruções de como rodar localmente, rodar testes e guidelines de PR.

## Licença

MIT
