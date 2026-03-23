# ROADMAP.md — Guia de Evolução do Voice Assistant

> Última atualização: 22/03/2026
> Autor: OpenClaw Principal (planejamento) + Dayner (decisões)
> Executor: Claude Code (via prompts em `prompts/`)
> Contexto: Projeto funcional nos 3 cenários. Agora: mapear e priorizar melhorias.

---

## Contexto do Projeto

### O que é
Interface de conversação **Speech-to-Speech (S2S)** conectada ao OpenClaw Gateway. O usuário fala → app transcreve → envia pro OpenClaw → recebe resposta → converte em voz → reproduz.

### Estado atual (22/03/2026)
- **Código unificado:** `core/` (config, stt, tts, llm, history) compartilhado entre todos os entrypoints
- **2 interfaces:** `server_ws.py` (WebSocket S2S — principal) + `voice_assistant_app.py` (Gradio — fallback)
- **Frontend:** `static/index.html` (HTML/CSS/JS inline — dark mode, mobile, VAD no browser)
- **3 cenários testados com sucesso:** tudo local, tudo VPS, local→VPS via tunnel
- **Stack:** faster-whisper (STT) + Kokoro/Piper/Edge TTS (fallback chain) + OpenClaw Gateway (LLM)
- **Barge-in:** Funcional no WebSocket (detecta fala durante playback → envia interrupt → cancela LLM+TTS)
- **Testes:** ~240+ pytest
- **Repo:** github.com/quenaisaacdayner-art/openclaw-voice-assistant

### Arquitetura atual

