# S7: Segurança — PROMPT COMPLETO

> Prompt unificado. Leia e execute TUDO.
> Pré-requisito: S1-S6 completos
> Arquivos a modificar: `server_ws.py`, `static/index.html`, `core/config.py`
> Arquivos a criar: `docs/SECURITY.md`

---

## Visão geral

7 fixes de segurança + 1 documento. Nenhuma feature nova — só proteção do que já existe. Implementar nesta ordem:

1. Auth por token (modelo OpenClaw/Jupyter)
2. XSS fix — sanitizar markdown
3. Rate limit — texto e áudio
4. Buffer limit — áudio máximo 10MB
5. Input validation — texto máximo 2000 chars no server
6. Erros genéricos pro client
7. marked.js local (remover CDN)
8. docs/SECURITY.md — documentação

---

## TAREFA 1: Auth por token (modelo OpenClaw/Jupyter)

### Lógica

- **Localhost** (`127.0.0.1`, `localhost`, `::1`): SEM autenticação — quem acessa o terminal já controla a máquina
- **Não-localhost** (`0.0.0.0` ou IP específico): EXIGE token
- Token gerado automaticamente no primeiro startup, salvo em `.ova_token` na raiz do projeto
- Printado no terminal como URL completa: `http://<host>:<port>?token=abc123`
- Frontend passa o token via query param no WebSocket: `ws://host:port/ws?token=abc123`
- Server valida no handshake do WebSocket. Rejeita com 403 se token errado

### Backend (`server_ws.py`)

**Adicionar no topo (após imports existentes):**

```python
import secrets
from urllib.parse import parse_qs, urlparse
```

**Adicionar função de token (antes de `app = FastAPI()`):**

```python
# ─── Auth ─────────────────────────────────────────────────────────────────────

_TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ova_token")

def _is_loopback(host: str) -> bool:
    """Verifica se o host é loopback (não precisa de auth)."""
    return host in ("127.0.0.1", "localhost", "::1", "")

def _load_or_create_token() -> str:
    """Carrega token existente ou gera um novo."""
    if os.path.exists(_TOKEN_FILE):
        with open(_TOKEN_FILE, "r") as f:
            token = f.read().strip()
            if token:
                return token
    token = secrets.token_urlsafe(32)
    with open(_TOKEN_FILE, "w") as f:
        f.write(token)
    return token

_server_host = os.environ.get("SERVER_HOST", "127.0.0.1")
_auth_required = not _is_loopback(_server_host)
_auth_token = _load_or_create_token() if _auth_required else None
```

**Modificar o endpoint `/ws`:**

Antes da linha `await ws.accept()`, adicionar validação:

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Auth check (só exigido em não-localhost)
    if _auth_required:
        query = parse_qs(str(ws.query_params))
        # parse_qs do scope pode não funcionar — usar ws.scope
        raw_qs = ws.scope.get("query_string", b"").decode()
        params = parse_qs(raw_qs)
        client_token = params.get("token", [None])[0]
        if client_token != _auth_token:
            await ws.close(code=4003, reason="Token inválido ou ausente")
            return

    await ws.accept()
    # ... resto do código continua igual
```

**Modificar a seção `if __name__`:**

Após imprimir o banner, adicionar:

```python
    if _auth_required:
        print(f"  🔒 Auth: token (não-localhost)")
        print(f"  🔗 http://{host}:{port}?token={_auth_token}")
    else:
        print(f"  🔓 Auth: nenhuma (localhost)")
        print(f"  🔗 http://{host}:{port}")
```

**Adicionar `.ova_token` ao `.gitignore`:**

```gitignore
# Auth token (auto-gerado)
.ova_token
```

### Frontend (`static/index.html`)

Modificar a constante `WS_URL`:

```javascript
// ─── Config ──────────────────────────────────────────
const _params = new URLSearchParams(window.location.search);
const _token = _params.get('token') || '';
const WS_URL = `ws://${window.location.host}/ws${_token ? '?token=' + encodeURIComponent(_token) : ''}`;
```

Modificar `connect()` para tratar rejeição de auth. No `ws.onclose`, diferenciar código 4003:

```javascript
ws.onclose = (event) => {
    stopKeepAlive();
    
    // Auth falhou — não reconectar
    if (event.code === 4003) {
        setStatus('disconnected', 'Não autorizado');
        bottomStatus.textContent = 'Token inválido. Verifique a URL.';
        showError('🔒 Acesso negado. Use a URL completa com token do terminal.');
        return;  // Não reconectar
    }
    
    setStatus('disconnected', 'Desconectado');
    reconnectAttempts++;
    reconnectDelay = Math.min(RECONNECT_MIN * Math.pow(RECONNECT_FACTOR, reconnectAttempts - 1), RECONNECT_MAX);
    bottomStatus.textContent = `Reconectando em ${Math.round(reconnectDelay / 1000)}s... (tentativa ${reconnectAttempts})`;
    reconnectTimer = setTimeout(connect, reconnectDelay);
};
```

### Endpoint `/` (index.html) — proteger também

Adicionar middleware ou check no endpoint GET `/`:

```python
@app.get("/")
async def index(request: Request):
    # Se auth é necessário, verificar token na query string
    if _auth_required:
        token = request.query_params.get("token")
        if token != _auth_token:
            return Response(
                content="<h1>🔒 Acesso negado</h1><p>Use a URL completa com token (printada no terminal).</p>",
                media_type="text/html",
                status_code=403
            )
    return FileResponse("static/index.html")
