# Auditoria — Fase 3: Limpeza do Repo

> Executada: 2026-03-19 ~00:23 BRT
> Auditada por: OpenClaw Principal (Opus 4)
> Commit: 677f259
> Auditoria do Claude Code: COMPARADA abaixo

## Resultado dos Testes

- **Real: 219 passed, 14 skipped, 0 failed**
- Claude Code reportou: **215 passed, 18 skipped** — ERRADO (3ª vez consecutiva, mesmo padrão)
- Igual à Fase 2 (nenhum teste novo/removido nesta fase)

## Comparação: Auditoria Claude Code vs Realidade

| Item | Claude Code disse | Realidade |
|------|-------------------|-----------|
| Testes | 215 passed, 18 skipped | **219 passed, 14 skipped** |
| Commit hash | c69ae14 | **677f259** (hash errado!) |
| Diff insertions | 96 | **111** |
| download_piper_model | "criada na Fase 3" | **Criada na Fase 2** (unstaged) e commitada na Fase 3 |
| test_code_duplication | "invertido" | **Já foi invertido na Fase 2** — agora só commitou a deleção |
| Scripts deletados | ✅ correto | ✅ confirmado |
| Modelo removido do git | ✅ correto | ✅ confirmado |
| requirements separados | ✅ correto | ✅ confirmado |

### Erros do Claude Code na sua própria auditoria
1. **Hash do commit errado** — disse `c69ae14`, real é `677f259`
2. **Números de testes errados** — padrão recorrente: sempre reporta menos passed e mais skipped
3. **Insertions erradas** — disse 96, real 111 (o registro dele tem 68 linhas = 15 linhas de diferença)
4. **Atribuição errada** — `download_piper_model()` foi criada na Fase 2 como mudança não-commitada, não na Fase 3
5. **Linha "Fase 2 tinha 233 collected"** — não faz sentido, são 233 de onde?

### O que o Claude Code acertou
1. Lista de arquivos criados/deletados/modificados ✅
2. Observação sobre size-pack (55MB no histórico) ✅ inteligente
3. Estrutura do registro organizada ✅
4. Movimentação de teste_tts.py → scripts/ ✅

## Verificação por Task

### ✅ Task 1: Modelo Piper fora do git
- `models/pt_BR-faber-medium.onnx` removido do tracking (60MB), continua local
- `models/pt_BR-faber-medium.onnx.json` removido
- `models/.gitkeep` criado (mantém pasta no git)
- `.gitignore` tem `models/*.onnx` e `models/*.onnx.json`
- `download_piper_model()` em `core/tts.py` baixa do HuggingFace com progresso
- **Veredicto:** ✅ Correto

### ✅ Task 2: Requirements separados
- `requirements.txt` — 7 deps base (faster-whisper, edge-tts, requests, gradio, scipy, numpy, sounddevice)
- `requirements-local.txt` — `-r requirements.txt` + PyAudio, RealtimeSTT, piper-tts
- **Veredicto:** ✅ Correto e limpo

### ✅ Task 3: .gitignore limpo
- Entradas com espaços quebrados removidas
- Adicionados: `models/*.onnx`, `.pytest_cache/`, `*.pyc`, etc.
- **Veredicto:** ✅ Correto

### ✅ Task 4: Scripts antigos deletados
- `voice_assistant.py` (384L) — DELETADO ✅
- `voice_assistant_web.py` (783L) — DELETADO ✅
- `voice_assistant_vps.py` (677L) — DELETADO ✅
- `teste_tts.py` movido → `scripts/teste_tts.py` ✅
- **Nota:** deleção já estava feita no working tree desde a Fase 2 (flag da auditoria anterior)

### ✅ Task 5: Testes adaptados
- `test_old_scripts_still_exist` → `test_old_scripts_removed` (já mudado na Fase 2 no commit, agora coerente com os deletes)
- **Veredicto:** ✅ Agora está coerente — teste e deleção no mesmo commit

## Diff Total Real

```
13 files changed, 111 insertions(+), 2343 deletions(-)
```

## Observações

### Sobreposição Fase 2 ↔ Fase 3
Como flagueado na auditoria da Fase 2, parte do trabalho da Fase 3 já tinha sido feito:
- `download_piper_model()` criada na Fase 2 (unstaged)
- `test_old_scripts_removed` mudado na Fase 2 (commitado)
- Deleção dos 3 scripts no working tree na Fase 2 (unstaged)

A Fase 3 basicamente "oficializou" o que já existia + adicionou requirements-local.txt e .gitignore cleanup.

### Padrão de erro do Claude Code (3 fases)
| Fase | Reportou | Real |
|------|----------|------|
| 1 | 212 passed, 18 skipped | **216 passed, 14 skipped** |
| 2 | 215 passed, 18 skipped | **219 passed, 14 skipped** |
| 3 | 215 passed, 18 skipped | **219 passed, 14 skipped** |

Sempre -4 passed e +4 skipped. Possível causa: está rodando os testes com uma versão diferente do working tree ou contando de forma errada. **Consistentemente impreciso.**

## Veredito

**✅ FASE 3 APROVADA** — limpeza completa, nada quebrou, todas as tasks executadas.
**⚠️ Auditoria do Claude Code tem 5 erros factuais** — não pode ser confiada sem verificação independente.
