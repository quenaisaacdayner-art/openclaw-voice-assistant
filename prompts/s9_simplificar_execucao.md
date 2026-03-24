# Prompt S9: Simplificar Execução — `run.sh` + `run.ps1` + `pyproject.toml` + comando `ova`

## Objetivo

Criar 4 arquivos novos que simplificam a execução do projeto para 1 comando.
NÃO modificar nenhum arquivo existente. NÃO deletar nada.

## Contexto obrigatório

Ler CLAUDE.md antes de começar. Ele tem a arquitetura, dependências entre arquivos, variáveis de ambiente, e partes frágeis.

## O que criar

### 1. `run.sh` (raiz do projeto)

Script bash "faz tudo" para Linux/Mac. Lógica em ordem:

1. Detectar diretório do script (pra funcionar de qualquer pasta)
2. Verificar se `venv/` existe:
   - NÃO existe → rodar `bash setup.sh` automaticamente
   - Existe → pular
3. Ativar o venv: `source venv/bin/activate`
4. Verificar se tem processo preso na porta 7860:
   - Se sim → matar com `kill`
5. Configurar variáveis de ambiente com defaults inteligentes:
   - `OPENCLAW_GATEWAY_URL`: auto-detectar de `~/.openclaw/openclaw.json` (campo `gateway.port`). Fallback: `http://127.0.0.1:18789/v1/chat/completions`
   - `OPENCLAW_MODEL`: default `anthropic/claude-sonnet-4-6`
   - `WHISPER_MODEL`: default `tiny`
   - `TTS_ENGINE`: default `edge`
   - `SERVER_HOST`: default `127.0.0.1`
   - Respeitar variáveis já definidas pelo usuário (não sobrescrever se já existem no env)
6. Aceitar flags opcionais por argumentos CLI:
   - `--host <ip>` → sobrescreve SERVER_HOST (ex: `--host 0.0.0.0` pra VPS)
   - `--port <numero>` → sobrescreve PORT
   - `--gateway-url <url>` → sobrescreve OPENCLAW_GATEWAY_URL
   - `--model <modelo>` → sobrescreve OPENCLAW_MODEL
   - `--whisper <tiny|small>` → sobrescreve WHISPER_MODEL
   - `--help` → mostrar todas as opções e sair
7. Imprimir banner com configuração:
   ```
   ═══════════════════════════════════════
     OpenClaw Voice Assistant
   ═══════════════════════════════════════
     Gateway: http://127.0.0.1:18789/...
     Modelo:  anthropic/claude-sonnet-4-6
     Whisper: tiny
     TTS:     edge
     URL:     http://127.0.0.1:7860
   ═══════════════════════════════════════
   ```
8. Abrir browser automaticamente ANTES de iniciar o server (em background):
   - Linux: `xdg-open http://127.0.0.1:$PORT &`
   - Mac: `open http://127.0.0.1:$PORT &`
   - Delay de 2 segundos antes de abrir (pra dar tempo do server subir): usar `(sleep 2 && xdg-open ...) &`
9. Rodar `python server_ws.py`

**Referência:** `scripts/run_local.sh` e `scripts/_activate_venv.sh` — eles já têm partes dessa lógica. Reutilizar o que fizer sentido, mas o `run.sh` deve ser **auto-contido** (não depender de `_activate_venv.sh`).

### 2. `run.ps1` (raiz do projeto)

Equivalente do `run.sh` para Windows PowerShell. Mesma lógica, adaptada:

1. Detectar diretório do script
2. Verificar `venv\`:
   - NÃO existe → rodar `.\setup.ps1` automaticamente
   - Existe → pular
3. Ativar venv: `.\venv\Scripts\Activate.ps1`
4. Verificar processo na porta 7860:
   - Usar `Get-NetTCPConnection -LocalPort 7860` + `Stop-Process`
5. Configurar variáveis de ambiente (mesmos defaults do bash)
   - Auto-detectar gateway URL de `~/.openclaw/openclaw.json` (usar `ConvertFrom-Json`)
   - Respeitar variáveis já definidas
6. Aceitar parâmetros PowerShell:
   - `param()` block no topo com: `-Host_`, `-Port`, `-GatewayUrl`, `-Model`, `-Whisper`
   - Nota: `-Host` é reservado no PowerShell, usar `-Host_` ou `-ServerHost`
7. Banner (mesmo formato do bash)
8. Abrir browser: `Start-Process "http://127.0.0.1:$port"` com delay de 2s via `Start-Job`
9. Rodar `python server_ws.py`

**Referência:** `scripts/run_local.ps1` — reutilizar lógica, mas auto-contido.

### 3. `pyproject.toml` (raiz do projeto)

Arquivo de configuração do pacote Python (padrão PEP 621). Conteúdo:

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "openclaw-voice-assistant"
version = "0.1.0"
description = "Speech-to-Speech voice interface for OpenClaw Gateway"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Dayner", email = ""}
]
keywords = ["openclaw", "voice-assistant", "speech-to-speech", "whisper", "tts"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Multimedia :: Sound/Audio :: Speech",
]
dependencies = [
    "faster-whisper",
    "edge-tts",
    "requests",
    "numpy",
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "websockets>=12.0",
]

[project.optional-dependencies]
local = [
    "scipy",
    "sounddevice",
]
gradio = [
    "gradio",
]

[project.urls]
Homepage = "https://github.com/quenaisaacdayner-art/openclaw-voice-assistant"
Repository = "https://github.com/quenaisaacdayner-art/openclaw-voice-assistant"
Issues = "https://github.com/quenaisaacdayner-art/openclaw-voice-assistant/issues"

[project.scripts]
ova = "core.__main__:main"

[tool.setuptools.packages.find]
include = ["core*", "static*"]

[tool.setuptools.package-data]
static = ["*.html", "*.js"]
```

