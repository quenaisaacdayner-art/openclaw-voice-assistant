# S3: Latência End-to-End — PROMPT COMPLETO

> Prompt auto-contido. Leia e execute TUDO.
> Pré-requisito: S1 e S2 executados
> Arquivos a modificar: `core/llm.py`, `core/stt.py`, `server_ws.py`
> Arquivos que NÃO devem ser modificados: `static/index.html`, `core/tts.py`, `core/config.py`

---

## Contexto

O voice assistant tem um pipeline sequencial:

```
[Usuário fala] → [VAD detecta silêncio 800ms] → [STT Whisper ~3-5s] → [LLM TTFT ~2-8s] → [TTS 1ª frase ~0.5-2s] → [Áudio]
```

A latência total desde que o usuário para de falar até ouvir a primeira palavra da resposta é ~7-16 segundos. Não podemos mudar hardware (sem GPU), mas podemos reduzir latência com 4 otimizações no código:

1. **HTTP keep-alive** no LLM — reutilizar conexão TCP (-100-200ms por turno)
2. **Split de frases mais agressivo** — TTS começa antes no streaming (-0.5-2s)
3. **Whisper VAD otimizado** — menos silêncio processado (-100-300ms)
4. **Métricas de latência no log** — medir pra saber se melhorou

**⚠️ NÃO mudar o VAD silence timeout do frontend (800ms). Manter como está.**

---

## OTIMIZAÇÃO 1: HTTP Keep-Alive com requests.Session (`core/llm.py`)

### Problema

Cada chamada ao gateway (`ask_openclaw` e `ask_openclaw_stream`) cria uma conexão TCP nova via `requests.post()`. O handshake TCP + TLS (se HTTPS) custa ~100-200ms. Em conversas com múltiplos turnos, isso se acumula.

### Solução

Usar `requests.Session()` como variável de módulo. A Session reutiliza a conexão HTTP via keep-alive automaticamente.

### Implementação

No topo de `core/llm.py`, após os imports e antes das funções:

```python
# Sessão HTTP persistente — reutiliza conexão TCP (keep-alive)
_session = requests.Session()
```

Modificar `ask_openclaw()` — trocar `requests.post(...)` por `_session.post(...)`:

```python
def ask_openclaw(text, token, history_messages):
    """Envia texto pro gateway OpenClaw. Retorna resposta ou string de erro."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    messages = list(history_messages) + [{"role": "user", "content": text}]
    body = {"model": MODEL, "messages": messages}

    try:
        resp = _session.post(GATEWAY_URL, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.ConnectionError:
        return "❌ OpenClaw não respondeu. Gateway tá rodando?"
    except requests.Timeout:
        return "❌ Timeout — OpenClaw demorou demais."
    except (requests.RequestException, KeyError, IndexError) as e:
        return f"❌ Erro: {e}"
```

Modificar `ask_openclaw_stream()` — trocar `requests.post(...)` por `_session.post(...)`:

```python
def ask_openclaw_stream(text, token, history_messages):
    """Envia texto com streaming SSE. Gera texto acumulado a cada chunk."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    messages = list(history_messages) + [{"role": "user", "content": text}]
    body = {"model": MODEL, "messages": messages, "stream": True}

    resp = _session.post(
        GATEWAY_URL, headers=headers, json=body, timeout=120, stream=True
    )
    resp.raise_for_status()

    full_text = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data_str = line[len("data: "):]
        if data_str.strip() == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
            content = chunk["choices"][0].get("delta", {}).get("content", "")
            if content:
                full_text += content
                yield full_text
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
```

**É exatamente o mesmo código, só troca `requests.post` por `_session.post`.**

### Gateway warmup

No `server_ws.py`, o startup já faz um ping ao gateway. Modificar pra usar a mesma session importada, assim o keep-alive já esquenta na inicialização:

