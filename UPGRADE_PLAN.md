# Upgrade Plan — Sessão de Upgrades

> Criado: 17/03/2026
> Status: PENDENTE — executar na próxima sessão

## Objetivo
Transformar o protótipo funcional em assistente de voz fluido: sem botão pra gravar, voz quase humana, resposta em tempo real.

## 3 Upgrades (ordem de execução)

### Upgrade 1: RealtimeSTT — Escuta Contínua (~30 min)

**O que muda:** Hoje tu clica pra gravar → para → envia. Com RealtimeSTT, tu FALA e ele detecta automaticamente quando tu começa e para de falar (VAD = Voice Activity Detection).

**Biblioteca:** [RealtimeSTT](https://github.com/KoljaB/RealtimeSTT)
- Wrapper de faster-whisper + Silero VAD
- Detecta início e fim de fala automaticamente
- Transcreve em tempo real (parcial + final)

**Implementação:**
1. `pip install RealtimeSTT`
2. Substituir lógica de gravação manual por `AudioToTextRecorder`
3. Callback `on_realtime_transcription` mostra texto parcial no Gradio
4. Callback `process_text` envia texto final pro OpenClaw
5. Manter fallback de texto digitado

**Risco:** Gradio + streaming de áudio contínuo pode ter conflito. Se travar, fallback: manter botão mas com VAD (para de gravar sozinho quando detecta silêncio).

**Teste de aceitação:** Abrir browser → falar uma frase → assistente responde sem tu clicar nada.

---

### Upgrade 2: Kokoro TTS — Voz Quase Humana (~30 min)

**O que muda:** Edge TTS (Microsoft) é funcional mas soa robótico. Kokoro TTS roda local e tem qualidade próxima de voz humana.

**Biblioteca:** [Kokoro](https://github.com/hexgrad/kokoro)
- Modelos ~80MB (leve)
- Roda 100% local, sem internet
- Suporte a português via vozes multilíngues
- Latência menor que edge-tts (sem rede)

**Implementação:**
1. `pip install kokoro`
2. Baixar modelo PT-BR (ou multilíngue)
3. Criar função `generate_tts_kokoro()` como alternativa
4. Config: `TTS_ENGINE=kokoro|edge` (env var)
5. Manter edge-tts como fallback (Kokoro precisa de download inicial)

**Risco:** Kokoro pode não ter voz PT-BR natural. Se qualidade for ruim → testar Piper TTS como alternativa. Se ambos forem piores que edge-tts → manter edge-tts.

**Teste de aceitação:** Ouvir resposta e comparar com edge-tts. Se Kokoro for melhor → default. Se não → manter edge-tts.

---

### Upgrade 3: Streaming — Resposta em Tempo Real (~20 min)

**O que muda:** Hoje espera a resposta INTEIRA do OpenClaw antes de mostrar e falar. Com streaming, o texto aparece palavra por palavra e a voz começa antes de terminar.

**Implementação:**
1. Mudar `ask_openclaw()` pra usar `stream: true` na API
2. Processar SSE (Server-Sent Events) chunk por chunk
3. Mostrar texto no Gradio conforme chega (via `yield`)
4. TTS: acumular ~1 frase → gerar áudio → tocar enquanto próxima frase chega
5. Resultado: texto aparece em ~1s, voz começa em ~3s (vs 8-10s atual)

**Risco:** TTS por frase pode ter gaps entre frases. Solução: buffer de 2 frases (gera a próxima enquanto a atual toca).

**Teste de aceitação:** Fazer pergunta → texto começa a aparecer em <2s → voz começa antes do texto terminar.

---

## Ordem de Prioridade

1. **Kokoro TTS** — impacto maior com menor risco
2. **Streaming** — segunda maior melhoria de UX
3. **RealtimeSTT** — maior impacto mas maior risco técnico

## Critério de Parada

Se algum upgrade não funcionar em 20 min de debug → PARAR e manter versão atual desse componente. Não entrar em rabbit hole.

## Depois dos Upgrades

- Commit + push pro GitHub
- Atualizar README com novas features
- Criar issues no repo pras features futuras
- Documentar o que aprendeu (daily + possível post)
