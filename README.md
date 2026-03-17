# 🎤 OpenClaw Voice Assistant

Talk to your [OpenClaw](https://github.com/openclaw/openclaw) AI agent using your voice. 100% free. Runs locally.

> Built by someone learning to code — documenting everything in public. [@preneurIAquem](https://x.com/preneurIAquem)

## What it does

```
You speak → Whisper transcribes → OpenClaw thinks → Edge TTS speaks back
```

Full voice conversation with your AI agent through a web interface. No API keys needed for speech — Whisper runs on your CPU, Edge TTS is free.

## Two modes

| Mode | Command | Interface |
|------|---------|-----------|
| **Web** (recommended) | `python voice_assistant_web.py` | Browser with chat UI, mic button, auto-play voice |
| **Terminal** | `python voice_assistant.py` | Press Enter to record, type to send text |

## Stack

| Layer | Tool | Cost | Runs on |
|-------|------|------|---------|
| **Speech-to-Text** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Free | CPU (local) |
| **LLM** | [OpenClaw](https://github.com/openclaw/openclaw) Gateway API | Your existing plan | Local/Remote |
| **Text-to-Speech** | [edge-tts](https://github.com/rany2/edge-tts) (Microsoft) | Free | Cloud (no key) |
| **UI** | [Gradio](https://gradio.app/) | Free | Local browser |

## Requirements

- Python 3.10+
- [OpenClaw](https://github.com/openclaw/openclaw) running with gateway HTTP API enabled
- A microphone
- Windows / macOS / Linux

## Setup

```bash
# Clone
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git
cd openclaw-voice-assistant

# Install dependencies
pip install -r requirements.txt

# Run (web interface)
python voice_assistant_web.py

# Or run (terminal mode)
python voice_assistant.py
```

### OpenClaw Gateway

The assistant connects to OpenClaw's HTTP API. Make sure your gateway has `chatCompletions` enabled:

```json
{
  "gateway": {
    "http": {
      "endpoints": {
        "chatCompletions": { "enabled": true }
      }
    }
  }
}
```

The token is auto-loaded from `~/.openclaw/openclaw.json`.

## Configuration

All settings are environment variables (optional — defaults work out of the box):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCLAW_GATEWAY_URL` | `http://127.0.0.1:18789/v1/chat/completions` | Gateway endpoint |
| `OPENCLAW_MODEL` | `openclaw:main` | Agent to talk to |
| `TTS_VOICE` | `pt-BR-AntonioNeural` | Edge TTS voice ([list](https://gist.github.com/BettyJJ/17cbaa1de96235a7f5773b8c50bf8f34)) |
| `WHISPER_MODEL` | `small` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `OPENCLAW_GATEWAY_TOKEN` | (from config) | Override gateway token |

### Whisper models

| Model | Size | Speed | Portuguese quality |
|-------|------|-------|--------------------|
| `tiny` | 75MB | ⚡ Fast | Basic — misses a lot |
| `base` | 150MB | ⚡ Fast | Okay for clear speech |
| `small` | 461MB | 🔵 Medium | Good for most use cases |
| `medium` | 1.5GB | 🟡 Slower | Great — handles accents well |
| `large-v3` | 3GB | 🔴 Slow | Best quality |

### TTS voices (Portuguese)

- `pt-BR-AntonioNeural` — Male, neutral (default)
- `pt-BR-FranciscaNeural` — Female, neutral
- `pt-BR-ThalitaNeural` — Female, warm

## Features

- 🌐 **Web interface** — Chat UI in your browser with mic recording and auto-play voice
- 🎤 Auto-detects best microphone (prefers built-in over virtual cameras)
- 🔇 VAD filter — ignores silence, prevents Whisper hallucinations
- 💬 Conversation history — remembers last 10 exchanges
- 🔊 Auto-play voice responses in browser
- ⌨️ Type or speak — both work seamlessly

## How it works

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│  Microphone  │────▶│ faster-whisper│────▶│   OpenClaw    │────▶│  edge-tts   │
│  (browser)   │     │  (transcribe) │     │  (think)      │     │  (speak)    │
└─────────────┘     └──────────────┘     └──────────────┘     └─────────────┘
     You speak        STT (local)         Your AI agent        TTS (free)
                      ~1-3 sec             ~2-5 sec            ~1-2 sec
```

Total latency: **4-10 seconds** depending on response length and Whisper model.

## Roadmap

- [ ] Continuous listening with VAD (no button press needed)
- [ ] Kokoro TTS — near-human voice quality, runs local
- [ ] Streaming responses — speak as text arrives
- [x] ~~Gradio web interface with chat history~~

## Built with

This project was built in a single session (~2 hours) using [OpenClaw](https://github.com/openclaw/openclaw) as the coding assistant. The AI helped write the code, debug microphone issues, and create this README.

Part of my build-in-public journey: learning AI + coding from scratch and documenting everything — mistakes included.

## License

MIT