```
┌─────────────────────────────────────────────────────┐
│  BROWSER (static/index.html)                        │
│  ┌──────────┐  ┌────────┐  ┌──────────────────────┐│
│  │ Web Audio │  │ VAD    │  │ Audio Playback Queue ││
│  │ Capture   │→ │(RMS)   │→ │ (decodeAudioData     ││
│  │ 16kHz PCM │  │800ms   │  │  → onended chain)    ││
│  └──────────┘  │silence  │  └──────────────────────┘│
│                └────────┘                            │
│                    ↕ WebSocket (binary PCM + JSON)   │
└─────────────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────────────┐
│  SERVER (server_ws.py — FastAPI + uvicorn)           │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐│
│  │ Whisper   │→ │ OpenClaw │→ │ TTS (kokoro/piper/ ││
│  │ STT       │  │ Gateway  │  │ edge) por frase    ││
│  │ (tiny)    │  │ (SSE)    │  │                    ││
│  └──────────┘  └──────────┘  └────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### Entrypoints

| Arquivo | Função | Protocolo | Status |
|---------|--------|-----------|--------|
| `server_ws.py` | S2S principal | WebSocket (binary + JSON) | ✅ Principal |
| `voice_assistant_app.py` | Fallback Gradio | HTTP (Gradio SSE) | ✅ Fallback |
| `voice_assistant_cli.py` | Terminal | stdin/stdout | ✅ Funcional |

### Módulos core/

| Módulo | Função | Notas |
|--------|--------|-------|
| `config.py` | Env vars, token, gateway URL (auto-detect porta) | Fonte única de config |
| `stt.py` | Whisper wrapper (lazy loading, thread-safe) | Default: tiny |
| `tts.py` | Fallback chain: kokoro → piper → edge. Download automático de modelos | Warmup no startup |
| `llm.py` | `ask_openclaw` (sync) + `ask_openclaw_stream` (SSE) + `_find_sentence_end` | Parser SSE frágil |
| `history.py` | `build_api_history` + `MAX_HISTORY` | Filtra prefixo `[🎤 Voz]:` |

---

## UPGRADE PLAN anterior (Fases 1-9)

Já executadas (17-20/03). Resumo do que foi feito:

| Fase | O que | Status |
|------|-------|--------|
| 1 | Unificação 3 scripts → core/ + app unificado | ✅ Completo |
| 2 | WebSocket S2S (server_ws.py + index.html) | ✅ Completo |
| 3 | Barge-in, TTS pipeline, testes, polish | ✅ Completo |
| 4 | Interface melhorada (indicadores, dark mode) | ✅ Parcial (no index.html) |
| 5 | Latência (buffer duplo TTS, warmup) | ✅ Completo |
| 6 | Kokoro TTS (local, melhor qualidade) | ✅ Integrado |
| 7 | Open source / DX | 🟡 Parcial (README, CONTRIBUTING, CI pendentes) |
| 8 | Hotfix infra (pre-warm, auto-detect) | ✅ Completo |
| 9 | Auto-detect porta do gateway | ✅ Completo |

---

## MAPA DE EVOLUÇÃO — 8 Subtítulos

### Legenda
- 🔴 Requer decisão arquitetural (debater antes de codar)
- 🟡 Implementável direto (prompt pro Claude Code)
- 🟢 Quick win (melhoria pontual)

---

### SUBTÍTULO 1: Interface & Interação (Frontend) 🔴

> Decisão fundamental: até onde podemos ir com `static/index.html` (JS puro) vs precisar de framework (React/Vue)?

#### 1.1 — Gatilhos de Interface

O `index.html` atual JÁ TEM parcialmente implementado:

| Gatilho | Estado atual no index.html | O que falta |
|---------|---------------------------|-------------|
| **Start/Connect** | ✅ Botão "Iniciar" → `start()` → pede permissão mic → abre WebSocket | Feedback visual durante handshake (loading state) |
| **Interrupt/Barge-in** | ✅ Detecta fala durante playback → `stopPlayback()` + envia `{type: "interrupt"}` via WS → server cancela LLM+TTS | Falta: botão manual de interrupt (tap na tela), feedback visual |
| **Mute/Unmute** | ✅ `toggleMute()` → para envio de chunks sem fechar WS. Ícone muda 🎤↔🔇 | Falta: feedback visual (barra de volume some quando muted) |
| **End/Disconnect** | ❌ Não existe. Fechar aba é a única forma de desconectar | Botão "Encerrar" → fecha WS limpo, limpa buffers, volta pra estado inicial |
| **Audio Routing** | ❌ Não implementável via Web Audio API em browser desktop. Só relevante em app mobile (iOS/Android) | Fora de escopo até ter app nativo |

#### 1.2 — Feedback Visual

| Elemento | Estado atual | O que falta |
|----------|-------------|-------------|
| Status dot (cor) | ✅ 5 estados: connected/listening/thinking/speaking/disconnected com animação pulse | OK — funcional |
| Status texto | ✅ "Escutando", "Pensando...", "Falando" | Adicionar tempo decorrido ("Pensando... 3.2s") |
| Barra de volume (mic) | ✅ `volumeBar` atualiza em tempo real (RMS) | Mudar cor quando muted |
| Transcrição parcial | ❌ Não existe no WS. Só aparece a transcrição final | Mostrar texto parcial enquanto processa (server envia parciais) |
| Waveform/animação | ❌ Só barra de volume | Animação de waveform ou esfera pulsante durante fala (CSS/Canvas) |
| Markdown na resposta | ❌ Texto puro (`.textContent`) | Renderizar markdown básico (bold, italic, code, links) |

#### 1.3 — Layout & UX

| Aspecto | Estado atual | O que falta |
|---------|-------------|-------------|
| Mobile | ✅ Responsivo básico (`@media max-width: 600px`) | Testar em celular real. Botão mic maior, touch-friendly |
| Dark mode | ✅ Hardcoded dark (#1a1a2e) | Opcional: toggle light/dark |
| Input de texto | ❌ Só voz | Adicionar campo de texto pra digitar quando mic não disponível |
| Config na UI | ❌ Hardcoded | Painel com: gateway URL, modelo Whisper, engine TTS, volume |
| Histórico persistente | ❌ Perde ao recarregar | localStorage pra manter histórico entre reloads |
| Export conversa | ❌ Não existe | Botão "Exportar" → salva como .txt ou .json |
| Indicador de rede | ❌ Não existe | Ping/latência visível ao servidor WS |

#### Decisão pendente (debater)
O `index.html` atual com JS puro é suficiente pra TUDO listado acima? **Sim** — nenhum item aqui exige framework. HTML/CSS/JS inline consegue fazer:
- Botões, feedback visual, animações CSS, Canvas pra waveform
- localStorage, markdown rendering (lib leve tipo marked.js)
- Campo de texto, painel de config

Framework (React/Vue) seria necessário APENAS se: (a) componentização pesada ou (b) state management complexo com muitas telas. Não é o caso hoje.

**Recomendação:** Continuar com JS puro no index.html. Dividir em seções claras. Se ficar >800 linhas, extrair pra `static/app.js`.

---

### SUBTÍTULO 2: Pipeline de Áudio (STT + TTS) 🟡

#### 2.1 — STT (Speech-to-Text)

| Aspecto | Hoje | Melhoria possível | Impacto | Viável grátis? |
|---------|------|-------------------|---------|----------------|
| Modelo | Whisper tiny (75MB, CPU) | `distil-whisper-large-v3` — 49% mais rápido que large-v3, qualidade ~igual | Precisão PT-BR | ✅ |
| Fallback | Nenhum | Se Whisper falhar → retornar erro claro (já faz parcial) | Robustez | ✅ |
| Modelo selecionável | `WHISPER_MODEL` env var | Seletor na UI (tiny/small/medium) + restart | UX | ✅ |
| Streaming STT | ❌ (transcreve só após `speech_end`) | Whisper processa chunks parciais e envia transcrição interim pro browser | Feedback visual | 🟡 Complexo |

#### 2.2 — TTS (Text-to-Speech)

| Aspecto | Hoje | Melhoria possível | Impacto | Viável grátis? |
|---------|------|-------------------|---------|----------------|
| Chain | Kokoro → Piper → Edge (fallback) | ✅ Já implementado. Sem melhoria óbvia | — | — |
| Vozes | 1 voz fixa por engine | Seletor de voz na UI. Edge tem ~10 vozes PT-BR | UX | ✅ |
| Velocidade/tom | Fixo (speed=1.0) | Slider de velocidade (Edge e Kokoro suportam) | Personalização | ✅ |
| SSML | ❌ | Edge TTS suporta SSML (ênfase, pausas, pronúncia). Kokoro não | Expressividade | 🟡 Complexo |

---

### SUBTÍTULO 3: Latência End-to-End 🟡

#### Pipeline atual (medido 19-20/03)

```
[Fala] → [VAD 800ms silence] → [Whisper tiny ~1-2s] → [LLM TTFT 2-31s*] → [TTS 1ª frase ~0.5-2s] → [Áudio]
                                                         ↑ GARGALO
