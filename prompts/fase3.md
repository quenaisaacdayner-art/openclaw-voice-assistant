# FASE 3 — Limpeza do repo

Leia estes arquivos:
1. CLAUDE.md
2. UPGRADE_PLAN.md (seção FASE 3)
3. .gitignore
4. requirements.txt

## TASKS

### Task 1: Modelo Piper fora do git
O arquivo models/pt_BR-faber-medium.onnx tem 60MB e está no git. Isso é errado.

1. Criar função download_piper_model() em core/tts.py que:
   - Checa se o modelo existe em models/
   - Se não existe, baixa de uma URL pública (usar HuggingFace: https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx)
   - Mostra progresso do download
   - Salva em models/
2. Chamar download_piper_model() dentro de init_piper() antes de carregar
3. Adicionar models/*.onnx e models/*.onnx.json ao .gitignore
4. Remover do git tracking: git rm --cached models/pt_BR-faber-medium.onnx (e o .json se existir)
5. Manter a pasta models/ com um .gitkeep

### Task 2: Requirements separados
Criar:
- requirements.txt — dependências base (faster-whisper, edge-tts, requests, gradio, scipy, numpy)
- requirements-local.txt — extras pra modo local (-r requirements.txt + PyAudio, RealtimeSTT, piper-tts)

### Task 3: .gitignore limpo
Verificar e corrigir entradas com espaços quebrados ou duplicadas.
Adicionar: models/*.onnx, models/*.onnx.json, __pycache__/, *.pyc, .pytest_cache/

### Task 4: Remover scripts antigos
- Deletar voice_assistant.py (substituído por voice_assistant_cli.py)
- Deletar voice_assistant_web.py (substituído por voice_assistant_app.py)  
- Deletar voice_assistant_vps.py (substituído por voice_assistant_app.py)
- Mover teste_tts.py pra scripts/teste_tts.py

### Task 5: Adaptar testes
- Testes que importam dos scripts antigos (voice_assistant, voice_assistant_web, voice_assistant_vps) devem ser removidos ou adaptados se ainda não foram na Fase 1
- Rodar: python -m pytest tests/ -v — tudo deve passar

### Após tudo
1. Rodar testes: python -m pytest tests/ -v
2. Verificar tamanho do repo: git count-objects -vH
3. Commitar: git add -A && git commit -m "chore: fase 3 - limpeza repo, modelo fora do git, requirements separados"
4. NÃO fazer git push

---

## REGISTRO OBRIGATÓRIO

Antes de commitar, crie o arquivo uditoria/faseN.md (substituir N pelo número da fase) com:

`markdown
# Registro — Fase N: [nome]

> Executada: [data e hora BRT]
> Commit: [hash curto]

## Resultado dos Testes

- **X passed, Y skipped, Z failed**
- Comparar com a fase anterior (Fase N-1 tinha A passed)

## Arquivos Criados
[lista com nome, linhas, descrição curta]

## Arquivos Modificados
[lista com nome, o que mudou]

## Arquivos Deletados
[lista ou "nenhum"]

## O que foi feito
[resumo em bullets do que realmente executou]

## Problemas encontrados durante a execução
[erros, retries, decisões tomadas, coisas que não saíram como esperado]

## Diff total
[output de git diff --stat HEAD~1]
`

Este registro é OBRIGATÓRIO. Não commitar sem ele.
