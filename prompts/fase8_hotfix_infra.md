# Fase 8: Hotfix de Infra — Pre-warm + Logging de Latência

> Leia CLAUDE.md, TESTING_RESULTS.md e TESTING_LOG.md antes de começar.
> Esses arquivos contêm o contexto completo dos testes dos 3 cenários.

## Contexto

Testamos 3 cenários de deploy (tudo local, tudo VPS, local→VPS remoto). **Zero erros de código** — tudo funciona. Mas dois problemas de experiência:

1. **1ª resposta demora ~30-40s** — cold start de Whisper, TTS e conexão HTTP
2. **Sem métricas de latência** — não sabemos quanto cada fase demora

## Objetivo

Duas mudanças cirúrgicas. NÃO mudar lógica de conversação, NÃO mudar interface, NÃO mudar config.

---

## Tarefa 1: Pre-warm no startup

O server (`server_ws.py`) precisa aquecer 3 componentes **antes** de aceitar conexões WebSocket:

### 1A. Whisper (STT)
- Em `core/stt.py`: o modelo Whisper é carregado com lazy loading (na 1ª chamada de `transcribe_audio`)
- **Mudar:** carregar o modelo no `import` ou expor uma função `init_stt()` que carrega o modelo
- Em `server_ws.py`: chamar `init_stt()` no startup (similar ao `init_tts()` que já existe)
- **Validação:** print `"[WARMUP] Whisper ({model_size}) carregado em {tempo}s"`

### 1B. TTS
- `init_tts()` já é chamado no startup — verificar se ele realmente carrega o engine
- Se Edge TTS: fazer uma geração dummy silenciosa (texto curto tipo "ok") pra abrir a conexão WebSocket com o servidor Microsoft
- **Validação:** print `"[WARMUP] TTS ({engine}) pronto em {tempo}s"`

### 1C. Gateway (conexão HTTP)
- Fazer um health-check pro gateway no startup: GET ou POST simples pra `GATEWAY_URL` (ou a URL base sem `/chat/completions`)
- Se falhar, apenas avisar (não bloquear startup): `"[WARMUP] ⚠️ Gateway não respondeu — vai conectar na 1ª mensagem"`
- Se funcionar: `"[WARMUP] Gateway OK em {tempo}s"`
- **Importar** `GATEWAY_URL` de `core/config.py` e `load_token` pra autenticar

### Onde colocar no server_ws.py

Depois do `TOKEN = load_token()` e `init_tts()`, adicionar bloco de warmup:

```python
# — Warmup —
init_stt()       # Carrega Whisper
# TTS warmup (se Edge, gerar dummy)
# Gateway ping
```

Print final: `"[WARMUP] Tudo pronto em {tempo_total}s"`

---

## Tarefa 2: Logging de latência por fase

Em `server_ws.py`, na função `process_speech()` (ou equivalente que processa cada mensagem), adicionar timestamps pra medir cada fase:

### Métricas a logar (print no terminal)

```
[REQ] Nova mensagem recebida
[STT] Transcrição: "{texto}" ({tempo}s)
[LLM] TTFT: {tempo}s (tempo até 1º token)
[LLM] Resposta completa: {total_tokens} chars em {tempo}s
[TTS] 1ª frase: "{frase}" ({tempo}s)
[TTS] Total: {n} frases em {tempo}s
[TOTAL] Fala→Resposta: {tempo_total}s
```

### Como implementar

1. `t0 = time.time()` no início de `process_speech()`
2. `t_stt = time.time()` após `transcribe_audio()` — print `[STT]`
3. No loop de streaming LLM: capturar tempo do 1º chunk (`t_ttft`) — print `[LLM] TTFT`
4. Após streaming completo: print `[LLM] Resposta completa`
5. No TTS: capturar tempo da 1ª frase e do total
6. No final: `time.time() - t0` — print `[TOTAL]`

### Formato do print

```python
print(f"[STT] Transcrição: \"{transcript[:50]}...\" ({t_stt - t0:.1f}s)")
```

Usar `import time` no topo do arquivo (se não tiver).

---

## Restrições

- **NÃO alterar:** lógica de conversação, barge-in, streaming, interface HTML, config.py, llm.py
- **NÃO adicionar:** dependências novas, arquivos novos (exceto auditoria/fase8.md)
- **NÃO mudar:** modelo LLM, parâmetros de VAD, formato de áudio
- **Prints apenas** — sem logging framework, sem arquivo de log, sem dependência extra
- Manter compatibilidade com os 3 cenários (local, VPS, local→VPS)

## Testes

Depois de implementar:
1. `pytest` — todos os testes existentes devem passar (215 passed, 0 failed)
2. Verificar que os prints de warmup aparecem no startup
3. Verificar que os prints de latência aparecem em cada mensagem

## Entrega

- Criar `auditoria/fase8.md` com diff e resultados dos testes
- Formato igual às fases anteriores (ver `auditoria/fase7.md` como referência)
