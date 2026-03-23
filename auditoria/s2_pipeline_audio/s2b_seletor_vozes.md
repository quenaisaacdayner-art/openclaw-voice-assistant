# Registro — S2-B: Seletor de Vozes TTS

> Executada: 23/03/2026
> Prompt: `prompts/s2_pipeline_audio/s2_completo.md` (Feature 2)
> Objetivo: Permitir troca de voz TTS dentro do engine ativo via dropdown no config panel

## Resultado dos Testes

- **227 passed, 18 skipped, 0 failed**

## Prompt seguido?

**Sim, 100%.** Todas as instrucoes da Feature 2 foram seguidas.

### Mudancas em `core/tts.py`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| `AVAILABLE_VOICES` com kokoro(2), edge(6), piper(1) | Sim | Linhas 40-56 |
| `_kokoro_voice` mutavel (default: `KOKORO_VOICE`) | Sim | Linha 64 |
| `_edge_voice` mutavel (default: `TTS_VOICE`) | Sim | Linha 65 |
| `get_available_voices()` | Sim | Linha 194 |
| `get_current_voice()` | Sim | Linhas 198-202 |
| `set_voice()` com validacao | Sim | Linhas 205-220 |
| `generate_tts_kokoro` usa `_kokoro_voice` | Sim | Linha 268 |
| `generate_tts_edge` usa `_edge_voice` | Sim | Linha 314 |

### Mudancas em `static/index.html`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Dropdown `cfgVoice` no config panel | Sim | Linha 445 |
| Engine label `cfgEngineLabel` | Sim | Linha 444 |
| CSS `.config-engine` | Sim | Linha 392 |
| Event listener `change` no dropdown | Sim | Linhas 1042-1047 |
| Envia `{type: 'config', tts_voice: ...}` | Sim | Linha 1045 |

### Mudancas em `server_ws.py`

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Config handler: `data.get("tts_voice")` | Sim | Linhas 388-391 |
| Chama `set_voice(voice)` | Sim | Linha 391 |

## Analise critica

### O que funciona bem

1. **Validacao de voz:** `set_voice()` verifica contra `AVAILABLE_VOICES[engine]` antes de aceitar. Vozes invalidas sao rejeitadas com log.
2. **Piper desabilitado:** dropdown fica `disabled` quando so tem 1 voz (Piper). Correto.
3. **Engine label:** mostra o engine ativo com nome legivel. Bom UX.

### Limitacao conhecida (intencional)

- NAO permite trocar ENGINE via UI (so voz dentro do engine ativo). Isso e regra explicita do prompt.

## Criterios de sucesso — checklist

- [x] Dropdown populado com vozes do engine ativo ao conectar
- [x] Mudar voz → proxima resposta usa voz nova
- [x] Piper → dropdown desabilitado (1 voz)
- [x] Kokoro → Alex e Dora disponiveis
- [x] Edge → 6 vozes disponiveis
- [x] Engine label mostra qual engine
