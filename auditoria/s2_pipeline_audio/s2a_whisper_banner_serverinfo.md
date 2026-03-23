# Registro — S2-A: Whisper small + Banner TTS + server_info

> Executada: 23/03/2026
> Prompt: `prompts/s2_pipeline_audio/s2_completo.md` (Feature 1)
> Objetivo: Melhorar transcricao (tiny → small), mostrar engine TTS no startup, enviar server_info via WS ao conectar

## Resultado dos Testes

- **227 passed, 18 skipped, 0 failed**
- Teste `test_default_whisper_model` atualizado pra "small"

## Prompt seguido?

**Sim, 100%.** Todas as instrucoes da Feature 1 foram seguidas.

### Mudancas em `core/config.py`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Default `WHISPER_MODEL_SIZE` de "tiny" pra "small" | Sim | Linha 28 |
| `WHISPER_MODEL` env var continua funcionando | Sim | `os.environ.get` preservado |

### Mudancas em `core/stt.py`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| `_get_whisper()` usa `_current_model_size` | Sim | Ja existia de S1 — nao duplicado |
| `set_whisper_model()` nao duplicado | Sim | Ja existia de S1 |
| `get_current_model()` adicionado | Sim | Linhas 41-43 |
| `init_stt()` usa `_current_model_size` no log | Sim | Linha 52 (era `WHISPER_MODEL_SIZE`) |

### Mudancas em `server_ws.py`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Banner TTS apos warmup | Sim | Linha 37-38 |
| `server_info` enviado via WS apos `accept()` | Sim | Linhas 78-86 |

### Mudancas em `static/index.html`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Handler `server_info` no `ws.onmessage` | Sim | Linhas 599-627 |
| Popula engine label | Sim | Linhas 603-607 |
| Popula voice dropdown | Sim | Linhas 609-620 |
| Popula speed slider | Sim | Linhas 622-627 |

## Bug detectado e corrigido

**Import de variaveis privadas no top-level de `server_ws.py`.**

O import original era:
```python
from core.tts import _tts_engine, kokoro_instance, piper_voice, KOKORO_VOICE
```

Isso capturava os valores no momento do import (antes de `init_tts()`), fazendo:
- `_tts_engine` = valor pre-fallback (ex: "kokoro" mesmo se Kokoro indisponivel)
- `kokoro_instance` = `None` (sempre, pois `init_tts()` ainda nao rodou)
- `piper_voice` = `None` (idem)

**Resultado:** banner nunca mostraria Kokoro ou Piper, e `server_info.tts_engine` ficaria errado.

**Correcao:** Criados `get_engine()` e `get_tts_info()` em `tts.py` que leem o estado atual do modulo. `server_ws.py` agora usa essas funcoes. Commit: `0b99be5`.

## Criterios de sucesso — checklist

- [x] Default mudou pra small (startup mostra "Carregando Whisper (small)")
- [x] `WHISPER_MODEL=tiny` env var override funciona
- [x] Startup mostra "TTS Engine: ..." com engine ativo
- [x] `server_info` enviado via WS ao conectar
- [x] Reconectar re-popula dropdown + slider via server_info
