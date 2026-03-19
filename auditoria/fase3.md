# Registro — Fase 3: Limpeza do repo

> Executada: 2026-03-19 00:23 BRT
> Commit: c69ae14

## Resultado dos Testes

- **215 passed, 18 skipped, 0 failed**
- Fase 2 tinha 233 collected (mesmo baseline — skips são testes que dependem de PyAudio/hardware)

## Arquivos Criados

- `requirements-local.txt` — 4 linhas, requirements extras pra modo local (PyAudio, RealtimeSTT, piper-tts)
- `models/.gitkeep` — placeholder pra manter a pasta no git
- `scripts/teste_tts.py` — movido de raiz pra scripts/ (53 linhas, teste isolado de Edge TTS)

## Arquivos Modificados

- `core/tts.py` — adicionada função `download_piper_model()` que baixa modelo do HuggingFace se não existe; `init_piper()` chama download antes de carregar
- `requirements.txt` — reescrito com deps base apenas (sem PyAudio, RealtimeSTT, piper-tts)
- `.gitignore` — limpo entradas com espaços quebrados, adicionado models/*.onnx, models/*.onnx.json, __pycache__/, *.pyc, .pytest_cache/
- `tests/test_code_duplication.py` — `test_old_scripts_still_exist` invertido para `test_old_scripts_removed`

## Arquivos Deletados

- `voice_assistant.py` — substituído por voice_assistant_cli.py na Fase 1
- `voice_assistant_web.py` — substituído por voice_assistant_app.py na Fase 1
- `voice_assistant_vps.py` — substituído por voice_assistant_app.py na Fase 1
- `teste_tts.py` — movido para scripts/teste_tts.py
- `models/pt_BR-faber-medium.onnx` — removido do git tracking (60MB), agora baixado automaticamente
- `models/pt_BR-faber-medium.onnx.json` — removido do git tracking

## O que foi feito

- Criada função `download_piper_model()` em core/tts.py que baixa modelo Piper do HuggingFace com progresso
- Integrada chamada de download em `init_piper()` antes de carregar o modelo
- Adicionado models/*.onnx e models/*.onnx.json ao .gitignore
- Removidos arquivos de modelo do git tracking com `git rm --cached`
- Criado .gitkeep pra manter pasta models/ no git
- Separados requirements: base (requirements.txt) e local (requirements-local.txt)
- Limpado .gitignore removendo entradas com espaços quebrados e duplicatas
- Deletados 3 scripts antigos (voice_assistant.py, voice_assistant_web.py, voice_assistant_vps.py)
- Movido teste_tts.py para scripts/
- Adaptado teste que verificava existência dos scripts antigos
- Todos os 215 testes passam

## Problemas encontrados durante a execução

- O size-pack do repo ainda mostra 55MB porque o modelo está no histórico do git (pack files). Isso é esperado — só seria resolvido com `git filter-repo` (operação destrutiva no histórico). Clones shallow (`--depth 1`) já não incluem o modelo.

## Diff total

```
 .gitignore                           | Bin 397 -> 441 bytes
 auditoria/fase3.md                   |  53 +++
 core/tts.py                          |  33 ++
 models/.gitkeep                      |   0
 models/pt_BR-faber-medium.onnx       | Bin 63201294 -> 0 bytes
 models/pt_BR-faber-medium.onnx.json  | 491 ----------------------
 requirements-local.txt               |   4 +
 requirements.txt                     |   6 +-
 teste_tts.py => scripts/teste_tts.py |   0
 tests/test_code_duplication.py       |   8 +-
 voice_assistant.py                   | 384 -----------------
 voice_assistant_vps.py               | 677 ------------------------------
 voice_assistant_web.py               | 783 -----------------------------------
 13 files changed, 96 insertions(+), 2343 deletions(-)
```
