# S6: Deploy & Distribuição — PROMPT COMPLETO

> Prompt unificado. Leia e execute TUDO.
> Pré-requisito: S1-S5 completos
> Arquivos a criar/modificar: `setup.ps1`, `.github/workflows/test.yml`, `README.md`, `CONTRIBUTING.md`, `prompts/README.md`, `.gitignore`

---

## Visão geral

4 tarefas de empacotamento e documentação. Zero mudanças no código funcional (server_ws, core/, index.html). Implementar nesta ordem:

1. `setup.ps1` — Setup automático pra Windows PowerShell
2. CI fix — GitHub Actions que não trava
3. README atualizado — Roadmap S1-S5, sem placeholder
4. Limpeza — .gitignore, screenshot solto, prompts/README.md

---

## TAREFA 1: `setup.ps1` — Setup pra Windows

Criar `setup.ps1` na raiz do projeto. Equivalente do `setup.sh` mas pra PowerShell.

```powershell
# OpenClaw Voice Assistant — Setup (Windows PowerShell)
# Roda: .\setup.ps1

$ErrorActionPreference = "Stop"

function Log($msg) { Write-Host "✅ $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "⚠️  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "❌ $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "═══════════════════════════════════════════════"
Write-Host "  OpenClaw Voice Assistant — Setup (Windows)"
Write-Host "═══════════════════════════════════════════════"
Write-Host ""

# 1. Verificar Python 3.10+
$py = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $parts = $ver.Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $py = $cmd
                break
            }
        }
    } catch {}
}

if (-not $py) {
    Fail "Python 3.10+ não encontrado. Instale de https://python.org/downloads e marque 'Add to PATH'"
}

$pyVersion = & $py --version 2>&1
Log "Python encontrado: $pyVersion ($py)"

# 2. Criar virtualenv
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (Test-Path "venv") {
    Log "Virtualenv já existe (venv\)"
} else {
    Log "Criando virtualenv..."
    & $py -m venv venv
    if ($LASTEXITCODE -ne 0) { Fail "Falha ao criar virtualenv" }
    Log "Virtualenv criado"
}

# 3. Ativar
$activateScript = Join-Path $scriptDir "venv\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Fail "Script de ativação não encontrado em venv\Scripts\Activate.ps1"
}
& $activateScript
Log "Virtualenv ativado"

# 4. Instalar dependências
Log "Instalando dependências base..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

Write-Host ""
Write-Host "═══════════════════════════════════════════════"
Write-Host "  ✅ Setup completo!"
Write-Host "═══════════════════════════════════════════════"
Write-Host ""
Write-Host "  Para rodar:"
Write-Host "    .\venv\Scripts\Activate.ps1"
Write-Host "    .\scripts\run_local.ps1         # Cenário 1: tudo local"
Write-Host ""
Write-Host "  Para TTS local (Kokoro/Piper) + mic direto:"
Write-Host "    pip install -r requirements-local.txt"
Write-Host ""
Write-Host "  Docs: README.md"
Write-Host ""
```

**Testar mentalmente:** O script é autocontido, usa `$ErrorActionPreference = "Stop"` pra parar em qualquer erro. Não tenta instalar Python (no Windows é via .msi/winget, não via script).

---

## TAREFA 2: Fix CI — GitHub Actions

O workflow atual (`test.yml`) pode quebrar porque alguns testes importam módulos que carregam modelos pesados. O fix já foi feito nos testes (verificação via source code em vez de import), mas o workflow precisa de ajustes.

**Substituir COMPLETAMENTE** `.github/workflows/test.yml` por:

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt pytest

      - name: Run tests
        run: python -m pytest tests/ -v --tb=short
        env:
          OPENCLAW_GATEWAY_TOKEN: "test-token-ci"