```python
# No bloco de warmup do gateway, trocar requests.get por:
from core.llm import _session as llm_session

_gw_t0 = time.time()
try:
    _gw_base = GATEWAY_URL.rsplit("/chat/completions", 1)[0]
    _gw_resp = llm_session.get(_gw_base, timeout=10, headers={"Authorization": f"Bearer {TOKEN}"})
    _gw_elapsed = time.time() - _gw_t0
    print(f"[WARMUP] Gateway OK em {_gw_elapsed:.1f}s (keep-alive)")
except Exception:
    _gw_elapsed = time.time() - _gw_t0
    print(f"[WARMUP] ⚠️ Gateway não respondeu — conecta na 1ª mensagem")
```

---

## OTIMIZAÇÃO 2: Split de frases mais agressivo (`core/llm.py`)

### Problema

A função `_find_sentence_end()` decide quando mandar texto parcial pro TTS durante o streaming do LLM. Hoje ela espera por:
1. Pontuação forte (`.!?…`) + espaço
2. Ponto-e-vírgula ou dois-pontos + espaço
3. Vírgula + espaço (só se texto > 80 chars)

O problema: LLMs frequentemente geram quebras de linha (`\n`) ANTES de terminar com `.`. Em respostas com listas ou parágrafos, o TTS fica esperando a pontuação forte enquanto já tem uma frase completa terminada em `\n`.

Também: o threshold de 80 chars pra vírgula é conservador demais. 50 chars é suficiente pra uma frase natural (uma frase falada de ~3 segundos tem ~40-60 chars em português).

### Implementação

Substituir a função `_find_sentence_end()` inteira por:

```python
def _find_sentence_end(text):
    """Encontra ponto de split pra TTS em texto parcial do LLM.

    Prioridade:
    1. Pontuação forte (.!?…) seguida de espaço ou fim
    2. Quebra de linha (\n) — LLMs geram \n entre frases/itens de lista
    3. Ponto-e-vírgula ou dois-pontos seguidos de espaço
    4. Vírgula seguida de espaço (só se texto > 50 chars — evita splits muito curtos)

    Retorna posição APÓS o separador (incluindo o espaço). 0 se não encontrou.
    """
    # Prioridade 1: pontuação forte
    m = re.search(r'[.!?…](\s|$)', text)
    if m:
        return m.end()

    # Prioridade 2: quebra de linha
    idx = text.find('\n')
    if idx >= 0:
        # Retorna posição após o \n (e quaisquer \n consecutivos)
        end = idx + 1
        while end < len(text) and text[end] == '\n':
            end += 1
        return end

    # Prioridade 3: ponto-e-vírgula, dois-pontos
    m = re.search(r'[;:](\s|$)', text)
    if m:
        return m.end()

    # Prioridade 4: vírgula (só se texto longo o suficiente)
    if len(text) > 50:
        m = re.search(r',\s', text)
        if m:
            return m.end()

    return 0
```

### Por que funciona

Exemplo de resposta do LLM em streaming:

```
"Existem três formas de fazer isso:\n1. Usando a API diretamente\n2. ..."
```

**Antes:** TTS espera até `...` pra gerar áudio de "Existem três formas de fazer isso: 1. Usando a API diretamente 2. ..."
**Depois:** TTS gera "Existem três formas de fazer isso:" no `\n`, manda pro browser, enquanto LLM continua gerando o item 2.

---

## OTIMIZAÇÃO 3: Whisper VAD otimizado (`core/stt.py`)

### Problema

O Whisper `transcribe()` usa `vad_filter=True` com `min_silence_duration_ms=500`. Isso filtra silêncio interno no áudio antes de transcrever. Mas 500ms é o default — pra áudio curto de voice assistant (2-10 segundos), podemos ser mais agressivos.

### Implementação

Em `core/stt.py`, na função `transcribe_audio()`, modificar o bloco de `transcribe()`:

```python
segments, _ = _get_whisper().transcribe(
    tmp.name,
    language="pt",
    beam_size=5,
    vad_filter=True,
    vad_parameters=dict(
        min_silence_duration_ms=300,      # era 500 — reduzir pra pular silêncios internos mais rápido
        speech_pad_ms=100,                 # padding em torno de fala detectada (default 400 — reduzir)
    ),
)
```

