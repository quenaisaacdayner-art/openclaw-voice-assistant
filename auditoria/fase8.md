# Registro — Fase 8: Hotfix de Infra — Pre-warm + Logging de Latência

> Executada: 20/03/2026
> Objetivo: Reduzir cold start da 1ª resposta + adicionar métricas de latência por fase

## Resultado dos Testes

- **230 passed, 14 skipped, 1 failed (pre-existente)**
- Falha pre-existente: `test_default_tts_engine` — env `TTS_ENGINE=edge` vs assert `"piper"` (não relacionado)
- Sem regressão

## Arquivos Modificados

| Arquivo | O que mudou |
|---------|-------------|
| `core/stt.py` | Adicionada função `init_stt()` — pre-warm do modelo Whisper no startup com timing |
| `core/tts.py` | Adicionada função `warmup_tts()` — geração dummy pra abrir conexões (Edge/Kokoro/Piper) |
| `server_ws.py` | Bloco de warmup (STT + TTS + gateway ping) no startup + logging de latência em `process_speech()` |

## Arquivos Criados

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `auditoria/fase8.md` | ~70 | Este registro |

## O que foi feito

### Tarefa 1: Pre-warm no startup (`server_ws.py`)

3 componentes aquecidos antes de aceitar conexões:

1. **Whisper (STT):** `init_stt()` em `core/stt.py` — carrega modelo com `_get_whisper()` e printa `[WARMUP] Whisper ({model}) carregado em {t}s`
2. **TTS:** `warmup_tts()` em `core/tts.py` — gera TTS dummy ("ok") pra abrir conexão WebSocket (Edge) ou carregar engine (Kokoro/Piper). Printa `[WARMUP] TTS ({engine}) pronto em {t}s`
3. **Gateway:** GET na URL base do gateway com token de auth. Se OK: `[WARMUP] Gateway OK em {t}s`. Se falhar: `[WARMUP] ⚠️ Gateway não respondeu` (não bloqueia startup)

Print final: `[WARMUP] Tudo pronto em {t_total}s`

### Tarefa 2: Logging de latência (`server_ws.py` → `process_speech()`)

Timestamps em cada fase do pipeline:

```
[REQ] Nova mensagem recebida
[STT] Transcrição: "{texto}" ({t}s)
[LLM] TTFT: {t}s
[LLM] Resposta completa: {N} chars em {t}s
[TTS] 1ª frase: "{frase}" ({t}s)
[TTS] Total: {N} frases
[TOTAL] Fala→Resposta: {t}s
```

## Restrições respeitadas

- Nenhuma mudança em: lógica de conversação, barge-in, streaming, index.html, config.py, llm.py
- Nenhuma dependência nova (apenas `requests` já existente + `time` stdlib)
- Apenas prints — sem logging framework
- Compatível com os 3 cenários (local, VPS, local→VPS)

## Diff total

```
 core/stt.py        |  8 +++++
 core/tts.py        | 22 +++++++++++
 server_ws.py       | 60 +++++++++++++++++++++++++++---
 auditoria/fase8.md | ~70 ++++++++++++
 4 files changed, ~160 insertions(+), ~10 deletions(-)
```
