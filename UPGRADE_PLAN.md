# UPGRADE_PLAN.md

> Atualizado: 18/03/2026
> Status: PENDENTE — executar fase por fase com commit entre cada uma
> Testes: 246 existentes são o guardrail — rodar após cada fase

## Contexto

Temos 3 scripts (CLI 305L, Web 661L, VPS 558L) com ~400 linhas duplicadas.
O código funciona, mas toda melhoria precisa ser feita 2-3x.
Antes de adicionar features, unificar a base. Depois, melhorar.

### Cobertura de testes atual (246 testes)

| Arquivo | Testes | Cobre |
|---------|--------|-------|
| `test_cli.py` | 32 | CLI: defaults, mic, token, transcribe, ask_openclaw, speak, record, play |
| `test_cli_extended.py` | 22 | CLI: mic keywords, API errors, speak_piper/edge, play_audio Linux, token edge cases |
| `test_web.py` | 23 | Web: config, PyAudio mic, Piper/Edge TTS, ContinuousListener, respond_text/audio |
| `test_web_extended.py` | 25 | Web: _get_whisper lazy loading, generate_tts wrapper, toggle/poll, streaming fallbacks |
| `test_vps.py` | 22 | VPS: config, BrowserContinuousListener, TTS, toggle, stream chunks |
| `test_vps_extended.py` | 28 | VPS: handle_stop_recording, respond_text/audio, _transcribe_buffer, ask_openclaw errors |
| `test_shared_logic.py` | 17 | SSE parser, _find_sentence_end, build_api_history, transcribe_audio |
| `test_code_duplication.py` | 17 | Inventário: quais funções existem em quais arquivos, deps, model |
| `test_bugs_documented.py` | 30 | Testes que PASSAM com os bugs atuais — servem de alarme quando corrigidos |

---

## FASE 1: Unificação — 3 scripts → core compartilhado (~4-6h)

**Por quê:** sem isso, todo bug fix e feature nova precisa ser replicado em 3 arquivos.

**Por que ~4-6h e não ~2h:** os 246 testes importam `voice_assistant`, `voice_assistant_web`, `voice_assistant_vps` diretamente — todos os imports e mocks precisam ser adaptados. Além disso, web e VPS têm diferenças sutis no streaming (web faz `yield` com 3 outputs, VPS com 2) e o `handle_stream_chunk` do VPS acopla buffer no `continuous_listener` — esse acoplamento precisa ser desfeito.

### Estrutura alvo

```
core/
  __init__.py
  config.py      — load_token(), gateway URL, model, constantes
  stt.py         — _get_whisper(), transcribe_audio()
  tts.py         — generate_tts() com Piper + Edge + fallback automático
  llm.py         — ask_openclaw(), ask_openclaw_stream(), _find_sentence_end()
  history.py     — build_api_history(), MAX_HISTORY

voice_assistant_cli.py   — Terminal (importa core/*)
voice_assistant_app.py   — Gradio unificado (detecta local vs VPS automaticamente)
```

### O que o app unificado detecta sozinho

| Detecção | Como | Resultado |
|----------|------|-----------|
| Mic local disponível? | Tenta importar PyAudio | Sim → modo local (RealtimeSTT) |
| Mic local disponível? | PyAudio falha | Não → modo browser (Gradio streaming + VAD) |
| Qual gateway? | `OPENCLAW_GATEWAY_URL` env var | Padrão: localhost:18789 |
| Piper disponível? | Tenta importar + checa modelo | Sim → Piper, Não → Edge TTS |

### Decisões de unificação que a Fase 1 resolve automaticamente

Estas inconsistências entre scripts deixam de existir quando há uma só implementação:

| Inconsistência atual | Resolve na unificação |
|---|---|
| CLI `ask_openclaw(text, token, history)` vs Web/VPS `ask_openclaw(text, history_messages)` | Uma assinatura só no `core/llm.py` |
| CLI retorna `None` em erro vs Web/VPS retornam string `"❌..."` | Um padrão de erro só |
| `ask_openclaw_stream` propaga exceções HTTP sem catch interno | Um handler só com tratamento consistente |

