# BUGS PENDENTES — Voice Assistant

> Identificados na sessão de teste manual (2026-03-19 01:30 BRT)
> Corrigir com Claude Code na próxima sessão

---

## BUG 1: `_detect_mode()` timeout muito curto [CORRIGIDO PARCIALMENTE]

**Arquivo:** `voice_assistant_app.py` linha ~40
**Problema:** `_detect_mode()` usa thread com timeout pra detectar se RealtimeSTT/PyAudio estão disponíveis. O timeout era 5s, RealtimeSTT demora >10s pra importar no laptop.
**Resultado:** Detectava BROWSER quando deveria ser LOCAL → escuta contínua não funcionava.
**Fix aplicado:** Timeout 5s → 15s.
**Status:** ⚠️ Parcial — funciona mas 15s de startup é lento. Ideal: cache do resultado ou detectar de outra forma.

**Reproduzir:**
```python
# _test_detect.py na raiz do projeto
python _test_detect.py  # mostra tempo de importação do RealtimeSTT
```

---

## BUG 2: `ERR_CONTENT_LENGTH_MISMATCH` no browser [CORRIGIDO PARCIALMENTE]

**Arquivo:** `core/tts.py` função `generate_tts()`
**Problema:** `generate_tts()` deletava o arquivo TTS anterior imediatamente ao gerar um novo. Com o buffer duplo (Fase 5), o Gradio ainda estava servindo o arquivo anterior pro browser quando ele era deletado.
**Resultado:** Console do browser mostrava `ERR_CONTENT_LENGTH_MISMATCH`, áudio cortado.
**Fix aplicado:** Em vez de deletar imediatamente, mantém os 2 arquivos mais recentes antes de limpar.
**Status:** ⚠️ Parcial — funciona mas acumula arquivos temporários. Ideal: usar callback do Gradio pra saber quando o browser terminou de baixar.

---

## BUG 3: Latência alta (~35s voz→resposta→voz) [NÃO CORRIGIDO]

**Medições reais (laptop Dayner, 2026-03-19):**

| Etapa | Tempo | Controlável? |
|-------|-------|-------------|
| Whisper STT (small) | ~3-5s | ✅ `WHISPER_MODEL=tiny` → ~1-2s |
| **LLM TTFT** | **31.4s** | ❌ Depende do modelo (Opus 4 via OpenClaw) |
| TTS Piper (1ª chamada) | 3.4s | 🟡 Cache interno aquece depois |
| TTS Piper (subsequentes) | 1.3s | OK |

**Pipeline total:** ~38-40s (voz do usuário → voz da resposta)
**Bottleneck:** 90% é o LLM (31.4s TTFT). Buffer duplo da Fase 5 ajuda entre frases mas NÃO reduz o tempo até a primeira resposta.

**Opções de melhoria:**
1. Usar modelo mais rápido pro voice assistant (`OPENCLAW_MODEL` ou modelo direto via API)
2. `WHISPER_MODEL=tiny` (reduz STT de 3-5s → 1-2s)
3. Edge TTS em vez de Piper pra 1ª frase (1-2s vs 3.4s na 1ª chamada)
4. Streaming TTS (Gradio não suporta — verificado na Fase 5)

**Reproduzir:**
```python
python _test_latency.py  # mede cada etapa do pipeline
```

---

## BUG 4: Código duplicado 3x no buffer duplo [DEBT]

**Arquivo:** `voice_assistant_app.py`
**Problema:** `respond_text()`, `respond_audio()`, `_process_voice_text()` têm ~30 linhas idênticas de lógica de buffer duplo TTS.
**Impacto:** Se corrigir bug no buffer, precisa editar em 3 lugares.
**Sugestão:** Extrair pra `_stream_with_tts(text, token, history, chat_history)` generator.

---

## BUG 5: `tts_future` não cancelado em exceções [MINOR]

**Arquivo:** `voice_assistant_app.py` — blocos `except Exception:` em respond_text/audio/_process_voice_text
**Problema:** Se o streaming falhar enquanto um `tts_future` está rodando no `_tts_executor`, o future continua em background. O fallback cria novo TTS síncrono → pode ter 2 gerações simultâneas.
**Impacto:** Mínimo (executor tem max_workers=1, enfileira).
**Fix:** Adicionar `if tts_future: tts_future.cancel()` antes do fallback.

---

## BUG 6: CSS duplicado [COSMÉTICO]

**Arquivo:** `voice_assistant_app.py`
**Problema:** `CUSTOM_CSS` aparece no `gr.Blocks(css=CUSTOM_CSS)` E no `launch(css=CUSTOM_CSS)`.
**Impacto:** Zero funcional. Gradio aceita sem conflito.
**Fix:** Remover de um dos dois.

---

## Arquivos de diagnóstico

Na raiz do projeto existem scripts de teste criados durante o diagnóstico:
- `_test_detect.py` — mede tempo de `_detect_mode()`
- `_test_import.py` — testa import do RealtimeSTT
- `_test_latency.py` — mede latência de cada etapa do pipeline

Podem ser movidos pra `scripts/` ou removidos após o debug.