```

Adicionar import no topo: `from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request` e `from fastapi.responses import FileResponse, Response`

---

## TAREFA 2: XSS fix — sanitizar markdown

O `marked.js` converte markdown em HTML mas NÃO sanitiza por padrão. Se o LLM devolver `<script>`, executa no browser.

### Frontend (`static/index.html`)

**Opção escolhida:** usar o renderer do marked pra escapar tags HTML perigosas.

Substituir o bloco de configuração do marked:

```javascript
// Marked.js config — sanitizar HTML pra prevenir XSS
if (typeof marked !== 'undefined') {
    const renderer = new marked.Renderer();
    const _origHtml = renderer.html.bind(renderer);
    // Escapar qualquer HTML raw que o LLM insira
    renderer.html = function(text) {
        const input = typeof text === 'object' ? text.text || text.raw || '' : text;
        const d = document.createElement('div');
        d.textContent = input;
        return d.innerHTML;
    };
    marked.setOptions({
        breaks: true,
        gfm: true,
        renderer: renderer,
    });
}
```

**Testar mentalmente:** Se o LLM responder `<script>alert(1)</script>`, o `renderer.html` escapa pra `&lt;script&gt;...` e aparece como texto no chat, não executa.

---

## TAREFA 3: Rate limit — texto e áudio

### Backend (`server_ws.py`)

Adicionar variáveis de rate limit dentro do `websocket_endpoint`, após as variáveis existentes:

```python
    # Rate limiting
    _last_text_time = 0.0
    _TEXT_COOLDOWN = 2.0  # segundos entre mensagens de texto
    _last_speech_time = 0.0
    _SPEECH_COOLDOWN = 1.0  # segundos entre speech_end
```

**No handler de `text_input`:**

```python
                elif data["type"] == "text_input":
                    user_text = data.get("text", "").strip()
                    now = time.time()
                    if now - _last_text_time < _TEXT_COOLDOWN:
                        await send_json_msg({
                            "type": "error",
                            "message": "Aguarde antes de enviar outra mensagem."
                        })
                        continue
                    _last_text_time = now
                    if user_text and not processing:
                        process_task = asyncio.create_task(process_text(user_text))
```

**No handler de `vad_event` / `speech_end`:**

```python
                if data["type"] == "vad_event" and data["event"] == "speech_end":
                    if len(audio_buffer) < 1600:  # <50ms = ruido
                        audio_buffer.clear()
                        continue
                    
                    now = time.time()
                    if now - _last_speech_time < _SPEECH_COOLDOWN:
                        audio_buffer.clear()
                        continue
                    _last_speech_time = now

                    if processing_lock.locked():
                        # ... resto igual
```

---

## TAREFA 4: Buffer limit — áudio máximo 10MB

### Backend (`server_ws.py`)

Adicionar constante no topo (após `LLM_TIMEOUT`):

```python
AUDIO_BUFFER_MAX = 10 * 1024 * 1024  # 10MB (~5 min de áudio 16kHz 16-bit mono)
```

Modificar o handler de bytes no receive loop:

```python
            if "bytes" in message:
                if not processing:
                    audio_buffer.extend(message["bytes"])
                    # Proteção contra buffer infinito
                    if len(audio_buffer) > AUDIO_BUFFER_MAX:
                        print(f"[WARN] Audio buffer excedeu {AUDIO_BUFFER_MAX // (1024*1024)}MB — descartando")
                        audio_buffer.clear()
                elif cancel_event.is_set():
                    audio_buffer.extend(message["bytes"])
                    if len(audio_buffer) > AUDIO_BUFFER_MAX:
                        audio_buffer.clear()
```

---

## TAREFA 5: Input validation — texto máximo 2000 chars no server

### Backend (`server_ws.py`)

No handler de `text_input`, truncar server-side (o frontend já tem maxlength=2000, mas o server deve validar independente):

```python
                elif data["type"] == "text_input":
                    user_text = data.get("text", "")[:2000].strip()
                    # ... resto do rate limit e processamento
```

No handler de `restore_history`, já existe `msg["content"][:5000]` — OK, manter.

---

## TAREFA 6: Erros genéricos pro client

### Backend (`server_ws.py`)

Em `process_speech()` e `process_text()`, no bloco except, mudar:

**Antes:**
```python
            except Exception as e:
                traceback.print_exc()
                await send_json_msg({
                    "type": "error",
                    "message": f"Erro interno: {e}"
                })
```

**Depois (ambas funções):**
```python
            except Exception:
                traceback.print_exc()
                await send_json_msg({
                    "type": "error",
                    "message": "Erro interno. Tente novamente."
                })
