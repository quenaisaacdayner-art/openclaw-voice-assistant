# BUGS PENDENTES — Voice Assistant

> Última revisão: 2026-03-23 (pós S1-S8)

---

## BUG 1: `_find_sentence_end()` não detecta `\n` [ABERTO]

**Arquivo:** `core/llm.py`
**Problema:** A função que detecta fim de frase pra split TTS não reconhece `\n` como ponto de corte. Quando o LLM responde com listas ou bullet points, a última frase antes de `\n` não vai pro TTS até acumular mais texto.
**Impacto:** Atraso perceptível no TTS quando resposta tem listas.
**Fix:** Adicionar `\n` como sentença terminadora em `_find_sentence_end()`.

---

## BUG 2: `build_api_history` filtra prefixo `[🎤` [ABERTO]

**Arquivo:** `core/history.py`
**Problema:** O filtro de histórico remove mensagens que começam com `[🎤` — provavelmente resíduo de uma versão anterior. Isso pode cortar contexto legítimo de transcrições de voz.
**Impacto:** Contexto potencialmente perdido pro LLM.
**Fix:** Remover ou ajustar o filtro.

---

## BUG 3: Latência Opus 4 ~35s TTFT [NÃO É BUG]

**Contexto:** TTFT do Opus 4 via OpenClaw Gateway é ~31s. É característica do modelo, não do voice assistant.
**Mitigação:** Usar modelo mais rápido (`OPENCLAW_MODEL=anthropic/claude-sonnet-4-6`, default). Opus 4 funciona mas é lento pra voz.

---

## Bugs corrigidos (referência)

| Bug | Corrigido em | Fix |
|-----|-------------|-----|
| `playbackQueue` trava se `decodeAudioData` falha | S5 | try/catch no playNext() |
| `_detect_mode()` timeout 15s | S5 | Irrelevante — app Gradio movido pra arquivo/ |
| `ERR_CONTENT_LENGTH_MISMATCH` | S5 | Irrelevante — Gradio removido, WebSocket S2S não tem esse problema |
| Código duplicado 3x buffer duplo | S5 | Irrelevante — voice_assistant_app.py movido pra arquivo/ |
| `tts_future` não cancelado | S5 | Irrelevante — Gradio removido |
| CSS duplicado | S5 | Irrelevante — Gradio removido |
