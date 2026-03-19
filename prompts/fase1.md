# FASE 1 — Unificação (core/ + app unificado + testes)

Leia estes arquivos nesta ordem antes de qualquer ação:
1. CLAUDE.md
2. UPGRADE_PLAN.md (seção FASE 1)
3. core/ (todos: config.py, stt.py, tts.py, llm.py, history.py, __init__.py)
4. voice_assistant_cli.py (já existe, já importa do core/)
5. voice_assistant_web.py (script Gradio local — 783 linhas)
6. voice_assistant_vps.py (script Gradio VPS — 677 linhas)
7. tests/conftest.py

NÃO leia os testes ainda. Primeiro entenda o código fonte.

## CONTEXTO

O core/ e voice_assistant_cli.py já foram criados e estão funcionais. Falta:
1. Criar voice_assistant_app.py — Gradio UNIFICADO que substitui web.py e vps.py
2. Adaptar os 246 testes pra funcionar com a nova estrutura

## TASK 1: Criar voice_assistant_app.py

Crie UM script Gradio que unifica voice_assistant_web.py e voice_assistant_vps.py.

### Detecção automática de modo

No startup, tenta importar RealtimeSTT:
- SUCESSO + PyAudio disponível → modo LOCAL
  - Escuta contínua via ContinuousListener (classe de voice_assistant_web.py)
  - Usa AudioToTextRecorder em thread daemon
  - audio_input manual (gravar botão, não streaming)
- FALHA → modo BROWSER  
  - Escuta contínua via BrowserContinuousListener (classe de voice_assistant_vps.py)
  - VAD por RMS (energy threshold 0.01)
  - audio_input com streaming=True, chunks vão pro feed_chunk()

### Regras

1. Importar TUDO de core/ (config, stt, tts, llm, history). ZERO duplicação.
2. A UI Gradio é IDÊNTICA em ambos os modos. Mesmos componentes, mesmo layout, mesmo CSS.
3. O que muda entre modos: APENAS o mecanismo de escuta contínua.
4. Funcionalidades que existem em AMBOS os scripts originais: copiar UMA vez.
5. Funcionalidades que existem em SÓ UM script: copiar e adaptar.
6. Manter CUSTOM_CSS exatamente como está nos scripts originais.
7. Manter gr.skip() em TODOS os retornos sem mudança (race condition Gradio documentada no CLAUDE.md).
8. Token carregado UMA vez no startup via core/config.load_token().
9. SERVER_HOST = env var SERVER_HOST ou '127.0.0.1'
10. SERVER_PORT = env var PORT ou 7860
11. inbrowser = True se modo LOCAL, False se modo BROWSER
12. NÃO deletar voice_assistant_web.py nem voice_assistant_vps.py (scripts antigos ficam)

### Funções que vêm do core (NÃO reimplementar)

- core.config: GATEWAY_URL, MODEL, TTS_VOICE, WHISPER_MODEL_SIZE, PIPER_MODEL, TTS_ENGINE, load_token()
- core.stt: transcribe_audio(audio_input), _get_whisper()
- core.tts: generate_tts(text), init_piper()
- core.llm: ask_openclaw(text, token, history), ask_openclaw_stream(text, token, history), _find_sentence_end(text)
- core.history: build_api_history(chat_history), MAX_HISTORY

### Funções que ficam NO app (específicas da UI)

- respond_text() — streaming com sentence TTS
- respond_audio() — transcreve + streaming  
- toggle_continuous() — liga/desliga escuta contínua
- poll_transcription() — checa text_queue do listener
- ContinuousListener (classe, modo LOCAL)
- BrowserContinuousListener (classe, modo BROWSER)
- find_mic_pyaudio() (só modo LOCAL)
- handle_stream_chunk() (só modo BROWSER)
- handle_stop_recording() (só modo BROWSER)

### Após criar

1. Verificar syntax: python -c "import voice_assistant_app"
2. Se der ImportError, corrigir

## TASK 2: Adaptar testes

Agora leia TODOS os arquivos em tests/.

Os testes atuais importam diretamente de voice_assistant, voice_assistant_web, voice_assistant_vps.
Precisam ser adaptados pra importar de core/ e dos novos scripts.

### Estratégia de adaptação

1. test_cli.py e test_cli_extended.py → adaptar imports pra core/ e voice_assistant_cli
2. test_web.py e test_web_extended.py → adaptar pra core/ e voice_assistant_app (modo LOCAL)
3. test_vps.py e test_vps_extended.py → adaptar pra core/ e voice_assistant_app (modo BROWSER)
4. test_shared_logic.py → adaptar pra core/ diretamente
5. test_code_duplication.py → REESCREVER: agora verifica que core/ tem as funções e os scripts importam delas
6. test_bugs_documented.py → adaptar imports pra core/ e voice_assistant_app
7. conftest.py → manter como está (fixtures são genéricas)

### Regras pra testes

- Se um teste mocka `voice_assistant_web.load_token`, agora mocka `core.config.load_token`
- Se um teste mocka `voice_assistant_vps.ask_openclaw`, agora mocka `core.llm.ask_openclaw`
- Se um teste verifica que uma função EXISTE em voice_assistant_web, agora verifica que existe em core/ ou voice_assistant_app
- Se um teste importa constante de voice_assistant_web (ex: GATEWAY_URL), agora importa de core.config
- MANTER o behavior que os testes verificam — só mudar imports/mocks
- test_code_duplication.py precisa ser reescrito do zero — o conceito mudou (antes: verificar duplicação, agora: verificar que core/ é a fonte única)

### Após adaptar

1. Rodar: python -m pytest tests/ -v
2. Se algum teste falha: ler o erro, entender se é import errado ou behavior real
3. Corrigir imports/mocks até TODOS passarem
4. Commitar: git add -A && git commit -m "refactor: fase 1 - core compartilhado + app unificado + testes adaptados"
5. NÃO fazer git push
