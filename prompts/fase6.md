# FASE 6 — Kokoro TTS

Leia estes arquivos:
1. CLAUDE.md
2. UPGRADE_PLAN.md (seção FASE 6)
3. core/tts.py
4. core/config.py

## CONTEXTO

Kokoro é um TTS local de alta qualidade (MIT license). Queremos testar se a voz PT-BR é boa.

## TASKS

### Task 1: Pesquisar Kokoro
- Verificar se kokoro-onnx ou kokoro suporta PT-BR
- Se sim: qual modelo, tamanho, qualidade
- Se não: documentar e pular esta fase

### Task 2: Integrar (se PT-BR disponível)
1. Adicionar kokoro como opção em core/tts.py
2. TTS_ENGINE aceita: "piper", "edge", "kokoro"
3. Criar generate_tts_kokoro(text) seguindo o padrão dos outros
4. Fallback: kokoro → piper → edge
5. Adicionar kokoro nas requirements-local.txt

### Task 3: Testar qualidade
1. Gerar mesmo texto com os 3 engines
2. Comparar tamanho dos arquivos e tempo de geração
3. Documentar resultado no CLAUDE.md

### Após tudo
1. Rodar testes: python -m pytest tests/ -v
2. Commitar: git add -A && git commit -m "feat: fase 6 - kokoro TTS como opção"
3. NÃO fazer git push

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
