# Auditoria — Fase 2: Corrigir Bugs Conhecidos

> Executada: 2026-03-19 ~00:00-00:10 BRT
> Auditada por: OpenClaw Principal (Opus 4)
> Commit: d78edeb

## Resultado dos Testes

- **Real: 219 passed, 14 skipped, 0 failed**
- Claude Code reportou: "215 passed, 18 skipped" — **números errados de novo**
- Diferença vs Fase 1: 216 → 219 (+3 testes novos), skips mantidos 14

## Bugs Corrigidos

### ✅ Bug 1: PortAudioError `__str__` (voice_assistant_cli.py:75)
- **Fix:** `{e}` → `{str(e)}` no f-string
- **Veredicto:** Correto, fix defensivo

### ✅ Bug 2: MIN_SPEECH_CHUNKS contava silêncio (voice_assistant_app.py)
- **Fix:** Novo campo `speech_chunk_count` — só incrementa com `rms > threshold`
- **Antes:** `len(audio_buffer)` incluía chunks de silêncio → transcrevia silêncio puro
- **Depois:** Só transcreve quando tem N chunks com áudio real
- **Veredicto:** Fix correto e bem implementado

### ✅ Bug 3: build_api_history descartava mensagens de voz (core/history.py)
- **Fix:** Remove prefixo `[🎤 Voz]: ` mas mantém o conteúdo
- **Antes:** Descartava TUDO que começava com `[🎤` → LLM perdia contexto de voz
- **Depois:** Strip do prefixo, conteúdo preservado. Edge case (sem `]: `) mantém original
- **Veredicto:** Fix correto, edge case coberto por teste novo

### ✅ Bug 4: `_find_sentence_end` não detectava pontuação no fim (core/llm.py)
- **Fix:** Regex `[.!?…]\s` → `[.!?…](\s|$)`
- **Antes:** "Frase completa." retornava 0 (sem match)
- **Depois:** Detecta pontuação no fim da string
- **Veredicto:** Fix correto

### ✅ Bug 5: TTS filtra ❌ só no início (core/tts.py)
- **Decisão:** Mantido como intencional + comentário explicativo
- **Veredicto:** Decisão correta — over-engineering evitado

## Extra não solicitado

### ⚠️ Download automático do modelo Piper (core/tts.py)
- Adicionou `download_piper_model()` que baixa de HuggingFace se não existe
- **Não era bug listado** — é feature preventiva
- Aceitável mas vai além do escopo da Fase 2

## 🚨 PROBLEMA ENCONTRADO

### Teste `test_old_scripts_removed` preparado ANTES da deleção
- Em `test_code_duplication.py`, mudou o teste de "old scripts should exist" → "old scripts were removed in Fase 3"
- Os scripts foram deletados no working tree (`git status` mostra `D`) mas **NÃO commitados**
- O teste passa AGORA porque os arquivos estão fisicamente ausentes
- **Se alguém fizer `git checkout .` (restore), o teste QUEBRA**
- **Conclusão:** misturou trabalho da Fase 3 (deleção de scripts antigos) com Fase 2 (bug fixes)
- **Impacto:** baixo se a Fase 3 for executada logo. Mas é anti-pattern — cada fase deve ser autocontida

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `core/history.py` | Fix: strip prefixo voz em vez de descartar |
| `core/llm.py` | Fix: regex `(\s\|$)` no sentence end |
| `core/tts.py` | Comentário intencional + download_piper_model() |
| `voice_assistant_cli.py` | Fix: `str(e)` no PortAudioError |
| `voice_assistant_app.py` | Fix: `speech_chunk_count` no BrowserContinuousListener |
| `tests/test_bugs_documented.py` | Reescrito: testes agora verificam comportamento CORRETO |
| `tests/test_shared_logic.py` | Atualizado pra novos comportamentos |
| `tests/test_web_extended.py` | Atualizado pra novos comportamentos |
| `tests/test_code_duplication.py` | ⚠️ Mudou teste de existência → remoção (prematuramente) |
| `requirements.txt` | Mudanças menores (CRLF) |

## Diff Total

```
9 files changed, 132 insertions(+), 61 deletions(-)
```

## Veredito

**✅ FASE 2 APROVADA com ressalvas:**
- 4/4 bugs corrigidos corretamente
- Bug 5 mantido como intencional (decisão correta)
- Testes atualizados de "documentar bug" → "verificar fix"
- **⚠️ Misturou escopo da Fase 3** (teste de deleção + deleção de arquivos no working tree)
- **⚠️ Números de testes errados** (reportou 215/18, real 219/14) — padrão recorrente do Claude Code
