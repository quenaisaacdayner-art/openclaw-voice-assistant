# Contribuindo

Obrigado por considerar contribuir com o OpenClaw Voice Assistant!

## Rodando localmente

```bash
# Clone o repositório
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git
cd openclaw-voice-assistant

# Crie um virtual environment (recomendado)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# ou: venv\Scripts\activate  # Windows

# Instale dependências base
pip install -r requirements.txt

# Para TTS local (Kokoro/Piper) e mic direto:
pip install -r requirements-local.txt

# Rode o app
python voice_assistant_app.py
```

Você precisa do [OpenClaw](https://github.com/openclaw/openclaw) rodando com o gateway HTTP habilitado.

## Rodando testes

```bash
python -m pytest tests/ -v
```

Todos os testes usam mocks — não precisam de modelo Whisper, mic ou gateway rodando.

## Estrutura do código

```
core/                    ─── Lógica compartilhada (zero duplicação)
  config.py              ─── Constantes, load_token(), env vars
  stt.py                 ─── faster-whisper, transcribe_audio()
  tts.py                 ─── Kokoro + Piper + Edge TTS com fallback automático
  llm.py                 ─── ask_openclaw(), streaming SSE parser
  history.py             ─── build_api_history(), MAX_HISTORY

voice_assistant_cli.py   ─── Entrypoint CLI (terminal)
voice_assistant_app.py   ─── Entrypoint Gradio (web, auto-detecta local vs browser)

tests/                   ─── ~215 testes com pytest + unittest.mock
scripts/                 ─── Scripts auxiliares (tunnel SSH, etc.)
```

## Guidelines de PR

1. **Rode os testes** antes de abrir o PR: `python -m pytest tests/ -v`
2. **Um PR por feature/fix** — PRs pequenos e focados são mais fáceis de revisar
3. **Descreva o que mudou** — inclua contexto no PR description
4. **Mantenha o estilo existente:**
   - Python 3.10+
   - Português nos comentários e UI
   - Sem type hints (manter consistente com o código atual)
   - Imports: stdlib → third-party → locais
5. **Testes** — adicione testes para funcionalidades novas, mantenha os existentes passando
6. **Sem duplicação** — toda lógica compartilhada vai no `core/`, scripts finais só têm UI + main()
