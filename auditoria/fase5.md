# Auditoria — Fase 5: Latência (Buffer Duplo TTS)

> Executada: 2026-03-19 ~00:37 BRT
> Auditada por: OpenClaw Principal (Opus 4)
> Commit: 595f795

## Resultado dos Testes

- **Real: 219 passed, 14 skipped, 0 failed**
- Claude Code reportou: **215 passed, 18 skipped** — errado (5ª vez, mesmo delta -4/+4)
- Claude Code hash: **03403a0** — errado (real: 595f795)

## Verificação por Task

### ✅ Task 1: Buffer duplo de TTS
- **Antes:** gerava TTS só da 1ª frase durante stream, resto no final
- **Depois:** gera TTS frase-a-frase via `_tts_executor.submit()` em background
- `_tts_executor` (criado na Fase 4 como dead code) agora é usado em 3 handlers: `respond_text`, `respond_audio`, `_process_voice_text`
- **Lógica verificada:**
  1. `_find_sentence_end(remaining)` detecta fim de frase no texto que ainda não foi processado
  2. `_tts_executor.submit(generate_tts, sentence)` → submete em background
  3. Próximo yield checa `tts_future.done()` → se pronto, emite áudio
  4. Pós-loop: `tts_future.result(timeout=30)` → espera pendente
  5. Trecho final (após último TTS) → `generate_tts(remaining)` síncrono
- **Tracking de posição:** `last_tts_end` e `tts_end_pos` corretos — evita re-processar frases já enviadas pro TTS
- **Thread safety:** `ThreadPoolExecutor(max_workers=1)` — sequencial, sem race conditions entre frases
- **Veredicto:** ✅ Correto. Melhoria real de latência

### ✅ Task 2: Whisper tiny como opção
- Claude Code verificou: já existe via `WHISPER_MODEL=tiny` em env vars
- Sem mudanças de código necessárias — correto
- **Veredicto:** ✅ Nada a fazer

### ✅ Task 3: Edge TTS streaming investigado
- Claude Code concluiu: `gr.Audio` substitui elemento a cada yield (não faz append)
- Decisão: manter approach atual — buffer duplo já resolve
- **Veredicto:** ✅ Decisão correta

## Problemas Encontrados

### ⚠️ tts_future não cancelado em exceções
- Nos blocos `except Exception:`, se `tts_future` está rodando, ele continua em background
- O fallback cria NOVO TTS síncrono → pode ter 2 TTS executando simultaneamente
- **Impacto:** mínimo (executor tem max_workers=1, então enfileira em vez de paralelizar)
- **Correção ideal:** `if tts_future: tts_future.cancel()` antes do fallback
- **Urgência:** baixa — não causa bug funcional

### 🟢 Código duplicado nos 3 handlers
- `respond_text`, `respond_audio`, `_process_voice_text` têm lógica de buffer duplo IDÊNTICA (~30 linhas cada)
- Idealmente seria extraído pra uma função `_stream_with_tts()`
- **Impacto:** manutenibilidade — se precisar corrigir o buffer, precisa editar 3 lugares
- **Urgência:** baixa — funciona, mas é DRY violation

## Diff Total Real

```
4 files changed, 320 insertions(+), 108 deletions(-)
```
(inclui auditorias das fases 3 e 4 reescritas por mim)

## Comparação com Auditoria do Claude Code

| Item | Claude Code | Realidade |
|------|-------------|-----------|
| Testes | 215/18 | **219/14** |
| Commit | 03403a0 | **595f795** |
| Diff | 2 files, 136+/36- | **4 files, 320+/108-** (inclui auditorias) |
| Task 1 descrição | ✅ precisa | ✅ confirmado |
| Task 2 descrição | ✅ precisa | ✅ confirmado |
| Task 3 descrição | ✅ precisa | ✅ confirmado |

## Veredito

**✅ FASE 5 APROVADA**
- Buffer duplo implementado corretamente nos 3 handlers
- Melhoria real de latência: TTS em background enquanto LLM streama
- `_tts_executor` dead code da Fase 4 agora está ativo
- **⚠️ Minor:** future não cancelado em exceções + código duplicado em 3 handlers
- **Nenhum bug funcional** — problemas são de robustez/manutenibilidade