### Regra

- Zero duplicação de lógica
- Cada função existe em UM lugar
- Scripts finais só contêm: imports do core + UI + main()

### Critério de sucesso

- [ ] `python voice_assistant_app.py` funciona no laptop (mic local, gateway local)
- [ ] `python voice_assistant_app.py` funciona na VPS (mic browser, gateway VPS)
- [ ] `OPENCLAW_GATEWAY_URL=... python voice_assistant_app.py` conecta em gateway remoto
- [ ] `python voice_assistant_cli.py` funciona igual ao CLI atual
- [ ] 246 testes passam (adaptar imports)

---

## FASE 2: Corrigir bugs conhecidos (~1h)

8 bugs/quirks documentados em `test_bugs_documented.py`. Corrigir no core unificado = corrigido em tudo.

### Bugs que precisam de fix manual (não resolvidos pela unificação)

| Bug | Onde | Fix |
|-----|------|-----|
| `PortAudioError.__str__()` retorna int → crash no print | `cli.py` / `record_audio` | `str(e)` no f-string |
| `MIN_SPEECH_CHUNKS` conta silêncio no buffer | `BrowserContinuousListener` | Contador separado `speech_chunk_count` |
| `build_api_history` filtra `[🎤` → voz não vai pro contexto | `core/history.py` | Filtrar o prefixo `[🎤 Voz]: `, manter o conteúdo |
| `_find_sentence_end` não detecta pontuação no fim da string | `core/llm.py` | Regex `[.!?…](\s\|$)` em vez de `[.!?…]\s` |
| `generate_tts` só filtra `"❌"` no início do texto | `core/tts.py` | Verificar se `"❌"` aparece em qualquer posição, ou manter e documentar como intencional |

### Bugs que a Fase 1 já resolve (pela unificação)

| Bug | Por que resolve |
|-----|----------------|
| `MAX_HISTORY` inconsistente (local var CLI vs module const Web/VPS) | Constante única no `core/history.py` |
| `ask_openclaw` assinaturas diferentes entre scripts | Uma implementação só no `core/llm.py` |
| CLI retorna `None` em erro vs Web/VPS retornam string `"❌..."` | Um padrão de retorno só |

### Critério de sucesso

- [ ] 246 testes adaptados pra refletir behavior correto (não mais "documenta bug")
- [ ] `test_bugs_documented.py` reescrito: testes agora verificam comportamento CORRETO
- [ ] Todos passam

---

## FASE 3: Limpeza do repo (~30min)

| Item | Ação |
|------|------|
| `models/pt_BR-faber-medium.onnx` (60MB no git) | Mover pra download automático no primeiro uso + `.gitignore` |
| `teste_tts.py` | Mover pra `scripts/` ou remover |
| `requirements.txt` | Separar: `requirements.txt` (base) + `requirements-local.txt` (PyAudio, RealtimeSTT, piper) |
| `.gitignore` | Limpar entradas com espaços quebrados |
| Scripts antigos | Remover `voice_assistant.py`, `voice_assistant_web.py`, `voice_assistant_vps.py` após unificação |

### Critério de sucesso

- [ ] Repo clonado < 5MB (sem modelo de 60MB)
- [ ] `pip install -r requirements.txt` funciona em qualquer ambiente
- [ ] Modelo Piper baixa automaticamente no primeiro uso

---

## FASE 4: Interface melhorada (~1h)

| Melhoria | Impacto | Complexidade |
|----------|---------|--------------|
| Indicadores visuais (🔴 gravando, 🧠 pensando, 🔊 falando) | Alto — UX | Baixa |
| Painel de config no browser (gateway, mic, TTS, modelo Whisper) | Médio — usabilidade | Média |
| Transcrição parcial em tempo real (ver palavras enquanto fala) | Alto — UX | Média |
| Theme escuro por padrão | Baixo — estética | Trivial |
| Mobile-friendly (layout responsivo) | Médio — acessibilidade | Baixa |

