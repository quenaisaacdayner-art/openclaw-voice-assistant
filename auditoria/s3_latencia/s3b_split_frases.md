# Registro — S3-B: Split de Frases Mais Agressivo

> Executada: 23/03/2026
> Prompt: `prompts/s3_latencia/s3_completo.md` (Otimizacao 2)
> Objetivo: TTS comeca antes no streaming do LLM — detectar \n e reduzir threshold de virgula

## Resultado dos Testes

- **227 passed, 18 skipped, 0 failed**
- Sem regressao
- Testes existentes de `_find_sentence_end` continuam passando (pontuacao forte, exclamacao, interrogacao, ellipsis, numero com ponto)

## Prompt seguido?

**Sim, 100%.** Funcao `_find_sentence_end()` substituida inteiramente conforme prompt.

### Mudancas em `core/llm.py` — `_find_sentence_end()` — Checklist

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Prioridade 1: pontuacao forte (.!?…) + espaco ou fim | Sim | `re.search(r'[.!?…](\s|$)', text)` — inalterado |
| Prioridade 2: quebra de linha (\n) — NOVA | Sim | `text.find('\n')` + avanco por \n consecutivos |
| Prioridade 3: ponto-e-virgula, dois-pontos + espaco | Sim | `re.search(r'[;:](\s|$)', text)` — inalterado |
| Prioridade 4: virgula + espaco se texto > 50 chars (era 80) | Sim | Threshold reduzido de 80 pra 50 |
| Retornar posicao APOS o \n (e consecutivos) | Sim | Loop `while end < len(text) and text[end] == '\n': end += 1` |
| Docstring atualizada com 4 prioridades | Sim | Docstring reflete nova ordem |

### Antes vs Depois

| Aspecto | Antes | Depois |
|---------|-------|--------|
| Prioridades | 3 (forte, ;:, virgula) | 4 (forte, \n, ;:, virgula) |
| Threshold virgula | 80 chars | 50 chars |
| Deteccao de \n | Nao existia | Prioridade 2 |

### Impacto esperado

- Respostas com listas (`1.\n2.\n3.`) geram TTS por item em vez de esperar o fim da lista
- Paragrafos separados por `\n` geram TTS independente por paragrafo
- Frases com virgula acima de 50 chars (antes 80) fazem split mais cedo

## Diferencas vs prompt

Nenhuma. Codigo identico ao especificado no prompt.
