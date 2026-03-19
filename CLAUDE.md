# CLAUDE.md — Contexto para Claude Code

## O que é este projeto

Assistente de voz conectado ao OpenClaw (gateway de IA). Pipeline: captura voz → Whisper transcreve → OpenClaw API responde (streaming SSE) → TTS fala a resposta.

**Repo:** https://github.com/quenaisaacdayner-art/openclaw-voice-assistant

## Arquitetura atual (3 scripts independentes — SERÁ UNIFICADO)

```
voice_assistant.py      — CLI original (terminal, ENTER pra gravar) — 305 linhas
voice_assistant_web.py  — Gradio local (mic direto via PyAudio/RealtimeSTT) — 661 linhas
voice_assistant_vps.py  — Gradio remoto (mic via browser streaming, roda na VPS) — 558 linhas
```

~400 linhas são copy-paste entre os 3 scripts. Bug corrigido num não propaga pros outros.

## Stack

- **STT:** faster-whisper (modelo "small", ~460MB, CPU)
- **TTS:** Kokoro (local, ~300MB, qualidade 8/10) + Piper (local, 63MB) + Edge TTS (online) — fallback: kokoro → piper → edge
- **LLM:** OpenClaw Gateway API (chatCompletions, streaming SSE)
- **UI:** Gradio 6.x (web + vps)
- **VAD web local:** RealtimeSTT (PyAudio direto no server)
- **VAD vps/remoto:** BrowserContinuousListener (RMS energy manual, threshold 0.01)

## Configs por ambiente

| | CLI | Web (local) | VPS |
|---|---|---|---|
| Gateway | localhost:18789 | localhost:18789 | localhost:19789 |
| Mic | sounddevice | PyAudio (RealtimeSTT) | Browser streaming |
| TTS | Kokoro/Piper + Edge | Kokoro/Piper + Edge | Edge only |
| Escuta contínua | ❌ | RealtimeSTT | BrowserContinuousListener |

## Testes

```bash
python -m pytest tests/ -v
```

129 testes cobrindo comportamento atual. Alguns testes documentam bugs (ver seção bugs).

### Bugs conhecidos documentados nos testes
1. `PortAudioError(-1).__str__()` retorna int → crash no print do record_audio (CLI)
2. `MIN_SPEECH_CHUNKS` conta chunks de silêncio no buffer, não só speech (VPS)
3. `build_api_history` filtra mensagens `[🎤` → voz transcrita não vai pro contexto do LLM
4. `MAX_HISTORY` é variável local no CLI, constante de módulo no web/vps

## Partes frágeis (entender antes de mexer)

1. **`ask_openclaw_stream`** — parser SSE (delta.content, [DONE]). Quebra silenciosamente.
2. **`gr.skip()` na VPS** — race condition Gradio resolvida. Timer sobrescreve outputs sem isso.
3. **`load_token()`** — lê de `~/.openclaw/openclaw.json`. Estrutura: `gateway.auth.token`.
4. **`build_api_history`** — filtra `[🎤` pra não mandar prefixo pro LLM. Mas isso descarta a mensagem inteira (bug #3).
5. **`generate_tts` no web** — roda edge-tts em ThreadPoolExecutor porque Gradio 6.x já tem event loop. `asyncio.run()` direto crasharia.
6. **`ContinuousListener` (web)** — usa RealtimeSTT com Silero VAD nativo. Roda em thread daemon separada.
7. **`BrowserContinuousListener` (vps)** — VAD manual por RMS. `audio_input.stream()` manda chunks do browser → `feed_chunk()` acumula → detecta silêncio → transcreve.

## Convenções

- Python 3.10+ (projeto roda em 3.13 localmente)
- Português nos comentários e UI
- Testes com pytest + unittest.mock
- Sem type hints no código atual (manter assim)
- Imports: stdlib primeiro, depois third-party, depois locais
