# Registro — S2-C: Slider de Velocidade TTS

> Executada: 23/03/2026
> Prompt: `prompts/s2_pipeline_audio/s2_completo.md` (Feature 3)
> Objetivo: Slider 0.5x-2.0x no config panel que controla velocidade do TTS (Kokoro + Edge)

## Resultado dos Testes

- **227 passed, 18 skipped, 0 failed**

## Prompt seguido?

**Sim, 100%.** Todas as instrucoes da Feature 3 foram seguidas.

### Mudancas em `core/tts.py`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| `_tts_speed = 1.0` variavel mutavel | Sim | Linha 66 |
| `get_speed()` | Sim | Linhas 223-224 |
| `set_speed()` com clamp 0.5-2.0 | Sim | Linhas 227-233 |
| Kokoro usa `_tts_speed` em `create()` | Sim | Linha 268: `speed=_tts_speed` |
| Edge usa `rate` como `+XX%`/`-XX%` | Sim | Linhas 315-317 |
| Piper ignora velocidade (intencional) | Sim | Documentado no `<small>` do HTML |

### Mudancas em `static/index.html`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Slider `cfgSpeed` min=0.5 max=2.0 step=0.1 | Sim | Linha 451 |
| Label `cfgSpeedLabel` atualiza em tempo real | Sim | Linhas 1049-1052 (evento `input`) |
| Envia ao server ao soltar | Sim | Linhas 1053-1058 (evento `change`) |
| Envia `{type: 'config', tts_speed: ...}` | Sim | Linha 1056 |

### Mudancas em `server_ws.py`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Config handler: `data.get("tts_speed")` | Sim | Linhas 393-396 |
| `if speed is not None` (aceita 0) | Sim | Correto — nao usa truthiness |
| Chama `set_speed(float(speed))` | Sim | Linha 396 |

## Analise critica

### Edge TTS `rate` kwarg

O prompt avisa pra verificar se `edge_tts.Communicate()` aceita `rate`. Verificacao:
- `edge_tts` aceita `rate` como parametro documentado (formato: "+50%", "-30%")
- A implementacao usa `**kwargs` pra passar `voice` e opcionalmente `rate`
- Se a API do edge_tts mudar no futuro, o `try/except` em `generate_tts_edge` captura e o fallback chain continua

### Clamp funciona corretamente

`set_speed()` faz `max(0.5, min(2.0, float(speed)))` — valores fora do range sao truncados, nao rejeitados. Isso e o comportamento correto pra um slider (o frontend ja limita, mas o backend nao confia).

## Criterios de sucesso — checklist

- [x] Slider 0.5x-2.0x no config panel
- [x] Label atualiza em tempo real
- [x] 1.5x → resposta mais rapida (Kokoro/Edge)
- [x] 0.7x → resposta mais devagar (Kokoro/Edge)
- [x] Server log: "[TTS] Velocidade: 1.0x → 1.5x"
- [x] Piper ignora configuracao (documentado no UI)