### O que muda

- `min_silence_duration_ms=300`: Whisper ignora silêncios internos menores que 300ms (antes: 500ms). Isso faz o VAD considerar pausas curtas como parte da fala, reduzindo splits desnecessários.
- `speech_pad_ms=100`: Adiciona apenas 100ms de padding antes e depois de cada segmento de fala detectado (antes: 400ms default). Menos áudio de silêncio pro Whisper processar.

**Resultado:** Whisper processa menos frames de silêncio = transcrição ~100-300ms mais rápida em áudios com pausas.

**⚠️ NÃO confundir com o VAD do frontend (speech_end 800ms).** Isso é o VAD INTERNO do Whisper que filtra silêncio dentro do arquivo de áudio que já foi gravado. São coisas diferentes.

---

## OTIMIZAÇÃO 4: Métricas de latência detalhadas (`server_ws.py`)

### Problema

Hoje o log mostra:
```
[STT] Transcrição: "..." (3.2s)
[LLM] TTFT: 4.1s
[TTS] 1ª frase: "..." (0.8s)
[TOTAL] Fala→Resposta: 8.1s
```

Falta:
- Tempo total até o usuário OUVIR a 1ª palavra (STT + TTFT + TTS 1ª frase)
- Comparação entre turnos (melhorando ou piorando?)
- Métricas do text_input (sem STT)

### Implementação

Modificar `_llm_and_tts()` em `server_ws.py`. Adicionar uma métrica **Time-to-First-Audio (TTFA)** — tempo desde o início do processamento até o primeiro `ws.send_bytes()`.

Após a primeira vez que `await ws.send_bytes(audio_bytes)` é chamado (tanto no loop de streaming quanto no fallback do resto), imprimir:

```python
if t_tts_first is None:
    t_tts_first = time.time()
    print(f"[TTS] 1ª frase: \"{sentence[:40]}{'...' if len(sentence) > 40 else ''}\" ({t_tts_first - t_tts_s:.1f}s)")
```

**Esse log já existe.** O que falta é o TTFA. Adicionar no `process_speech()`, APÓS `_llm_and_tts()` retornar:

Modificar `process_speech()` — adicionar tracking de TTFA. A forma mais limpa é passar `t0` (tempo de início) pra `_llm_and_tts()` e retornar o timestamp do primeiro áudio.

**Abordagem:** Modificar `_llm_and_tts()` pra aceitar `t_start` opcional e retornar métricas:

```python
async def _llm_and_tts(user_text, t_start=None):
    """LLM streaming + TTS por frase. Retorna dict com métricas."""
    # ... (código existente inalterado) ...
    
    # No final da função, antes do return implícito:
    metrics = {
        "ttft": t_ttft - t_llm_start if t_ttft else None,
        "tts_first": t_tts_first,
        "tts_count": tts_count,
        "response_len": len(full_response),
    }
    
    if t_start and t_tts_first:
        ttfa = t_tts_first - t_start
        print(f"[PERF] ⚡ Time-to-First-Audio: {ttfa:.1f}s")
    
    return metrics
```

Modificar `process_speech()` — passar `t0`:
```python
# Trocar:
await _llm_and_tts(transcript)
# Por:
metrics = await _llm_and_tts(transcript, t_start=t0)
```

Modificar `process_text()` — passar `t0`:
```python
# Trocar:
await _llm_and_tts(user_text)
# Por:
metrics = await _llm_and_tts(user_text, t_start=t0)
```

### Log esperado após as otimizações:

```
[REQ] Nova mensagem recebida
[STT] Transcrição: "qual a previsão do tempo?" (2.8s)
[LLM] TTFT: 3.2s
[TTS] 1ª frase: "A previsão para hoje é de" (0.6s)
[PERF] ⚡ Time-to-First-Audio: 6.6s
[LLM] Resposta completa: 245 chars em 5.1s
[TTS] Total: 3 frases
[TOTAL] Fala→Resposta: 7.8s
```

Agora dá pra comparar TTFA entre turnos e saber exatamente onde o tempo está.