* Opus 4: ~31s TTFT | Sonnet 4.6: ~2-5s TTFT
```

| Fase | Tempo (tiny+Sonnet) | Tempo (tiny+Opus) | Otimização possível |
|------|--------------------|--------------------|---------------------|
| VAD silence | 800ms | 800ms | Reduzir pra 500ms — risco de cortar frases | 
| Whisper STT | 1-2s | 1-2s | distil-whisper (ganho marginal em tiny) |
| **LLM TTFT** | **2-5s** | **~31s** | **Modelo mais rápido pra voz** (config na UI) |
| TTS 1ª frase | 0.5-2s | 0.5-2s | Já otimizado com buffer duplo + warmup |
| **Total** | **~4-9s** | **~35-40s** | — |

#### O que PODEMOS otimizar (grátis)
1. **System prompt pra voz** — instruir LLM a responder curto e conversacional = menos tokens = TTFT menor
2. **Modelo configurável na UI** — Sonnet pra sessões de voz, Opus pra texto detalhado
3. **VAD tuning** — ajustar `SILENCE_MS` (800→600ms) + `SPEECH_MIN_MS` (200→150ms) na UI
4. **Streaming STT parcial** — enviar transcrição interim pro browser enquanto Whisper processa (complexo)

#### O que NÃO podemos otimizar
- TTFT do LLM — depende do modelo/provider. Fora do nosso controle
- Latência de rede (cenário 3: tunnel) — ~30-50ms por hop, imperceptível

---

### SUBTÍTULO 4: Transporte & Conexão 🟡

| Aspecto | Hoje | Melhoria | Prioridade |
|---------|------|----------|------------|
| Protocolo | ✅ WebSocket bidirecional (binary PCM + JSON) | Já implementado | — |
| Reconexão | ✅ Auto-reconnect com 3s delay (`onclose → setTimeout(connect, 3000)`) | Backoff exponencial (3s → 6s → 12s → max 30s) | Baixa |
| Compressão áudio | ❌ PCM raw 16-bit 16kHz (~32KB/s) | Opus codec (~3KB/s) — reduz 10x | 🟡 Médio (precisa WebAssembly encoder) |
| Keep-alive | ❌ Nenhum heartbeat WS | Ping/pong cada 30s pra detectar conexão morta | 🟡 Médio |
| Config via WS | ❌ `data["type"] == "config"` existe no server mas é `pass` | Implementar: mudar modelo, Whisper, TTS, VAD params em tempo real | 🟡 Médio |
| Multi-sessão | ❌ 1 WebSocket = 1 conversa. Sem persistência | Session ID → reconectar sem perder histórico | Baixo |
| TLS/WSS | ❌ ws:// (sem criptografia) | Para acesso remoto: wss:// via reverse proxy (nginx/caddy) | 🔴 Necessário pra produção |

---

### SUBTÍTULO 5: Robustez & Stress Test 🟡

#### Cenários a testar

| # | Cenário | Testado? | Risco | Como testar |
|---|---------|----------|-------|-------------|
| 1 | Gateway cai mid-response | ❌ | SSE trava, TTS nunca gera | Matar gateway durante streaming |
| 2 | Áudio vazio / silêncio puro | Parcial (VAD) | Whisper pode alucinar | Enviar 5s de silêncio |
| 3 | Resposta LLM muito longa (>3000 chars) | ❌ | TTS trunca em 1500, gap longo | Prompt que gera resposta longa |
| 4 | Múltiplos `speech_end` rápidos | ❌ | Race condition em `process_speech` (flag `processing`) | Falar-parar-falar em <1s |
| 5 | Perda de rede mid-TTS (Edge engine) | ❌ | Edge falha, Piper/Kokoro ok (local) | Desconectar internet durante TTS |
| 6 | Browser fecha mid-response | Parcial | `WebSocketDisconnect` capturado, mas `process_task` pode continuar | Fechar aba durante resposta |
| 7 | Memória ao longo do tempo | ❌ | Whisper + TTS + histórico acumulam RAM | Session de 1h contínua |
| 8 | 2 abas abertas (concorrência) | ❌ | 2 WebSockets pro mesmo server — devem ser independentes | Abrir 2 tabs |
| 9 | Áudio com ruído/música de fundo | ❌ | VAD pode triggerar, Whisper transcreve lixo | Tocar música e falar |
| 10 | `decodeAudioData` falha no browser | ❌ | Playback queue trava (falta try/catch no `enqueueAudio`) | Enviar WAV malformado |
| 11 | WebSocket desconecta e reconecta | ❌ | `chat_history` reinicia (está no server) | Reconectar e verificar contexto |
| 12 | Cold start após sleep do Windows | Parcial | Warmup refaz, mas AudioContext do browser pode estar suspenso | Fechar laptop, reabrir |

#### Erros conhecidos (de BUGS_PENDENTES.md, atualizados)

| Bug | Status | Onde | Impacto |
|-----|--------|------|---------|
| `_detect_mode()` timeout 15s | ⚠️ Parcial | voice_assistant_app.py | Startup lento (só Gradio) |
| `ERR_CONTENT_LENGTH_MISMATCH` | ⚠️ Parcial | core/tts.py | Acumula arquivos temp (só Gradio) |
| Latência 1ª resposta ~35-40s | 📝 Documentado | LLM (Opus 4) | Usar Sonnet pra voz |
| `_find_sentence_end` não detecta pontuação no fim | 🔴 Pendente | core/llm.py | TTS pode atrasar última frase |
| `build_api_history` filtra `[🎤` inteiro | 🔴 Pendente | core/history.py | Contexto de voz não vai pro LLM |
| `playbackQueue` trava se `decodeAudioData` falha | 🔴 Pendente | static/index.html | Fila de áudio para |

---

### SUBTÍTULO 6: Deploy & Distribuição 🟢

| Item | Hoje | Melhoria | Complexidade |
|------|------|----------|-------------|
| Instalação | `pip install -r requirements.txt` manual | Script de setup (detect OS, cria venv, instala deps, baixa modelos) | 🟢 Baixa |
| Docker | ❌ Não existe | `Dockerfile` + `docker-compose.yml` (VPS em 1 comando) | 🟡 Média |
| Modelo Piper (60MB) | No .git (gitignore parcial) | Download automático no 1º uso (já implementado em tts.py) | 🟢 Pronto |
| CI | ❌ Não existe | GitHub Actions: pytest no push/PR | 🟢 Baixa |
| README | Existe mas desatualizado | Reescrever: 3 cenários, screenshots, GIF demo | 🟢 Baixa |
| `.env.example` | Existe | Verificar se todas as vars estão documentadas | 🟢 Trivial |
| Scripts de conexão | `scripts/run_*.sh` + `.ps1` | ✅ Já existem pra 3 cenários | Pronto |

---

### SUBTÍTULO 7: Segurança 🟡

| Aspecto | Hoje | Risco | Melhoria |
|---------|------|-------|----------|
| Token do gateway | Lido de `openclaw.json` server-side | ✅ Nunca vai pro browser (WebSocket envia texto, não token) | OK |
| HTTPS/WSS | ❌ HTTP puro (ws://) | Mic API exige HTTPS em produção (localhost é exceção) | Reverse proxy (nginx + certbot) |
| Auth da interface | ❌ Zero. Quem acessa `:7860` tem acesso total | Risco baixo (localhost). Risco ALTO se expor na internet | PIN/password simples |
| Rate limit | ❌ Nenhum | DoS: alguém manda 100 requests/s | Limite no server_ws.py (ex: 1 request a cada 2s) |
| Input sanitization | ❌ Texto do Whisper vai direto pro LLM | Prompt injection via voz | Filtrar/sanitizar transcrição (complexo) |
| Logs | Transcrições no stdout | Dados sensíveis nos logs | Rotação de logs + nível configurável |

---

### SUBTÍTULO 8: Conversação & Contexto 🟡

| Aspecto | Hoje | Melhoria | Impacto |
|---------|------|----------|---------|
| Histórico | 10 exchanges em memória (server-side `chat_history`) | Persistir em arquivo/SQLite. Retomar ao reconectar | Alto |
| System prompt | Nenhum customizado | Prompt otimizado pra voz: "responda de forma conversacional, máximo 2-3 frases, como se estivesse falando" | Alto |
| Contexto do OpenClaw | ✅ Usa model `openclaw:main` → acessa memória/skills do agente | OK — já integrado | — |
| Modos de conversa | Sempre igual | Toggle: conversa livre vs assistente focado vs tutor | Médio |
| Export | ❌ Não existe | Botão "Salvar conversa" → .txt ou .json | Baixo |
| Feedback loop | ❌ Não existe | 👍/👎 por resposta → salvar pra análise | Baixo |

---

## PRIORIZAÇÃO (recomendação — Dayner decide)

### Fase imediata (próxima sessão)
1. **Subtítulo 1** — Completar gatilhos + feedback visual no `index.html`
2. **Subtítulo 5** — Stress test dos cenários críticos (gateway down, playback queue, pontuação)

### Fase seguinte
3. **Subtítulo 3** — System prompt pra voz + modelo configurável na UI
4. **Subtítulo 4** — Config via WS + heartbeat + backoff

### Depois
5. **Subtítulo 6** — Docker + CI + README
6. **Subtítulo 8** — Histórico persistente + export
7. **Subtítulo 7** — Auth + HTTPS (quando expor na internet)
8. **Subtítulo 2** — Vozes/velocidade (nice-to-have)

---

## REGRAS DE EXECUÇÃO

1. **OpenClaw (eu) planeja e escreve prompts** → `prompts/subtituloN_descricao.md`
2. **Dayner pede ao Claude Code:** "Leia `prompts/subtituloN_descricao.md` e execute"
3. **Claude Code executa** seguindo o CLAUDE.md do projeto
4. **OpenClaw audita** o resultado
5. **Dayner aprova** e comita
6. Cada prompt é **auto-contido** — Claude Code não precisa de contexto externo
7. Se um subtítulo é grande, dividimos em sub-prompts (ex: `subtitulo1a_disconnect.md`, `subtitulo1b_waveform.md`)
8. **Commit após cada prompt executado com sucesso**
9. **Testes rodam após cada mudança** (~240 testes = guardrail)
10. **Se quebrar algum teste → reverter e investigar antes de continuar**

---

## DECISÕES TOMADAS

| Data | Decisão | Contexto |
|------|---------|----------|
| 22/03 | Continuar com JS puro no `index.html` (sem framework) | Tudo listado é implementável sem React/Vue |
| 22/03 | Audio Routing fora de escopo | Só relevante em app nativo mobile |
| 22/03 | OpenClaw planeja, Claude Code executa | Dayner confirmou os papéis |
| 22/03 | Prompts ficam em `prompts/` dentro do projeto | Dayner pede "leia e execute" pro Claude Code |

---

## REFERÊNCIAS

| Arquivo | Conteúdo |
|---------|----------|
| `CLAUDE.md` | Contexto pro Claude Code (arquitetura, regras, partes frágeis) |
| `BUGS_PENDENTES.md` | Bugs documentados (6 items) |
| `TESTING_RESULTS.md` | Resultados dos 3 cenários (20/03) |
| `UPGRADE_PLAN.md` | Plano original das fases 1-9 (histórico) |
| `prompts/` | Prompts auto-contidos pra Claude Code |
| `auditoria/` | Logs de auditoria das fases anteriores |