**Notas importantes:**
- `gradio` e `scipy`/`sounddevice` vão como dependências OPCIONAIS — não são necessárias pro WebSocket S2S
- O entry point `ova` aponta pra `core/__main__.py:main` — arquivo criado abaixo
- `static/` precisa ser incluído como package data (HTML + JS)

### 4. `core/__main__.py`

Arquivo que roda quando o usuário digita `ova` no terminal. Lógica:

```python
"""
OpenClaw Voice Assistant — Entry point (comando `ova`)
Uso: ova [--host IP] [--port NUM] [--gateway-url URL] [--model MODELO] [--whisper tiny|small]
"""
```

1. Usar `argparse` para parsear argumentos CLI:
   - `--host` (default: `127.0.0.1`) — endereço do server
   - `--port` (default: `7860`) — porta
   - `--gateway-url` — sobrescreve OPENCLAW_GATEWAY_URL
   - `--model` — sobrescreve OPENCLAW_MODEL
   - `--whisper` (choices: `tiny`, `small`) — sobrescreve WHISPER_MODEL
   - `--tts-engine` (choices: `edge`, `piper`, `kokoro`) — sobrescreve TTS_ENGINE
   - `--tts-voice` — sobrescreve TTS_VOICE
   - `--no-browser` — não abrir browser automaticamente
   - `--version` — mostrar versão e sair

2. Setar variáveis de ambiente ANTES de importar qualquer módulo do core:
   - Se o usuário passou `--gateway-url`, setar `os.environ["OPENCLAW_GATEWAY_URL"]`
   - Idem pra model, whisper, tts, host, port
   - Isso é necessário porque `core/config.py` lê env vars no import

3. Matar processo anterior na porta (mesmo do run.sh):
   - Windows: `Get-NetTCPConnection` via subprocess
   - Linux/Mac: `lsof -ti:PORT` via subprocess
   - Se falhar silenciosamente, ok — não é crítico

4. Imprimir banner (mesmo formato do run.sh/run.ps1)

5. Abrir browser em background thread (a menos que `--no-browser`):
   - Usar `import webbrowser` + `threading.Timer(2.0, webbrowser.open, [url])`
   - 2 segundos de delay pro server subir

6. Importar e rodar uvicorn:
   ```python
   import uvicorn
   # Importar app DEPOIS de setar env vars
   from server_ws import app
   uvicorn.run(app, host=host, port=port)
   ```

**Atenção no import:** `server_ws.py` está na RAIZ do projeto, não dentro de `core/`. Quando instalado via pip, o Python precisa encontrar `server_ws`. Há duas soluções:
- **Opção A (simples):** Adicionar o diretório do projeto ao `sys.path` antes do import
- **Opção B (limpa):** Mover `server_ws.py` pra dentro de `core/` e ajustar imports — MAS isso quebra os scripts existentes

**Usar Opção A.** Não mover arquivos. Dentro de `__main__.py`:
```python
import sys
import os
# Garantir que a raiz do projeto está no path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
```

### 5. `core/__init__.py`

Se não existir, criar arquivo vazio `core/__init__.py`. Necessário para o Python reconhecer `core/` como pacote quando instalado via pip.

## Testes a criar

Adicionar em `tests/test_entry_point.py`:

1. **test_ova_help** — `ova --help` retorna código 0 e contém "OpenClaw Voice Assistant"
2. **test_ova_version** — `ova --version` retorna "0.1.0"
3. **test_main_sets_env_vars** — chamar `main()` com args `["--model", "test-model"]` e verificar que `os.environ["OPENCLAW_MODEL"]` foi setado
4. **test_main_default_host** — sem args, host default é `127.0.0.1`
5. **test_main_default_port** — sem args, port default é `7860`
6. **test_pyproject_exists** — `pyproject.toml` existe e tem `[project.scripts]`
7. **test_core_main_importable** — `from core.__main__ import main` não levanta exceção

**Importante:** Os testes que chamam `main()` devem usar mock pra `uvicorn.run` — NÃO subir o server de verdade nos testes.

## O que NÃO fazer

- ❌ NÃO modificar `server_ws.py`, `core/config.py`, ou qualquer arquivo existente
- ❌ NÃO deletar nada
- ❌ NÃO mover `server_ws.py` de lugar
- ❌ NÃO mudar a lógica de detecção de gateway URL em `core/config.py` (já funciona)
- ❌ NÃO adicionar dependências novas ao `requirements.txt` (pyproject.toml é o novo)
- ❌ NÃO rodar o server durante os testes

## Checklist de validação

Depois de criar tudo:

1. `python -m pytest tests/ -v --tb=short` — TODOS os testes anteriores (111) + novos devem passar
2. `pip install -e .` (dentro do venv) — deve instalar sem erro
3. Verificar que `ova --help` funciona e mostra opções
4. Verificar que `ova --version` mostra `0.1.0`
5. Verificar que `python -c "from core.__main__ import main"` funciona
6. NÃO rodar `ova` de verdade (precisa do gateway ativo)

## Ordem de execução

1. Criar `core/__init__.py` (se não existir)
2. Criar `core/__main__.py`
3. Criar `pyproject.toml`
4. Criar `run.sh`
5. Criar `run.ps1`
6. Criar `tests/test_entry_point.py`
7. Rodar `pip install -e .` no venv
8. Rodar `python -m pytest tests/ -v --tb=short`
9. Verificar `ova --help` e `ova --version`
