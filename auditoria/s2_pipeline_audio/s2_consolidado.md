# Auditoria Consolidada — S2: Pipeline de Audio

> Executada: 23/03/2026
> Prompt: `prompts/s2_pipeline_audio/s2_completo.md`
> Commits: `aa0b853` (feat), `0b99be5` (fix)
> Testes: 227 passed, 18 skipped, 0 failed

## Resumo das 3 Features

| Feature | Descricao | Status |
|---------|-----------|--------|
| S2-A | Whisper small + Banner TTS + server_info | Completa |
| S2-B | Seletor de vozes TTS | Completa |
| S2-C | Slider de velocidade TTS | Completa |

## Arquivos modificados

| Arquivo | Tipo de mudanca |
|---------|----------------|
| `core/config.py` | Default Whisper: "tiny" → "small" |
| `core/stt.py` | `get_current_model()`, fix `init_stt()` log |
| `core/tts.py` | AVAILABLE_VOICES, voice/speed state, getters/setters, get_engine(), get_tts_info() |
| `server_ws.py` | Banner, server_info, config handler (voice + speed) |
| `static/index.html` | Voice dropdown, speed slider, server_info handler, event listeners |
| `tests/test_cli.py` | Default Whisper assertion atualizada |

## Regras "NAO fazer" — todas respeitadas

| Regra | Respeitada? |
|-------|-------------|
| NAO instalar PyTorch/distil-whisper | Sim |
| NAO mudar fallback chain TTS (kokoro → piper → edge) | Sim |
| NAO mudar `language="pt"` no transcribe | Sim |
| NAO permitir trocar ENGINE via UI | Sim |
| NAO mexer em `voice_assistant_app.py` / `cli.py` | Sim |
| NAO duplicar funcoes (S1 ja criou `set_whisper_model`) | Sim |
| NAO mexer em streaming/barge-in/VAD/history | Sim |

## Bug detectado e corrigido

### Import de variaveis privadas no top-level (commit `0b99be5`)

**Problema:** `server_ws.py` fazia `from core.tts import _tts_engine, kokoro_instance, piper_voice`. Isso capturava os valores no momento do import (antes de `init_tts()` rodar), resultando em:
- `_tts_engine` = valor pre-fallback (ex: "kokoro" quando Kokoro nao esta instalado)
- `kokoro_instance` = `None` (sempre)
- `piper_voice` = `None` (sempre)

**Impacto:** Banner no startup nunca mostraria Kokoro ou Piper corretamente. `server_info.tts_engine` enviaria o engine errado pro frontend.

**Correcao:** Criados `get_engine()` e `get_tts_info()` em `tts.py` como funcoes getter que leem o estado atual do modulo. Eliminados imports de variaveis privadas mutaveis.

**Licao:** Nunca importar variaveis mutaveis de modulo via `from module import var` quando o valor pode mudar entre import e uso. Sempre usar funcoes getter ou acessar via `module.var`.

## Analise critica — o que esta BEM

1. **Separacao de responsabilidades:** Todo estado mutavel de TTS vive em `tts.py`, exposto via getters. `server_ws.py` nao guarda copias locais.
2. **Validacao de voz:** `set_voice()` verifica contra `AVAILABLE_VOICES[engine]` — vozes invalidas sao rejeitadas.
3. **Clamp de velocidade:** `set_speed()` faz `max(0.5, min(2.0, ...))` — o backend nao confia no frontend.
4. **server_info na reconexao:** Toda conexao WS recebe o estado atual, garantindo que dropdown e slider estejam sincronizados.
5. **Fallback chain intacta:** Kokoro → Piper → Edge nao foi tocado.

## Analise critica — pontos de atencao

1. **`_tts_speed` nao e thread-safe.** Se dois WS clients mudarem velocidade simultaneamente, ha race condition. Na pratica, e single-user, entao e aceitavel.

2. **Velocidade e global, nao per-connection.** Se dois clients estiverem conectados, mudar velocidade num afeta o outro. Idem pra voz. Aceitavel pro caso de uso (assistente pessoal).

3. **Piper nao suporta velocidade.** O `<small>` no HTML avisa, mas nao ha feedback visual (ex: desabilitar slider quando engine=piper). Melhoria possivel.

4. **`import sys` nao usado em `tts.py`.** Linha 4 — import orfao. Ja existia antes do S2, nao introduzido por nos.

## Mudancas pos-S2 (S3 Latencia)

Apos o S2, foram feitas otimizacoes de latencia (commit `cae1753`):
- HTTP keep-alive via `requests.Session` em `core/llm.py`
- Split agressivo de frases em `core/llm.py`
- Whisper VAD: `min_silence_duration_ms` 500→300, `speech_pad_ms` 400→100 em `core/stt.py`
- Metricas TTFA em `server_ws.py` (`_llm_and_tts` retorna metrics dict)
- Handler `perf` no frontend (linha 628-629 de `index.html`)

Essas mudancas sao compativeis e nao conflitam com o S2.

## Conclusao

S2 foi executado com sucesso. O unico erro real foi o bug de import de variaveis privadas, detectado na auditoria e corrigido imediatamente no commit seguinte. Nenhum criterio de sucesso ficou pendente. 227 testes passando sem regressao.
