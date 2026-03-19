# Registro — Fase 5: Latencia

> Executada: 2026-03-19 BRT
> Commit: 03403a0

## Resultado dos Testes

- **215 passed, 18 skipped, 0 failed**
- Fase anterior (Fase 4) tinha 219 passed, 14 skipped (conforme auditoria real)

## Arquivos Criados

- `auditoria/fase5.md` — este registro

## Arquivos Modificados

- `voice_assistant_app.py` — buffer duplo de TTS em `respond_text()`, `respond_audio()` e `_process_voice_text()`: gera TTS frase-a-frase com ThreadPoolExecutor em background (overlap TTS generation + LLM streaming)

## Arquivos Deletados

Nenhum

## O que foi feito

- **Task 1 (Buffer duplo de TTS):** Substituido o approach de "TTS so na primeira frase + resto no final" por geracao frase-a-frase. Cada vez que `_find_sentence_end()` detecta fim de frase, submete TTS ao `_tts_executor` (ThreadPoolExecutor max_workers=1) em background. Enquanto o TTS gera, o LLM continua streamando. Quando o future completa, o audio e yielded pro Gradio (autoplay). Isso elimina gap entre frases.
- **Task 2 (Whisper tiny como opcao):** Ja funcional — env var `WHISPER_MODEL` existe em `config.py`, usada em `stt.py`, documentada no `README.md`. Setar `WHISPER_MODEL=tiny` usa modelo 3x mais rapido.
- **Task 3 (Edge TTS streaming):** Investigado. Gradio `gr.Audio` com `autoplay=True` substitui o elemento inteiro a cada yield — nao suporta streaming progressivo (append de chunks a audio em reproducao). O `edge_tts.Communicate.save()` ja faz streaming interno. O buffer duplo da Task 1 ja resolve a latencia principal. Approach atual mantido conforme instrucao.

## Problemas encontrados durante a execucao

- Task 3 (Edge TTS streaming chunk-a-chunk) nao e viavel com Gradio — o componente `gr.Audio` nao suporta streaming progressivo de output. Mantido approach atual.
- Tasks 2 ja estava implementada de fases anteriores — nenhuma alteracao necessaria.

## Diff total

```
 auditoria/fase5.md     |  36 +++++++++++++
 voice_assistant_app.py | 136 ++++++++++++++++++++++++++++++++++++-------------
 2 files changed, 136 insertions(+), 36 deletions(-)
```