### Enviar métricas pro frontend

Após `_llm_and_tts()` retornar, enviar mensagem com métricas pra que o frontend possa (opcionalmente) mostrar:

```python
if metrics:
    perf_msg = {"type": "perf"}
    if metrics.get("ttft"):
        perf_msg["ttft"] = round(metrics["ttft"], 1)
    if t_start and metrics.get("tts_first"):
        perf_msg["ttfa"] = round(metrics["tts_first"] - t_start, 1)
    await send_json_msg(perf_msg)
```

No frontend, logar no console (sem mostrar na UI por enquanto):
```javascript
if (data.type === 'perf') {
    console.log(`[PERF] TTFT: ${data.ttft}s | TTFA: ${data.ttfa}s`);
    return;
}
```

---

## Resumo de mudanças por arquivo

| Arquivo | O que muda |
|---------|------------|
| `core/llm.py` | `_session = requests.Session()` + trocar `requests.post` por `_session.post` + nova `_find_sentence_end()` |
| `core/stt.py` | VAD params: `min_silence_duration_ms=300`, `speech_pad_ms=100` |
| `server_ws.py` | Gateway warmup via `_session` + `_llm_and_tts()` retorna métricas + TTFA log + perf msg pro frontend |
| `static/index.html` | Handler `data.type === 'perf'` (console.log, 3 linhas) |

---

## O que NÃO fazer

- **NÃO** mudar o VAD silence timeout do frontend (800ms). Manter como está.
- **NÃO** mudar a lógica de `speech_end` no frontend
- **NÃO** mudar o modelo Whisper (isso é S2)
- **NÃO** mudar TTS engine, vozes, ou velocidade (isso é S2)
- **NÃO** mudar a UI, config panel, ou esfera (isso é S1)
- **NÃO** adicionar threading ou multiprocessing novo
- **NÃO** mudar `core/tts.py` ou `core/config.py`
- **NÃO** mudar `voice_assistant_app.py` ou `voice_assistant_cli.py`
- **NÃO** tentar paralelizar STT + LLM (são sequenciais por natureza — precisa do texto antes de mandar pro LLM)

---

## Critérios de sucesso

### Keep-alive:
- [ ] `core/llm.py` usa `_session.post()` em vez de `requests.post()`
- [ ] Gateway warmup usa a mesma session
- [ ] 2ª mensagem em diante não reabre conexão TCP (verificar: tempo de TTFT da 1ª msg vs 2ª — 2ª deve ser ~100-200ms mais rápida)

### Split de frases:
- [ ] Resposta com `\n` faz TTS antes do ponto final
- [ ] Resposta com lista (1. ... 2. ...) gera TTS por item
- [ ] Frases curtas com vírgula (>50 chars) fazem split
- [ ] Frases com pontuação forte continuam funcionando igual

### Whisper VAD:
- [ ] `min_silence_duration_ms=300` no transcribe
- [ ] `speech_pad_ms=100` no transcribe
- [ ] Transcrição continua precisa (sem cortar palavras)

### Métricas:
- [ ] Log mostra `[PERF] ⚡ Time-to-First-Audio: X.Xs`
- [ ] Frontend console mostra `[PERF] TTFT: ... | TTFA: ...`
- [ ] `_llm_and_tts()` retorna dict de métricas

### Geral:
- [ ] `python -m pytest tests/ -v` — todos os testes passam
- [ ] Conversa de 3+ turnos funciona normalmente
- [ ] Barge-in (interrupt) continua funcionando

---

## Teste manual

1. Iniciar server → falar algo → verificar log com TTFA
2. Falar segunda vez → comparar TTFA (deve ser ~100-200ms menor que a 1ª)
3. Perguntar algo que gere lista → verificar que TTS começa antes do fim da lista
4. Abrir DevTools → Console → verificar `[PERF]` com TTFT e TTFA
5. Falar com pausa curta (~500ms) no meio da frase → verificar que Whisper NÃO cortou a frase (VAD ok)
6. Testar barge-in → falar enquanto IA responde → deve interromper normalmente