```

**Mudanças vs atual:**
1. `pip install --upgrade pip` antes das deps (evita warnings)
2. `--tb=short` no pytest (logs mais limpos no CI)
3. `OPENCLAW_GATEWAY_TOKEN` como env var (evita que `load_token()` tente ler `openclaw.json` que não existe no CI)

**Verificar:** Rodar `python -m pytest tests/ -v` localmente pra confirmar que tudo passa ANTES de mudar o workflow.

---

## TAREFA 3: Atualizar README.md

O README atual é bom mas tem 3 problemas:
1. Roadmap desatualizado (só mostra fases 1-3)
2. Placeholder de GIF que nunca foi substituído
3. Falta mencionar o WebSocket server (`server_ws.py`) como entrypoint principal

**Editar as seguintes seções do README.md (manter o resto intacto):**

### 3a. Remover placeholder do GIF

Trocar:
```markdown
<!-- TODO: substituir por GIF de demo -->
![Demo placeholder](https://via.placeholder.com/800x400?text=Demo+GIF+aqui)
```

Por:
```markdown
<!-- GIF de demo será adicionado em breve -->
```

### 3b. Atualizar seção Roadmap

Trocar a seção `## Roadmap` inteira por:

```markdown
## Roadmap

- [x] Protótipo funcional (VAD + STT + LLM + TTS)
- [x] Interface web + CLI
- [x] Escuta contínua (local + browser)
- [x] Buffer duplo TTS
- [x] 3 engines TTS com fallback
- [x] **Fase 1-3:** Latência, WebSocket S2S, Barge-in
- [x] **S1:** Interface & Interação — Disconnect, Interrupt, Input texto, Timer, Esfera pulsante, Markdown, Config panel
- [x] **S2:** Pipeline de Áudio — Whisper small, Seletor de vozes, Velocidade TTS
- [x] **S3:** Latência — Keep-alive LLM, Split agressivo, VAD otimizado, Métricas TTFA
- [x] **S4:** Transporte — Backoff exponencial, Keep-alive ping/pong, Session persistence
- [x] **S5:** Robustez — Markdown strip TTS, Timeout LLM 120s, Race protection, Cleanup disconnect, Aviso sessão longa
- [x] **S6:** Deploy — Setup Windows, CI GitHub Actions, Docs atualizados
- [ ] **S7:** Segurança — HTTPS/WSS, Auth da interface
- [ ] **S8:** Conversação — Contexto longo, Persona, Memória
```

### 3c. Atualizar seção Instalação — adicionar Windows

Na seção `## Instalação`, APÓS o bloco `bash setup.sh`, adicionar:

```markdown
**Windows (PowerShell):**

```powershell
git clone https://github.com/quenaisaacdayner-art/openclaw-voice-assistant.git
cd openclaw-voice-assistant
.\setup.ps1
```
```

### 3d. Atualizar arquitetura

Trocar:
```markdown
server_ws.py             ─── Servidor WebSocket S2S (principal)
static/index.html        ─── Frontend Web Audio API
voice_assistant_app.py   ─── Fallback Gradio (APP_MODE=gradio)
voice_assistant_cli.py   ─── CLI terminal
core/                    ─── Módulos compartilhados
```

Por:
```markdown
server_ws.py             ─── Servidor WebSocket S2S (principal)
static/index.html        ─── Frontend Web Audio API + orbe visual
voice_assistant_app.py   ─── Fallback Gradio (legado)
voice_assistant_cli.py   ─── CLI terminal
core/                    ─── Módulos compartilhados (STT, TTS, LLM, config, history)
setup.sh / setup.ps1     ─── Setup automático (Linux/Mac / Windows)
scripts/                 ─── Scripts de execução (3 cenários)
tests/                   ─── ~111 testes automatizados
```

---

## TAREFA 4: Limpeza

### 4a. `.gitignore` — adicionar

Adicionar ao final do `.gitignore`:

```gitignore
# Screenshots soltos (devem ir em docs/ se necessário)
*.png
!docs/*.png

# Environment
.env

# Arquivo morto (código antigo movido pra cá)
arquivo/
```

### 4b. Mover screenshot solto

```bash
# Se existe "Captura de tela 2026-03-23 011330.png" na raiz:
git rm "Captura de tela 2026-03-23 011330.png"
```

Se o arquivo não existir no git, ignorar.

### 4c. Atualizar `prompts/README.md`

Na seção "Ordem de execução", atualizar:

```markdown
## Ordem de execução

1. **S1** ✅ Interface & Interação (8 features)
2. **S2** ✅ Pipeline de Áudio (3 features)
3. **S3** ✅ Latência (4 otimizações)
4. **S4** ✅ Transporte & Conexão (backoff, keepalive, session persistence)
5. **S5** ✅ Robustez (markdown TTS, timeout LLM, race condition, cleanup, aviso sessão)
6. **S6** ✅ Deploy & Distribuição (setup Windows, CI, README, limpeza)
7. S7: Segurança (ver ROADMAP.md)
8. S8: Conversação (ver ROADMAP.md)
```

### 4d. Atualizar `CONTRIBUTING.md` — seção "Rodando localmente"

Na seção do clone, adicionar Windows:
```markdown
# Windows PowerShell:
.\setup.ps1
# ou manualmente:
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Testes

Antes de comitar, rodar:

```bash
python -m pytest tests/ -v
```

Confirmar que **todos 111+ testes passam** (este prompt não muda código funcional, então nada deve quebrar).

---

## Checklist final

- [ ] `setup.ps1` existe na raiz e está correto
- [ ] `.github/workflows/test.yml` atualizado
- [ ] README.md: sem placeholder GIF, roadmap S1-S6, instalação Windows, arquitetura atualizada
- [ ] Screenshot solto removido do git
- [ ] `.gitignore` atualizado
- [ ] `prompts/README.md` atualizado
- [ ] `CONTRIBUTING.md` atualizado com Windows
- [ ] Testes passam: `python -m pytest tests/ -v`
