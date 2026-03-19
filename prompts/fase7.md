# FASE 7 — Open Source / DX

Leia estes arquivos:
1. CLAUDE.md
2. UPGRADE_PLAN.md (seção FASE 7)
3. README.md (se existir)
4. .gitignore
5. requirements.txt
6. requirements-local.txt

## TASKS

### Task 1: README completo
Reescrever README.md com:
- Título + descrição (1 parágrafo)
- Screenshot ou placeholder pra GIF
- Features (bullet list)
- Instalação rápida (3 comandos)
- Modos de uso (CLI, Local Gradio, VPS/Remoto)
- Configuração (env vars)
- Arquitetura (diagrama ASCII do pipeline)
- Stack técnico
- Contribuindo (link pra CONTRIBUTING.md)
- Licença

### Task 2: .env.example
Todas as env vars documentadas com valores default e descrição:
- OPENCLAW_GATEWAY_URL
- OPENCLAW_GATEWAY_TOKEN
- OPENCLAW_MODEL
- TTS_VOICE
- TTS_ENGINE
- WHISPER_MODEL
- SERVER_HOST
- PORT

### Task 3: CONTRIBUTING.md
- Como rodar localmente
- Como rodar testes
- Estrutura do código (core/ + scripts)
- Guidelines de PR

### Task 4: GitHub Actions CI
Criar .github/workflows/test.yml:
- Trigger: push + PR
- Python 3.10, 3.11, 3.12, 3.13
- pip install -r requirements.txt + pytest
- Rodar: python -m pytest tests/ -v
- NÃO precisa de Whisper model (testes mockam tudo)

### Task 5: Scripts auxiliares
- scripts/connect.sh — tunnel SSH pra VPS (5 linhas, já especificado no UPGRADE_PLAN)

### Após tudo
1. Rodar testes: python -m pytest tests/ -v
2. Verificar que CI workflow é válido: revisar YAML syntax
3. Commitar: git add -A && git commit -m "docs: fase 7 - README, CI, CONTRIBUTING, .env.example"
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