```

Remover `as e` e não incluir detalhes do erro na mensagem pro client. O `traceback.print_exc()` já loga no server.

---

## TAREFA 7: marked.js local (remover CDN)

### Download

Baixar marked.min.js e salvar em `static/`:

```bash
curl -o static/marked.min.js "https://cdn.jsdelivr.net/npm/marked@15.0.7/marked.min.js"
```

Se `curl` não estiver disponível (Windows), usar:
```powershell
Invoke-WebRequest -Uri "https://cdn.jsdelivr.net/npm/marked@15.0.7/marked.min.js" -OutFile "static/marked.min.js"
```

### Frontend (`static/index.html`)

Substituir:
```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
```

Por:
```html
<script src="/static/marked.min.js"></script>
```

---

## TAREFA 8: docs/SECURITY.md

Criar `docs/SECURITY.md`:

```markdown
# Segurança — OpenClaw Voice Assistant

## Modelo de autenticação

| Cenário | Host | Auth | Comportamento |
|---------|------|------|---------------|
| Local (padrão) | `127.0.0.1` | Nenhuma | Acesso direto — mesmo modelo do OpenClaw |
| VPS / Rede | `0.0.0.0` | Token auto-gerado | URL com token printada no terminal |

### Como funciona

1. Se `SERVER_HOST` é loopback → sem auth (quem acessa o terminal já controla a máquina)
2. Se `SERVER_HOST` não é loopback → token gerado automaticamente em `.ova_token`
3. Terminal printa: `http://<host>:<port>?token=<token>`
4. Token passado via query param no WebSocket handshake
5. Conexão recusada com código 4003 se token inválido

### Regenerar token

Deletar `.ova_token` e reiniciar o server. Um novo token será gerado.

## Proteções implementadas

| Proteção | Descrição |
|----------|-----------|
| XSS | HTML no markdown é escapado (marked.js renderer customizado) |
| Rate limit | 2s entre mensagens de texto, 1s entre speech_end |
| Buffer limit | Áudio máximo 10MB (~5 min) — descartado se exceder |
| Input truncation | Texto truncado em 2000 chars server-side |
| Erros genéricos | Detalhes de erro só nos logs do server, client recebe mensagem genérica |
| CDN removida | marked.js servido localmente (sem dependência externa em runtime) |

## Riscos aceitos (documentados)

### Prompt injection via voz

Alguém pode falar comandos que manipulam o LLM ("ignore suas instruções anteriores..."). Isso é inerente a qualquer aplicação LLM e não tem solução simples. Mitigação: o assistente não tem acesso a ferramentas perigosas (não executa código, não acessa filesystem).

### HTTP em localhost

Tráfego em localhost não passa pela rede — risco de interceptação é negligível. Para acesso remoto, usar SSH tunnel:

```bash
ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>
```

### HTTPS para produção

Se quiser expor diretamente na internet (sem SSH tunnel), use nginx como reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name voice.seudominio.com;

    ssl_certificate /etc/letsencrypt/live/voice.seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/voice.seudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

O navegador exige HTTPS para acessar o microfone (exceto em localhost).

### Arquivo temporário STT

O Whisper salva WAV temporário em `/tmp/` com nome aleatório, deletado imediatamente após transcrição. Risco mínimo em máquina single-user.
```

---

## Testes

Após implementar, rodar:

```bash
python -m pytest tests/ -v
```

Todos os testes existentes devem continuar passando (nenhum depende de auth — os testes usam `TestClient` que conecta em localhost).

### Testes manuais

1. **Auth localhost:** Rodar `python server_ws.py` (default `127.0.0.1`) → acessar `http://127.0.0.1:7860` → funciona sem token ✅
2. **Auth VPS:** Rodar com `SERVER_HOST=0.0.0.0 python server_ws.py` → terminal mostra URL com token → acessar sem token → 403 ✅ → acessar com token → funciona ✅
3. **XSS:** Digitar "responda com `<script>alert(1)</script>`" → deve aparecer como TEXTO no chat, não executar ✅
4. **Rate limit:** Enviar 3 mensagens de texto rápido → 2ª/3ª bloqueadas com erro ✅
5. **Buffer:** Falar por mais de 5 minutos sem pausa → buffer limpa sem crash ✅
6. **Erro genérico:** Desligar o gateway OpenClaw e falar → mensagem "Erro interno. Tente novamente." sem stack trace ✅

---

## Checklist final

- [ ] Auth por token implementado (server + frontend + .gitignore)
- [ ] XSS: marked renderer escapa HTML
- [ ] Rate limit: 2s texto, 1s speech
- [ ] Buffer limit: 10MB áudio
- [ ] Input validation: 2000 chars server-side
- [ ] Erros genéricos (sem detalhes pro client)
- [ ] marked.js local em static/
- [ ] `docs/SECURITY.md` criado
- [ ] Testes passam: `python -m pytest tests/ -v`
- [ ] `.ova_token` no `.gitignore`
