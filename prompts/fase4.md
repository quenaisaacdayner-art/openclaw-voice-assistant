# FASE 4 — Interface melhorada

Leia estes arquivos:
1. CLAUDE.md  
2. UPGRADE_PLAN.md (seção FASE 4)
3. voice_assistant_app.py (inteiro)

## TASKS

### Task 1: Indicadores visuais de estado
Adicionar estados visuais claros na UI:
- 🔴 "Escutando..." — quando gravando áudio ou escuta contínua ativa
- 🧠 "Pensando..." — quando aguardando resposta do LLM
- 🔊 "Falando..." — quando TTS está gerando/tocando
- ⏸️ "Pronto" — estado idle

Implementar com um componente gr.HTML ou gr.Textbox que mostra o estado atual.
Atualizar o estado em cada etapa de respond_text() e respond_audio().

### Task 2: Transcrição parcial em tempo real
No modo de escuta contínua (LOCAL com RealtimeSTT):
- RealtimeSTT já suporta callbacks de transcrição parcial
- Mostrar texto parcial enquanto o usuário fala (antes de finalizar)
- Usar o parâmetro on_realtime_transcription_update do AudioToTextRecorder

No modo BROWSER: não aplicável (transcrição só acontece após silêncio).

### Task 3: Theme escuro
- Usar gr.themes.Soft(primary_hue="blue") como base
- Adicionar CSS customizado pro theme escuro se necessário
- Manter CUSTOM_CSS existente

### Task 4: Mobile-friendly
- Verificar que o layout funciona em tela estreita
- Botões grandes o suficiente pra toque
- Audio input acessível no mobile

### Após tudo
1. Rodar testes: python -m pytest tests/ -v
2. Testar visualmente: python voice_assistant_app.py (abrir no browser)
3. Commitar: git add -A && git commit -m "feat: fase 4 - indicadores visuais, theme escuro, mobile-friendly"
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
