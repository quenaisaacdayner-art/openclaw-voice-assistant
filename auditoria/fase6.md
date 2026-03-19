# Auditoria — Fase 6: Kokoro TTS

> Executada: 2026-03-19 ~00:45 BRT
> Auditada por: OpenClaw Principal (Opus 4)
> Commit: 4040bb4

## Resultado dos Testes

- **219 passed, 14 skipped** OU **215 passed, 18 skipped** — FLAKY
- Total: sempre 233 collected
- **Descoberta:** os testes oscilam entre 219/14 e 215/18 por causa de `_detect_mode()` em `voice_assistant_app.py` — usa thread com timeout=5s pra detectar PyAudio, resultado varia entre execuções
- **Isso explica TODAS as "discrepâncias" das fases anteriores** — o Claude Code NÃO estava errando os números. Eu é que rodava em momentos diferentes e pegava resultados diferentes
- Claude Code dessa vez reconheceu: "diferença é por detecção PyAudio" ✅

### Correção das auditorias anteriores
- Fases 1-5: eu acusei o Claude Code de reportar números errados (sempre -4/+4). Na verdade os testes são não-determinísticos. O padrão -4/+4 é real mas não é erro do Claude Code
- Os hashes ainda estavam errados (verificado independente) — esse erro permanece

## Verificação por Task

### ✅ Task 1: Pesquisa Kokoro TTS
- kokoro-onnx suporta PT-BR (lang "pt-br")
- Vozes: `pm_alex` (masculina, padrão), outras disponíveis
- Modelos: ~300MB (kokoro-v1.0.onnx + voices-v1.0.bin)
- **Veredicto:** ✅ Pesquisa correta

### ✅ Task 2: Integração Kokoro
- **Import condicional:** `from kokoro_onnx import Kokoro` com try/except ✅
- **`init_kokoro()`:** download automático + carregamento + fallback pra Piper ✅
- **`init_tts()`:** nova função que gerencia cadeia completa kokoro→piper→edge ✅
- **`generate_tts_kokoro()`:** usa `kokoro_instance.create()` + `soundfile.write()` → WAV ✅
- **`_download_file()`:** helper extraído (reutilizado por Piper e Kokoro) ✅
- **Fallback chain no `generate_tts()`:** kokoro→piper→edge com fallback em runtime ✅
- **Config:** `TTS_ENGINE=kokoro` + `KOKORO_VOICE=pm_alex` via env vars ✅
- **Entry points:** `voice_assistant_app.py` e `voice_assistant_cli.py` agora usam `init_tts()` em vez de `init_piper()` ✅
- **Deps:** `kokoro-onnx` e `soundfile` em `requirements-local.txt` ✅

### Análise do fallback chain

```
generate_tts(text):
  if kokoro configurado e kokoro_instance existe:
    → tenta kokoro
    → se falha: tenta piper
    → se falha: tenta edge
  elif piper configurado e piper_voice existe:
    → tenta piper
    → se falha: tenta edge
  else:
    → edge
```

**Correto.** Três níveis de fallback, nunca fica sem TTS (Edge é online e não requer modelo local).

### Testes adaptados
- Todos os patches `init_piper` → `init_tts` ✅
- `test_code_duplication.py` agora verifica `generate_tts_kokoro`, `init_kokoro`, `init_tts` ✅
- `test_web.py` TTS_ENGINE aceita "kokoro" ✅

## Problemas Encontrados

### 🟢 Nenhum problema no código
- Implementação limpa — seguiu o padrão dos outros engines
- Import condicional correto
- Download automático com progresso
- Fallback chain sólida

### 🟡 Modelos grandes (~300MB)
- Kokoro modelo: ~300MB, Piper: ~60MB
- Ambos baixados automaticamente no primeiro uso
- .gitignore já cobre `models/*.onnx` ✅

### 🟡 soundfile como dependência nova
- Usado por `generate_tts_kokoro()` — `sf.write(tmp.name, samples, sample_rate)`
- Piper usa `wave` (stdlib), Edge usa `edge_tts.Communicate.save()`
- soundfile requer libsndfile — pode dar problema em ambientes mínimos
- **Impacto:** baixo (requirements-local.txt, não base)

## Diff Total Real

```
16 files changed, 457 insertions(+), 128 deletions(-)
```
(inclui minhas auditorias reescritas das fases 3-5)

## Veredito

**✅ FASE 6 APROVADA**
- Kokoro TTS integrado corretamente com fallback chain completa
- Padrão consistente com engines existentes
- Testes adaptados
- Nenhum bug funcional
- **🔄 RETIFICAÇÃO:** números de testes nas fases 1-5 — Claude Code estava certo, testes são flaky por `_detect_mode()`
