# FASE 2 — Corrigir bugs conhecidos

Leia estes arquivos:
1. CLAUDE.md
2. UPGRADE_PLAN.md (seção FASE 2)
3. tests/test_bugs_documented.py (30 testes que documentam bugs)
4. core/history.py
5. core/llm.py
6. core/tts.py
7. voice_assistant_app.py (BrowserContinuousListener)
8. voice_assistant_cli.py (record_audio)

## CONTEXTO

Existem 30 testes em test_bugs_documented.py que PASSAM com o comportamento bugado atual.
Esses testes foram escritos como documentação dos bugs — quando corrigirmos, eles vão FALHAR.
Isso é intencional: corrigir o bug + atualizar o teste pra verificar o comportamento CORRETO.

## BUGS PRA CORRIGIR

### Bug 1: PortAudioError.__str__() retorna int
**Onde:** voice_assistant_cli.py, função record_audio
**Problema:** `sd.PortAudioError(-1)` — o `__str__` retorna int, não string. O f-string crasharia.
**Fix:** Envolver em str(): `print(f"❌ Erro no microfone: {str(e)}")`

### Bug 2: MIN_SPEECH_CHUNKS conta chunks de silêncio
**Onde:** voice_assistant_app.py, BrowserContinuousListener.feed_chunk()
**Problema:** `self.chunks_received` conta TODOS os chunks (incluindo silêncio), não só os de fala.
**Fix:** Adicionar contador separado `speech_chunk_count` que incrementa só quando `energy > threshold`.
Usar esse contador na verificação de MIN_SPEECH_CHUNKS.

### Bug 3: build_api_history filtra mensagens [🎤 inteiras
**Onde:** core/history.py
**Problema:** Mensagens que começam com `[🎤` são descartadas completamente. Isso significa que tudo que o usuário diz por voz é removido do histórico enviado pro LLM.
**Fix:** Em vez de descartar a mensagem, remover apenas o prefixo. Se content começa com `[🎤 Voz]: `, extrair o texto após o prefixo. Se começa com `[🎤` mas não tem `: `, manter como está.

### Bug 4: _find_sentence_end não detecta pontuação no fim da string
**Onde:** core/llm.py
**Problema:** Regex `[.!?…]\s` exige espaço APÓS a pontuação. "Olá mundo." não matcheia porque não tem espaço depois do ponto.
**Fix:** Regex `[.!?…](\s|$)` — aceita espaço OU fim da string.

### Bug 5: generate_tts só filtra "❌" no início
**Onde:** core/tts.py
**Problema:** `text.startswith("❌")` — se o erro estiver no meio do texto, gera TTS com "❌".
**Decisão:** Manter como está e documentar como intencional (na prática, erros sempre começam com ❌). NÃO corrigir este — só adicionar comentário explicando.

## COMO EXECUTAR

1. Corrigir cada bug no código fonte (core/ e scripts)
2. Ler test_bugs_documented.py — cada teste que documenta um bug corrigido agora deve ser REESCRITO pra verificar o comportamento CORRETO
3. Testes de bugs NÃO corrigidos (bug 5) continuam documentando o comportamento atual
4. Rodar: python -m pytest tests/ -v
5. TODOS os testes devem passar
6. Commitar: git add -A && git commit -m "fix: fase 2 - corrigir 4 bugs documentados"
7. NÃO fazer git push

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
