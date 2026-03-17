# 🎤 OpenClaw Voice Assistant

Talk to your [OpenClaw](https://github.com/openclaw/openclaw) AI agent using your voice. 100% free. Runs locally.

> Built by someone learning to code — documenting everything in public. [@preneurIAquem](https://x.com/preneurIAquem)

## What it does

```
You speak → Whisper transcribes → OpenClaw thinks → Edge TTS speaks back
```

Full voice conversation with your AI agent. No API keys needed for speech — Whisper runs on your CPU, Edge TTS is free.

## Demo

```
=======================================================
  🎤 OpenClaw Voice Assistant
  Talk to your AI agent using your voice
=======================================================

✅ Token carregado
✅ Microfone: Grupo de microfones (Intel® Smart Sound Technology)
⏳ Carregando Whisper (small)...
✅ Whisper pronto

🎤 ENTER para falar (ou digite comando):
  🔴 Gravando... (ENTER para parar)
  📝 Transcrevendo...
  Tu: quanto é dois mais dois?
  🧠 Pensando...
  🤖 Quatro.
  🔊 Falando...
```

## Stack

| Layer | Tool | Cost | Runs on |
|-------|------|------|---------|
| **Speech-to-Text** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Free | CPU (local) |
| **LLM** | [OpenClaw](https://github.com/openclaw/openclaw) Gateway API | Your existing plan | Local/Remote |
| **Text-to-Speech** | [edge-tts](https://github.com/rany2/edge-tts) (Microsoft) | Free | Cloud (no key) |

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

# Run
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

Change with: `set TTS_VOICE=pt-BR-FranciscaNeural` (Windows) or `export TTS_VOICE=...` (Linux/Mac)

## Commands

While running:

| Input | Action |
|-------|--------|
| `ENTER` | Start recording |
| `ENTER` again | Stop recording |
| Type any text | Send as text (skip recording) |
| `limpar` / `clear` | Reset conversation history |
| `sair` / `exit` | Quit |

## Features

- 🎤 Auto-detects best microphone (prefers built-in over virtual cameras)
- 🔇 VAD filter — ignores silence, prevents Whisper hallucinations ("e e e e e")
- 📊 Volume check — warns if mic is too quiet
- 💬 Conversation history — remembers last 10 exchanges
- 🔊 Cross-platform audio playback (Windows/macOS/Linux)
- ⌨️ Text fallback — type instead of speaking when you want

## How it works

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│  Microphone  │────▶│ faster-whisper│────▶│   OpenClaw    │────▶│  edge-tts   │
│  (record)    │     │  (transcribe) │     │  (think)      │     │  (speak)    │
└─────────────┘     └──────────────┘     └──────────────┘     └─────────────┘
     You speak        STT (local)         Your AI agent        TTS (free)
                      ~1-3 sec             ~2-5 sec            ~1-2 sec
```

Total latency: **4-10 seconds** depending on response length and Whisper model.

## Limitations

- Not real-time (press-to-talk, not continuous listening)
- Whisper `small` struggles with strong accents — use `medium` if needed
- Edge TTS requires internet connection
- No streaming — waits for full response before speaking

## Roadmap

- [ ] Continuous listening with VAD (no button press)
- [ ] Gradio web interface with chat history
- [ ] Streaming TTS (speak as response arrives)
- [ ] Kokoro/Piper TTS for fully offline operation

## Built with

This project was built in a single session using [OpenClaw](https://github.com/openclaw/openclaw) as the coding assistant. The AI helped write the code, debug microphone issues, and create this README.

Part of my build-in-public journey: learning AI + coding from scratch and documenting everything — mistakes included.

## License

MIT
