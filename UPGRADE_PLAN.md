# UPGRADE_PLAN.md

> Atualizado: 18/03/2026
> Status: PENDENTE — executar fase por fase com commit entre cada uma
> Testes: 129 existentes são o guardrail — rodar após cada fase

## Contexto

Temos 3 scripts (CLI 305L, Web 661L, VPS 558L) com ~400 linhas duplicadas.
O código funciona, mas toda melhoria precisa ser feita 2-3x.
Antes de adicionar features, unificar a base. Depois, melhorar.

---

## FASE 1: Unificação — 3 scripts → core compartilhado (~2h)

**Por quê:** sem isso, todo bug fix e feature nova precisa ser replicado em 3 arquivos.

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

### Regra

- Zero duplicação de lógica
- Cada função existe em UM lugar
- Scripts finais só contêm: imports do core + UI + main()

### Critério de sucesso

- [ ] `python voice_assistant_app.py` funciona no laptop (mic local, gateway local)
- [ ] `python voice_assistant_app.py` funciona na VPS (mic browser, gateway VPS)
- [ ] `OPENCLAW_GATEWAY_URL=... python voice_assistant_app.py` conecta em gateway remoto
- [ ] `python voice_assistant_cli.py` funciona igual ao CLI atual
- [ ] 129 testes passam (adaptar imports)

---

## FASE 2: Corrigir bugs conhecidos (~30min)

4 bugs documentados nos testes. Corrigir no core unificado = corrigido em tudo.

| Bug | Onde | Fix |
|-----|------|-----|
| `PortAudioError.__str__()` retorna int → crash no print | `cli.py` / `record_audio` | `str(e)` no f-string |
| `MIN_SPEECH_CHUNKS` conta silêncio no buffer | `BrowserContinuousListener` | Contador separado `speech_chunk_count` |
| `build_api_history` filtra `[🎤` → voz não vai pro contexto | `history.py` | Filtrar o prefixo, manter o conteúdo |
| `MAX_HISTORY` inconsistente (local vs módulo) | `history.py` | Constante no core |

### Critério de sucesso

- [ ] 129 testes adaptados pra refletir behavior correto (não mais "documenta bug")
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

## FASE 4: Tunnel SSH automático (~1h)

**Por quê:** hoje precisa abrir terminal separado pra tunnel. Quem clona o repo não sabe fazer isso.

### Implementação

```bash
# Hoje (2 terminais):
ssh -N -L 19792:127.0.0.1:19792 root@31.97.171.12   # terminal 1
python voice_assistant_vps.py                          # terminal 2

# Depois (1 comando):
python voice_assistant_app.py --gateway ssh://root@31.97.171.12:19789
```

O script:
1. Detecta `ssh://` no gateway URL
2. Abre tunnel SSH em subprocess (background)
3. Conecta no gateway via localhost
4. Fecha tunnel quando o script encerra

### Critério de sucesso

- [ ] `--gateway ssh://user@host:port` abre tunnel automaticamente
- [ ] Ctrl+C mata o tunnel junto com o script
- [ ] Sem `ssh://` funciona igual (conexão direta)

---

## FASE 5: Interface melhorada (~1h)

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

## FASE 6: Latência (~1h)

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

## FASE 7: Voz melhor — Kokoro TTS (~30min)

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

## FASE 8: Open Source / DX (~1h)

| Item | Ação |
|------|------|
| README | Reescrever: instalação, 4 modos de uso, screenshots, GIF de demo |
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

## Ordem de execução

```
FASE 1 (Unificação) ← base pra tudo
  ↓
FASE 2 (Bugs) ← agora é 1 lugar, não 3
  ↓
FASE 3 (Limpeza) ← repo profissional
  ↓
FASE 4-7 (Features) ← ordem flexível, cada uma independente
  ↓
FASE 8 (Open Source) ← polimento final
```

## Regra geral

- Commit após cada fase completa
- Testes rodam após cada fase
- Se uma fase trava por 30+ min → parar, commitar o que tem, seguir pra próxima
- Claude Code executa, Dayner revisa