### Critério de sucesso

- [ ] Usuário sabe visualmente em qual estado o assistente está (escutando/processando/falando)
- [ ] Pode mudar gateway URL sem reiniciar o script

---

## FASE 5: Latência (~1h)

| Melhoria | Ganho esperado | Como |
|----------|---------------|------|
| Buffer duplo de TTS | Elimina gap entre frases | Gera frase N+1 enquanto frase N toca |
| Whisper `tiny` como opção rápida | STT 3x mais rápido (qualidade menor) | Selecionável na UI |
| TTS streaming (chunk por chunk) | Voz começa em ~1s vs ~3s | Edge TTS já suporta streaming |
| Pré-carregamento do Whisper | Elimina delay na 1ª transcrição | Carregar no startup (já é lazy) |

### Critério de sucesso

- [ ] Primeira palavra falada em < 3s após fim da pergunta (hoje: 4-10s)
- [ ] Sem gap audível entre frases do TTS

---

## FASE 6: Voz melhor — Kokoro TTS (~30min)

| Engine | Qualidade | Latência | Custo | Local? |
|--------|-----------|----------|-------|--------|
| Edge TTS (atual) | 6/10 | ~1-2s (rede) | Grátis | ❌ Cloud |
| Piper (atual) | 5/10 | ~0.5s | Grátis | ✅ Local |
| Kokoro | 8/10 | ~1s | Grátis | ✅ Local |

Testar Kokoro como TTS padrão. Se PT-BR não for bom → manter Edge.

### Critério de sucesso

- [ ] Voz mais natural que Edge TTS em comparação cega
- [ ] Funciona 100% offline

---

## FASE 7: Open Source / DX (~1h)

| Item | Ação |
|------|------|
| README | Reescrever: instalação, modos de uso, screenshots, GIF de demo |
| `.env.example` | Todas as variáveis documentadas |
| Docker | `Dockerfile` + `docker-compose.yml` (rodar em 1 comando) |
| CI | GitHub Actions rodando os testes em push/PR |
| CONTRIBUTING.md | Como contribuir, rodar testes, estrutura do código |
| Issues | Criar issues no GitHub pras fases futuras |

### Critério de sucesso

- [ ] Alguém clona, roda `pip install -r requirements.txt && python voice_assistant_app.py` e funciona
- [ ] README tem GIF mostrando o assistente em ação
- [ ] CI verde no GitHub

---

## NICE-TO-HAVE: Tunnel SSH automático

> Rebaixado de fase obrigatória. O custo (subprocess management, signal handlers, cross-platform) é desproporcional ao valor. Um `scripts/connect.sh` de 5 linhas resolve 80%.

```bash
# scripts/connect.sh
#!/bin/bash
ssh -N -L ${1:-19789}:127.0.0.1:${1:-19789} ${2:-root@31.97.171.12} &
SSH_PID=$!
trap "kill $SSH_PID 2>/dev/null" EXIT
python voice_assistant_app.py --gateway http://127.0.0.1:${1:-19789}/v1/chat/completions
```

Se depois houver demanda, promover a fase completa com `--gateway ssh://user@host:port`.

---

## Ordem de execução

```
FASE 1 (Unificação)  ← base pra tudo [~4-6h]
  ↓
FASE 2 (Bugs)        ← agora é 1 lugar, não 3 [~1h]
  ↓
FASE 3 (Limpeza)     ← repo profissional [~30min]
  ↓
FASE 4-6 (Features)  ← ordem flexível, cada uma independente
  ↓
FASE 7 (Open Source)  ← polimento final
```

## Regra geral

- Commit após cada fase completa
- Testes rodam após cada fase (246 testes = guardrail)
- Se uma fase trava por 30+ min → parar, commitar o que tem, seguir pra próxima
- Claude Code executa, Dayner revisa
