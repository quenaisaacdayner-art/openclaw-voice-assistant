# OpenClaw Voice Assistant (OVA)

Plugin [OpenClaw](https://github.com/openclaw/openclaw) que adiciona conversação por voz ao seu agente. Fale → Whisper transcreve → OpenClaw responde → TTS gera áudio → você ouve. Sem apertar botão, conversação contínua.

> Construído por alguém aprendendo a programar — documentando tudo em público. [@preneurIAquem](https://x.com/preneurIAquem)

## O que faz

- **Speech-to-Speech** — Conversação por voz com detecção automática de fala (VAD)
- **Barge-in** — Interrompa a resposta falando por cima
- **Streaming real** — LLM gera texto + TTS gera áudio simultaneamente (por frase)
- **Tunnel HTTPS** — Acesso mobile via Cloudflare (automático)
- **Multi-TTS** — Piper (local) / Edge TTS (online) / Kokoro (local, alta qualidade)
- **Whisper local** — STT na CPU, sem API keys

## Instalação

### Como plugin OpenClaw (recomendado)

```bash
# Clone na pasta de extensões do OpenClaw
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git ~/.openclaw/extensions/ova
cd ~/.openclaw/extensions/ova
npm install
```

Reinicie o OpenClaw. O plugin carrega automaticamente.

**Requisitos:** Python 3.10+ instalado na máquina.

### Uso

Em qualquer canal (Telegram, webchat, Discord):

```
/ova          # inicia — recebe link pro browser
/ova stop     # para o servidor
/ova status   # verifica se está rodando
```

Na primeira execução, o plugin cria o `venv/` e instala as dependências Python automaticamente.

## Configuração

Todas opcionais — defaults funcionam out of the box.

Adicione ao `openclaw.json` em `plugins.entries.ova.config`:

```json
{
  "plugins": {
    "entries": {
      "ova": {
        "enabled": true,
        "config": {
          "host": "0.0.0.0",
          "port": 7860,
          "whisperModel": "small",
          "ttsEngine": "piper",
          "tunnel": true
        }
      }
    }
  }
}
```

| Opção | Default | Descrição |
|-------|---------|-----------|
| `host` | `127.0.0.1` | `0.0.0.0` pra acesso remoto |
| `port` | `7860` | Porta do servidor |
| `whisperModel` | `tiny` | `tiny` (rápido) / `small` (preciso) |
| `ttsEngine` | `piper` | `piper` / `edge` / `kokoro` |
| `ttsVoice` | `pt-BR-AntonioNeural` | Voz Edge TTS |
| `python` | auto-detectado | Caminho pro Python |
| `tunnel` | `true` (se host ≠ localhost) | Túnel Cloudflare HTTPS |

Variáveis de ambiente (`OPENCLAW_MODEL`, `WHISPER_MODEL`, `TTS_ENGINE`, etc.) também funcionam como override.

## Arquitetura

```
┌──────────┐    WebSocket    ┌──────────┐    SSE streaming    ┌──────────┐
│ Browser  │◄──────────────▶│  Python   │◄──────────────────▶│ OpenClaw │
│ (mic+spk)│                 │ (FastAPI) │                    │ Gateway  │
└──────────┘                 └──────────┘                    └──────────┘
                               ├─ Whisper (STT)
                               ├─ Piper/Edge (TTS)
                               └─ static/index.html
```

Latência típica: ~3-6s do fim da fala até início da resposta em áudio.

## Estrutura do código

```
index.ts                 ─ Plugin OpenClaw (registra /ova, gerencia servidor + tunnel)
package.json             ─ Metadata + peerDependencies
openclaw.plugin.json     ─ Manifesto do plugin

core/                    ─ Servidor Python
  __main__.py            ─ Entry point (python -m core)
  config.py              ─ Constantes + env vars
  llm.py                 ─ Cliente OpenClaw (streaming SSE)
  stt.py                 ─ Whisper STT
  tts.py                 ─ TTS multi-engine
  history.py             ─ Chat history

static/index.html        ─ Frontend (HTML + CSS + JS)
requirements.txt         ─ Dependências Python
tests/                   ─ 118 testes (pytest)
```

## Stack

| Camada | Ferramenta | Custo |
|--------|-----------|-------|
| **STT** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Grátis (CPU) |
| **LLM** | [OpenClaw](https://github.com/openclaw/openclaw) | Seu plano |
| **TTS** | [Piper](https://github.com/rhasspy/piper) / [Edge TTS](https://github.com/rany2/edge-tts) / [Kokoro](https://github.com/hexgrad/kokoro) | Grátis |
| **Tunnel** | [Cloudflare](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | Grátis |

## Testes

```bash
python -m pytest tests/ -v    # 118 testes
```

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

MIT
