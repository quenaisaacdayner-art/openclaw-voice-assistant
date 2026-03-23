# Registro — S3-D: Metricas de Latencia e TTFA

> Executada: 23/03/2026
> Prompt: `prompts/s3_latencia/s3_completo.md` (Otimizacao 4)
> Objetivo: Medir Time-to-First-Audio (TTFA) no log do backend e enviar metricas pro frontend

## Resultado dos Testes

- **227 passed, 18 skipped, 0 failed**
- Sem regressao

## Prompt seguido?

**Sim, 100%.** Metricas implementadas conforme prompt.

### Mudancas em `server_ws.py` — `_llm_and_tts()` — Checklist

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Aceitar `t_start=None` como parametro | Sim | Linha 102: `async def _llm_and_tts(user_text, t_start=None)` |
| Retornar dict `metrics` com ttft, tts_first, tts_count, response_len | Sim | Linhas 212-217: dict com 4 campos |
| Calcular TTFA = t_tts_first - t_start | Sim | Linha 220: `ttfa = t_tts_first - t_start` |
| Log `[PERF] ⚡ Time-to-First-Audio: X.Xs` | Sim | Linha 221 |
| Docstring atualizada: "Retorna dict com metricas" | Sim | Linha 103 |

### Mudancas em `server_ws.py` — `process_speech()` — Checklist

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Passar `t_start=t0` pra `_llm_and_tts()` | Sim | Linha 270: `metrics = await _llm_and_tts(transcript, t_start=t0)` |
| Enviar mensagem `{"type": "perf"}` com ttft e ttfa | Sim | Linhas 275-281 |

### Mudancas em `server_ws.py` — `process_text()` — Checklist

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Passar `t_start=t0` pra `_llm_and_tts()` | Sim | Linha 312: `metrics = await _llm_and_tts(user_text, t_start=t0)` |
| Enviar mensagem `{"type": "perf"}` com ttft e ttfa | Sim | Linhas 317-323 |

### Mudancas em `static/index.html` — Frontend — Checklist

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Handler `data.type === 'perf'` | Sim | `else if (data.type === 'perf')` antes do switch |
| `console.log` com TTFT e TTFA | Sim | `` console.log(`[PERF] TTFT: ${data.ttft}s | TTFA: ${data.ttfa}s`) `` |
| Nao mostrar na UI (so console) | Sim | Apenas console.log, return implicito |

### Log esperado apos as otimizacoes

```
[REQ] Nova mensagem recebida
[STT] Transcricao: "..." (2.8s)
[LLM] TTFT: 3.2s
[TTS] 1a frase: "..." (0.6s)
[PERF] ⚡ Time-to-First-Audio: 6.6s
[LLM] Resposta completa: 245 chars em 5.1s
[TTS] Total: 3 frases
[TOTAL] Fala→Resposta: 7.8s
```

### Mensagem WebSocket enviada ao frontend

```json
{"type": "perf", "ttft": 3.2, "ttfa": 6.6}
```

## Diferencas vs prompt

Nenhuma diferenca funcional. Implementacao identica ao especificado.
