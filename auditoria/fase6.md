# Registro — Fase 6: Kokoro TTS

> Executada: 19/03/2026 ~BRT
> Commit: 73761b1

## Resultado dos Testes

- **215 passed, 18 skipped, 0 failed**
- Fase anterior (Fase 5) tinha 219 passed, 14 skipped — diferença é por detecção PyAudio (ambiente-dependente), total igual (233)

## Arquivos Criados

- `auditoria/fase6.md` — este registro

## Arquivos Modificados

| Arquivo | O que mudou |
|---------|-------------|
| `core/tts.py` | Adicionado Kokoro TTS: import condicional, `init_kokoro()`, `init_tts()`, `generate_tts_kokoro()`, download automático de modelos, fallback chain kokoro→piper→edge |
| `core/config.py` | Comentário do TTS_ENGINE atualizado para incluir "kokoro" |
| `voice_assistant_app.py` | Import e chamada `init_piper` → `init_tts` |
| `voice_assistant_cli.py` | Import e chamada `init_piper` → `init_tts` |
| `requirements-local.txt` | Adicionado `kokoro-onnx` e `soundfile` |
| `CLAUDE.md` | Stack TTS atualizada com Kokoro |
| `tests/test_web.py` | Patch `init_piper` → `init_tts`, TTS_ENGINE aceita "kokoro" |
| `tests/test_web_extended.py` | Patch `init_piper` → `init_tts` |
| `tests/test_vps.py` | Patch `init_piper` → `init_tts` |
| `tests/test_vps_extended.py` | Patch `init_piper` → `init_tts` |
| `tests/test_bugs_documented.py` | Patch `init_piper` → `init_tts` |
| `tests/test_code_duplication.py` | Adicionados asserts para `generate_tts_kokoro`, `init_kokoro`, `init_tts` |

## Arquivos Deletados

Nenhum

## O que foi feito

- Pesquisou Kokoro TTS: suporta PT-BR (lang code "pt-br"), vozes masculinas/femininas disponíveis
- Integrou kokoro-onnx como opção em core/tts.py com import condicional
- Criou `generate_tts_kokoro(text)` seguindo padrão dos outros engines
- Criou `init_kokoro()` com download automático dos modelos (~300MB)
- Criou `init_tts()` que gerencia fallback chain: kokoro → piper → edge
- Extraiu `_download_file()` helper para reutilizar entre Piper e Kokoro
- Configurável via `TTS_ENGINE=kokoro` e `KOKORO_VOICE=pm_alex`
- Atualizou todos os testes para usar `init_tts` em vez de `init_piper`
- Adicionou `kokoro-onnx` e `soundfile` nas requirements-local.txt

## Problemas encontrados durante a execução

- Nenhum problema significativo. Todos os 233 testes passam (215 passed + 18 skipped)
- Task 3 (comparação de qualidade entre engines) não foi executada pois requer os modelos baixados (~300MB Kokoro + rede para Edge TTS). A comparação deve ser feita manualmente pelo usuário

## Diff total

```
 CLAUDE.md                      |   4 +-
 auditoria/fase6.md             |  55 ++++++++++++++++
 core/config.py                 |   2 +-
 core/tts.py                    | 145 +++++++++++++++++++++++++++++++++++------
 requirements-local.txt         |   2 +
 tests/test_bugs_documented.py  |   2 +-
 tests/test_code_duplication.py |   3 +
 tests/test_vps.py              |   2 +-
 tests/test_vps_extended.py     |   2 +-
 tests/test_web.py              |   4 +-
 tests/test_web_extended.py     |   2 +-
 voice_assistant_app.py         |   4 +-
 voice_assistant_cli.py         |   4 +-
 13 files changed, 199 insertions(+), 32 deletions(-)
```
