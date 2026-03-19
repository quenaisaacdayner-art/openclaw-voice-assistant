# CLAUDE.md — Contexto para Claude Code

## O que é este projeto

Assistente de voz conectado ao OpenClaw (gateway de IA). Pipeline: captura voz → Whisper transcreve → OpenClaw API responde (streaming SSE) → TTS fala a resposta.

**Repo:** https://github.com/quenaisaacdayner-art/openclaw-voice-assistant

## Arquitetura atual (3 scripts independentes)

```
voice_assistant.py      — CLI original (terminal, ENTER pra gravar)
voice_assistant_web.py  — Gradio local (mic direto via PyAudio/RealtimeSTT)
voice_assistant_vps.py  — Gradio remoto (mic via browser streaming, roda na VPS)
```

~70% do código é duplicado entre os 3 scripts (copy-paste). Bug corrigido num não propaga pros outros.

## Stack

- **STT:** faster-whisper (modelo "small", ~460MB, CPU)
- **TTS:** Piper local (pt_BR-faber-medium, 63MB — web/cli) + Edge TTS online (fallback/vps)
- **LLM:** OpenClaw Gateway API (chatCompletions, streaming SSE)
- **UI:** Gradio 6.x (web + vps)
- **VAD web:** RealtimeSTT (PyAudio direto)
- **VAD vps:** BrowserContinuousListener (RMS energy manual, threshold 0.01)

## Configs por ambiente

| | CLI | Web (local) | VPS |
|---|---|---|---|
| Gateway | localhost:18789 | localhost:18789 | localhost:19789 |
| Mic | sounddevice | PyAudio (RealtimeSTT) | Browser streaming |
| TTS | Piper + Edge | Piper + Edge | Edge only |
| Escuta contínua | ❌ | RealtimeSTT | BrowserContinuousListener |

## Testes

```bash
python -m pytest tests/ -v
```

129 testes cobrindo comportamento atual. Testes documentam bugs sem corrigir.

### Bugs conhecidos documentados nos testes
1. `PortAudioError(-1).__str__()` retorna int → crash no print do record_audio
2. `MIN_SPEECH_CHUNKS` conta chunks de silêncio no buffer (não só speech)
3. `build_api_history` filtra mensagens `[🎤` → voz transcrita não vai pro contexto do LLM
4. `MAX_HISTORY` é variável local no CLI, constante de módulo no web/vps

## Arquivos importantes

- `voice_assistant.py` (13KB) — protótipo v1, CLI
- `voice_assistant_web.py` (28KB) — versão completa local
- `voice_assistant_vps.py` (25KB) — versão VPS (browser mic)
- `tests/` — 129 testes (conftest + 5 arquivos)
- `models/pt_BR-faber-medium.onnx` (63MB) — modelo Piper commitado no git (problema)
- `UPGRADE_PLAN.md` — plano de refatoração existente

## Partes frágeis (não mexer sem entender)

1. **`ask_openclaw_stream`** — parser SSE (delta.content, [DONE]). Quebra silenciosamente.
2. **`gr.skip()` na VPS** — race condition Gradio resolvida. Timer sobrescreve outputs sem isso.
3. **`load_token()`** — lê de `~/.openclaw/openclaw.json`. Estrutura específica.
4. **`build_api_history`** — filtra `[🎤` pra não mandar prefixo pro LLM.

## Convenções

- Python 3.13+
- Português nos comentários e UI
- Testes com pytest + unittest.mock
- Sem type hints no código atual
