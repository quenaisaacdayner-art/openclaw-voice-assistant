# FASE 5 — Latência

Leia estes arquivos:
1. CLAUDE.md
2. UPGRADE_PLAN.md (seção FASE 5)
3. core/tts.py
4. core/stt.py
5. core/llm.py
6. voice_assistant_app.py (funções respond_text e respond_audio)

## TASKS

### Task 1: Buffer duplo de TTS
Enquanto a frase N está sendo enviada pro browser (autoplay), já gerar a frase N+1.
- Em respond_text(), quando _find_sentence_end() detecta fim de frase:
  1. Gerar TTS da frase atual
  2. Yield pro Gradio (que faz autoplay)
  3. Continuar acumulando a próxima frase
- Usar threading ou asyncio pra overlap TTS generation + streaming LLM

### Task 2: Whisper tiny como opção
- Adicionar env var WHISPER_MODEL (já existe em config.py)
- Documentar que "tiny" é 3x mais rápido mas menor qualidade
- Garantir que funciona: python -c "from faster_whisper import WhisperModel; m = WhisperModel('tiny', device='cpu', compute_type='int8')"

### Task 3: Edge TTS streaming (chunk por chunk)
Edge TTS já suporta streaming — em vez de salvar MP3 inteiro e depois tocar:
1. Receber chunks de áudio via edge_tts.Communicate().stream()
2. Enviar cada chunk pro Gradio assim que chega
3. Resultado: primeira palavra em ~1s vs ~3s atuais

Investigar se Gradio gr.Audio suporta streaming de output. Se não, manter approach atual.

### Após tudo
1. Rodar testes: python -m pytest tests/ -v
2. Testar latência real: cronometrar tempo entre fim da pergunta e início da resposta falada
3. Commitar: git add -A && git commit -m "perf: fase 5 - buffer duplo TTS, opção whisper tiny"
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
