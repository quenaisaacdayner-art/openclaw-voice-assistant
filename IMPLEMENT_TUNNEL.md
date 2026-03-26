# IMPLEMENT_TUNNEL.md — Implementar HTTPS Tunnel via Cloudflare Quick Tunnel

---

## Contexto: o problema

Browsers bloqueiam `navigator.mediaDevices.getUserMedia()` (microfone) em páginas HTTP cujo host **NÃO** é `localhost`. Isso é política de segurança do browser, não bug do código.

| Cenário | URL | Mic funciona? |
|---------|-----|:---:|
| Laptop local, browser local | `http://localhost:7860` | OK |
| VPS, browser via SSH tunnel | `http://localhost:7860` | OK |
| Laptop local, **celular** na rede | `http://192.168.X.X:7860` | **BLOQUEADO** |
| VPS, **celular** | `http://IP:7860` | **BLOQUEADO** |

**Solução:** Usar [Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) para criar URL HTTPS gratuita sem conta, sem domínio, sem config. O binário `cloudflared` cria um tunnel HTTPS que dá proxy reverso transparente para o server local.

**Também:** O frontend tem um bug latente — o WebSocket URL está hardcoded como `ws://`, que quebra com qualquer proxy HTTPS (mixed content). Precisa ser protocol-relative.

---

## Arquivos envolvidos

| Arquivo | Ação | Motivo |
|---------|------|--------|
| `static/index.html` | Alterar 1 linha | Fix WS protocol (`ws://` → protocol-relative) |
| `index.ts` | Alterar ~10 linhas + ~90 novas | Tunnel lifecycle (find, download, start, cleanup) |
| `openclaw.plugin.json` | Adicionar ~5 linhas | Campo `tunnel` no configSchema |
| `.gitignore` | Adicionar 1 linha | Ignorar `bin/` (binário cloudflared baixado) |
| `server_ws.py` | **NENHUMA** | Proxy é transparente, auth funciona, WebSocket passa |
| `core/*.py` | **NENHUMA** | Sem impacto |
| `tests/` | **NENHUMA** | Mudanças são aditivas, nada quebra |

---

## Ordem de implementação

Executar nesta ordem exata:

1. **Fase 1** — Fix do WS protocol no frontend (`static/index.html`)
2. **Fase 2.1** — Novos imports em `index.ts`
3. **Fase 2.2** — Novas variáveis de estado em `index.ts`
4. **Fase 2.3** — Nova função `findCloudflared()`
5. **Fase 2.4** — Nova função `downloadCloudflared()`
6. **Fase 2.5** — Nova função `startTunnel()`
7. **Fase 2.6** — Modificar shutdown handler
8. **Fase 2.7** — Modificar STOP handler
9. **Fase 2.8** — Modificar STATUS handler
10. **Fase 2.9** — Modificar "already running" check
11. **Fase 2.10** — Modificar START handler (seções 8 e 9: URL + tunnel + return)
12. **Fase 2.11** — Modificar exit handler do processo Python
13. **Fase 2.12** — Adicionar campo `tunnel` em `openclaw.plugin.json`
14. **Fase 2.13** — Adicionar `bin/` ao `.gitignore`

---

## FASE 1 — Frontend WS Protocol Fix

### Arquivo: `static/index.html`, linha 796

**ANTES:**
```javascript
const WS_URL = `ws://${window.location.host}/ws${_token ? '?token=' + encodeURIComponent(_token) : ''}`;
```

**DEPOIS:**
```javascript
const _wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${_wsProto}//${window.location.host}/ws${_token ? '?token=' + encodeURIComponent(_token) : ''}`;
```

**Por que:** Quando a página é servida via HTTPS (tunnel), `ws://` falha por mixed content. Com a detecção automática, usa `wss://` para HTTPS e `ws://` para HTTP. Retrocompatível — cenários sem tunnel continuam funcionando.

**Contexto ao redor (para localizar):** A linha fica logo após `const _token = _params.get('token') || '';` e antes de `const SAMPLE_RATE = 16000;`.

---

## FASE 2 — Tunnel Integration no `index.ts`

### 2.1 — Imports

**ANTES (linhas 1-5):**
```typescript
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawn, ChildProcess, execFile } from "child_process";
import { readFile, access } from "fs/promises";
import { join } from "path";
import { networkInterfaces } from "os";
```

**DEPOIS:**
```typescript
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawn, ChildProcess, execFile } from "child_process";
import { readFile, writeFile, access, mkdir, chmod, unlink } from "fs/promises";
import { join } from "path";
import { networkInterfaces } from "os";
```

**Mudança:** Adicionados `writeFile`, `mkdir`, `chmod`, `unlink` ao import de `fs/promises`. Necessários para baixar e salvar o binário cloudflared.

---

### 2.2 — State

**ANTES (linhas 9-12):**
```typescript
let childProc: ChildProcess | null = null;
let startedAt: number | null = null;
let activePort: number | null = null;
let activeHost: string | null = null;
```

**DEPOIS:**
```typescript
let childProc: ChildProcess | null = null;
let startedAt: number | null = null;
let activePort: number | null = null;
let activeHost: string | null = null;
let tunnelProc: ChildProcess | null = null;
let tunnelUrl: string | null = null;
```

---

### 2.3 — Nova função: `findCloudflared`

Inserir **depois** da função `killProcess` (após a linha 110), antes do comentário `// ─── Plugin Entry`.

```typescript
async function findCloudflared(pluginDir: string): Promise<string | null> {
  // 1. Check PATH
  try {
    await new Promise<void>((resolve, reject) => {
      execFile("cloudflared", ["version"], { timeout: 5000 }, (err) => {
        if (err) reject(err);
        else resolve();
      });
    });
    return "cloudflared";
  } catch {
    // not in PATH
  }

  // 2. Check pluginDir/bin/
  const localName = isWindows ? "cloudflared.exe" : "cloudflared";
  const localPath = join(pluginDir, "bin", localName);
  if (await pathExists(localPath)) {
    return localPath;
  }

  return null;
}
```

**Lógica:**
1. Tenta `cloudflared version` — se funcionar, está no PATH, retorna `"cloudflared"`.
2. Se não, verifica `pluginDir/bin/cloudflared[.exe]` — se existir, retorna o caminho completo.
3. Se nenhum encontrado, retorna `null`.

**Nota:** No Windows, `execFile("cloudflared", ...)` encontra `cloudflared.exe` no PATH automaticamente (CreateProcess faz isso).

---

### 2.4 — Nova função: `downloadCloudflared`

Inserir logo depois de `findCloudflared`.

```typescript
async function downloadCloudflared(
  pluginDir: string,
  logger: { info: (msg: string) => void; error: (msg: string) => void }
): Promise<string> {
  const binDir = join(pluginDir, "bin");
  await mkdir(binDir, { recursive: true });

  // Map platform + arch to cloudflared binary name
  const platform = process.platform;  // win32, darwin, linux
  const nodeArch = process.arch;      // x64, arm64, ia32, arm
  const cfArch = nodeArch === "arm64" ? "arm64" : "amd64";

  let filename: string;
  let targetName: string;

  if (platform === "win32") {
    filename = "cloudflared-windows-amd64.exe";  // Windows ARM64 uses amd64 via emulation
    targetName = "cloudflared.exe";
  } else if (platform === "darwin") {
    filename = `cloudflared-darwin-${cfArch}.tgz`;
    targetName = "cloudflared";
  } else {
    filename = `cloudflared-linux-${cfArch}`;
    targetName = "cloudflared";
  }

  const url = `https://github.com/cloudflare/cloudflared/releases/latest/download/${filename}`;
  const targetPath = join(binDir, targetName);

  logger.info(`[OVA] Downloading cloudflared...`);

  const resp = await fetch(url, {
    redirect: "follow",
    signal: AbortSignal.timeout(120000),
  });
  if (!resp.ok) {
    throw new Error(`Failed to download cloudflared: HTTP ${resp.status}`);
  }

  const buffer = Buffer.from(await resp.arrayBuffer());

  if (platform === "darwin") {
    // macOS: download is .tgz — extract then cleanup
    const tgzPath = join(binDir, filename);
    await writeFile(tgzPath, buffer);
    await new Promise<void>((resolve, reject) => {
      execFile("tar", ["xzf", tgzPath, "-C", binDir], (err) => {
        if (err) reject(new Error(`Failed to extract cloudflared: ${err.message}`));
        else resolve();
      });
    });
    try { await unlink(tgzPath); } catch {}
  } else {
    await writeFile(targetPath, buffer);
  }

  // Make executable on Unix
  if (platform !== "win32") {
    await chmod(targetPath, 0o755);
  }

  logger.info(`[OVA] cloudflared downloaded to ${targetPath}`);
  return targetPath;
}
```

**Lógica:**
1. Cria `pluginDir/bin/` se não existir.
2. Detecta plataforma e arquitetura. Mapeia para o nome do binário no GitHub Releases.
3. Baixa via `fetch` (Node 18+ nativo). Timeout de 2 minutos. GitHub `/latest/download/` redireciona para a versão atual automaticamente.
4. **macOS**: binário vem em `.tgz` — salva, extrai com `tar`, deleta o `.tgz`.
5. **Linux**: binário direto — salva e `chmod +x`.
6. **Windows**: `.exe` — salva direto.

**Mapa de binários:**

| `process.platform` | `process.arch` | Arquivo baixado | Binário final |
|---|---|---|---|
| `win32` | `x64` | `cloudflared-windows-amd64.exe` | `bin/cloudflared.exe` |
| `win32` | `arm64` | `cloudflared-windows-amd64.exe` | `bin/cloudflared.exe` |
| `linux` | `x64` | `cloudflared-linux-amd64` | `bin/cloudflared` |
| `linux` | `arm64` | `cloudflared-linux-arm64` | `bin/cloudflared` |
| `darwin` | `x64` | `cloudflared-darwin-amd64.tgz` | `bin/cloudflared` |
| `darwin` | `arm64` | `cloudflared-darwin-arm64.tgz` | `bin/cloudflared` |

---

### 2.5 — Nova função: `startTunnel`

Inserir logo depois de `downloadCloudflared`.

```typescript
async function startTunnel(
  port: number,
  cfPath: string,
  logger: { info: (msg: string) => void; error: (msg: string) => void }
): Promise<{ proc: ChildProcess; url: string }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(cfPath, ["tunnel", "--url", `http://localhost:${port}`], {
      stdio: ["ignore", "pipe", "pipe"],
    });

    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        proc.kill();
        reject(new Error("Tunnel did not produce URL within 30s"));
      }
    }, 30000);

    const urlRegex = /https:\/\/[-a-zA-Z0-9]+\.trycloudflare\.com/;

    proc.stderr?.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      logger.info(`[OVA:tunnel] ${text.trimEnd()}`);
      if (!settled) {
        const match = text.match(urlRegex);
        if (match) {
          settled = true;
          clearTimeout(timer);
          resolve({ proc, url: match[0] });
        }
      }
    });

    proc.stdout?.on("data", (chunk: Buffer) => {
      logger.info(`[OVA:tunnel] ${chunk.toString().trimEnd()}`);
    });

    proc.on("error", (err) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(err);
      }
    });

    proc.on("exit", (code) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(new Error(`cloudflared exited (code ${code}) before tunnel was ready`));
      }
    });
  });
}
```

**Lógica:**
1. Spawna `cloudflared tunnel --url http://localhost:{port}`.
2. cloudflared printa a URL HTTPS no **stderr** (usa zerolog com console writer para stderr).
3. Parseia cada chunk de stderr com regex para capturar `https://xxx.trycloudflare.com`.
4. Quando encontra a URL, resolve a Promise com `{ proc, url }`.
5. Se o processo morre antes de produzir URL, rejeita.
6. Se 30 segundos passam sem URL, mata o processo e rejeita.
7. A função **retorna** o ChildProcess — o caller é responsável por atribuir a `tunnelProc` e configurar o exit handler de cleanup.

**Sobre o formato do output do cloudflared no stderr:**
```
2026-03-25T10:00:00Z INF +-------------------------------------------------------------------+
2026-03-25T10:00:00Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):
2026-03-25T10:00:00Z INF |  https://banana-river.trycloudflare.com
2026-03-25T10:00:00Z INF +-------------------------------------------------------------------+
```

A regex `/https:\/\/[-a-zA-Z0-9]+\.trycloudflare\.com/` encontra a URL independente dos caracteres ao redor (`|`, espaços, timestamps).

---

### 2.6 — Modificar shutdown handler

**ANTES (linhas 123-130):**
```typescript
    api.on("shutdown", async () => {
      if (childProc) {
        logger.info("[OVA] Gateway shutting down — stopping voice assistant");
        await killProcess(childProc);
        childProc = null;
        startedAt = null;
      }
    });
```

**DEPOIS:**
```typescript
    api.on("shutdown", async () => {
      if (tunnelProc) {
        await killProcess(tunnelProc);
        tunnelProc = null;
        tunnelUrl = null;
      }
      if (childProc) {
        logger.info("[OVA] Gateway shutting down — stopping voice assistant");
        await killProcess(childProc);
        childProc = null;
        startedAt = null;
      }
    });
```

**Por que tunnel primeiro:** Matar o tunnel antes do server evita que o tunnel tente reconectar a um server que está morrendo.

---

### 2.7 — Modificar STOP handler

**ANTES (linhas 159-169):**
```typescript
        if (subcommand === "stop") {
          if (!childProc || childProc.killed) {
            return { text: "Voice assistant is not running." };
          }
          await killProcess(childProc);
          childProc = null;
          startedAt = null;
          activePort = null;
          activeHost = null;
          return { text: "Voice assistant stopped." };
        }
```

**DEPOIS:**
```typescript
        if (subcommand === "stop") {
          if (!childProc || childProc.killed) {
            return { text: "Voice assistant is not running." };
          }
          if (tunnelProc) {
            await killProcess(tunnelProc);
            tunnelProc = null;
            tunnelUrl = null;
          }
          await killProcess(childProc);
          childProc = null;
          startedAt = null;
          activePort = null;
          activeHost = null;
          return { text: "Voice assistant stopped." };
        }
```

---

### 2.8 — Modificar STATUS handler

**ANTES (linhas 142-156):**
```typescript
        if (subcommand === "status") {
          if (!childProc || childProc.killed) {
            return { text: "Voice assistant is not running." };
          }
          const uptime = Math.round((Date.now() - (startedAt || 0)) / 1000);
          const mins = Math.floor(uptime / 60);
          const secs = uptime % 60;
          return { text: [
            `Voice Assistant running`,
            `  Port: ${activePort}`,
            `  Host: ${activeHost}`,
            `  PID:  ${childProc.pid}`,
            `  Uptime: ${mins}m ${secs}s`,
          ].join("\n") };
        }
```

**DEPOIS:**
```typescript
        if (subcommand === "status") {
          if (!childProc || childProc.killed) {
            return { text: "Voice assistant is not running." };
          }
          const uptime = Math.round((Date.now() - (startedAt || 0)) / 1000);
          const mins = Math.floor(uptime / 60);
          const secs = uptime % 60;
          return { text: [
            `Voice Assistant running`,
            `  Port: ${activePort}`,
            `  Host: ${activeHost}`,
            `  PID:  ${childProc.pid}`,
            `  Uptime: ${mins}m ${secs}s`,
            ...(tunnelUrl ? [`  Tunnel: ${tunnelUrl}`] : []),
          ].join("\n") };
        }
```

**Mudança:** Uma linha adicionada com spread condicional — mostra a URL do tunnel se ativo.

---

### 2.9 — Modificar "already running" check

**ANTES (linhas 177-180):**
```typescript
        if (childProc && !childProc.killed) {
          const displayHost = activeHost === "0.0.0.0" ? getLocalIp() : activeHost;
          return { text: `Voice assistant already running at http://${displayHost}:${activePort}` };
        }
```

**DEPOIS:**
```typescript
        if (childProc && !childProc.killed) {
          const displayUrl = tunnelUrl || `http://${activeHost === "0.0.0.0" ? getLocalIp() : activeHost}:${activePort}`;
          return { text: `Voice assistant already running at ${displayUrl}` };
        }
```

**Mudança:** Mostra a URL do tunnel (HTTPS) se ativo, senão mostra a URL HTTP como antes.

---

### 2.10 — Modificar START handler (seções 8 e 9)

Esta é a mudança principal. Substituir TODO o bloco desde o comentário `// 8. Read auth token and build URL` até o final do return (linhas 292-320).

**ANTES (linhas 292-320):**
```typescript
        // 8. Read auth token and build URL
        let url: string;
        const isLoopback = host === "127.0.0.1" || host === "localhost" || host === "::1";

        if (isLoopback) {
          url = `http://localhost:${port}`;
        } else {
          // Remote — read .ova_token
          let token = "";
          try {
            token = (await readFile(join(pluginDir, ".ova_token"), "utf-8")).trim();
          } catch {
            logger.error("[OVA] Could not read .ova_token");
          }
          const displayHost = host === "0.0.0.0" ? getLocalIp() : host;
          url = token
            ? `http://${displayHost}:${port}?token=${token}`
            : `http://${displayHost}:${port}`;
        }

        // 9. Return message
        return { text: [
          "\uD83C\uDF99\uFE0F Voice Assistant active",
          "",
          `\uD83D\uDD17 ${url}`,
          "",
          "Open the link in your browser to talk.",
          "To stop: /ova stop",
        ].join("\n") };
```

**DEPOIS:**
```typescript
        // 8. Read auth token and build URL
        const isLoopback = host === "127.0.0.1" || host === "localhost" || host === "::1";
        let url: string;
        let tunnelActive = false;

        if (isLoopback) {
          url = `http://localhost:${port}`;
        } else {
          // Non-loopback — read auth token
          let token = "";
          try {
            token = (await readFile(join(pluginDir, ".ova_token"), "utf-8")).trim();
          } catch {
            logger.error("[OVA] Could not read .ova_token");
          }

          // 9. Start HTTPS tunnel (unless disabled via config)
          if (config.tunnel !== false) {
            try {
              let cfPath = await findCloudflared(pluginDir);
              if (!cfPath) {
                logger.info("[OVA] cloudflared not found — downloading...");
                cfPath = await downloadCloudflared(pluginDir, logger);
              }
              const result = await startTunnel(port, cfPath, logger);
              tunnelProc = result.proc;
              tunnelUrl = token ? `${result.url}?token=${token}` : result.url;
              url = tunnelUrl;
              tunnelActive = true;
              logger.info(`[OVA] Tunnel active: ${tunnelUrl}`);

              // Cleanup when tunnel process dies
              result.proc.on("exit", (code) => {
                logger.info(`[OVA:tunnel] Exited (code ${code})`);
                if (tunnelProc === result.proc) {
                  tunnelProc = null;
                  tunnelUrl = null;
                }
              });
            } catch (err: any) {
              logger.error(`[OVA] Tunnel failed: ${err.message} — falling back to HTTP`);
            }
          }

          // Fallback: plain HTTP (tunnel disabled or failed)
          if (!tunnelActive) {
            const displayHost = host === "0.0.0.0" ? getLocalIp() : host;
            url = token
              ? `http://${displayHost}:${port}?token=${token}`
              : `http://${displayHost}:${port}`;
          }
        }

        // 10. Return message
        const lines = [
          "\uD83C\uDF99\uFE0F Voice Assistant active",
          "",
          `\uD83D\uDD17 ${url}`,
        ];
        if (tunnelActive) {
          lines.push("", "\uD83D\uDD12 HTTPS tunnel active (Cloudflare)");
        } else if (!isLoopback) {
          lines.push("", "\u26A0\uFE0F No HTTPS tunnel \u2014 microphone won't work on remote devices.");
        }
        lines.push("", "Open the link in your browser to talk.", "To stop: /ova stop");

        return { text: lines.join("\n") };
```

**Fluxo do novo código:**

```
isLoopback?
  SIM → url = http://localhost:PORT (sem tunnel, sem token)
  NAO →
    Lê token de .ova_token
    config.tunnel !== false?
      SIM →
        Encontra cloudflared (PATH ou bin/)
        Não encontrou? Baixa automaticamente
        Spawna tunnel → captura URL HTTPS
        url = https://xxx.trycloudflare.com?token=yyy
        tunnelActive = true
        (Se qualquer passo falhar → catch → log → fallback)
      NAO → fallback
    !tunnelActive?
      url = http://IP:PORT?token=yyy (fallback HTTP)
```

**Mensagem retornada nos 3 cenários:**

**Loopback (cenários 1 e 2):**
```
🎙️ Voice Assistant active

🔗 http://localhost:7860

Open the link in your browser to talk.
To stop: /ova stop
```

**Tunnel ativo (cenários 3 e 4):**
```
🎙️ Voice Assistant active

🔗 https://banana-river.trycloudflare.com?token=abc123

🔒 HTTPS tunnel active (Cloudflare)

Open the link in your browser to talk.
To stop: /ova stop
```

**Tunnel falhou/desabilitado (fallback):**
```
🎙️ Voice Assistant active

🔗 http://192.168.1.100:7860?token=abc123

⚠️ No HTTPS tunnel — microphone won't work on remote devices.

Open the link in your browser to talk.
To stop: /ova stop
```

---

### 2.11 — Modificar exit handler do processo Python

**ANTES (linhas 264-272):**
```typescript
        proc.on("exit", (code) => {
          logger.info(`[OVA] Process exited with code ${code}`);
          if (childProc === proc) {
            childProc = null;
            startedAt = null;
            activePort = null;
            activeHost = null;
          }
        });
```

**DEPOIS:**
```typescript
        proc.on("exit", (code) => {
          logger.info(`[OVA] Process exited with code ${code}`);
          if (childProc === proc) {
            childProc = null;
            startedAt = null;
            activePort = null;
            activeHost = null;
            // Kill tunnel if server dies (no point keeping it alive)
            if (tunnelProc) {
              killProcess(tunnelProc);
              tunnelProc = null;
              tunnelUrl = null;
            }
          }
        });
```

**Por que:** Se o server Python morre, o tunnel fica apontando pra nada. Melhor matar ambos.

---

### 2.12 — Config schema: `openclaw.plugin.json`

**ANTES:**
```json
{
  "id": "ova",
  "name": "OpenClaw Voice Assistant",
  "description": "Speech-to-Speech voice interface — talk to your agent with Whisper STT + streaming TTS",
  "version": "0.1.0",
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "port": {
        "type": "number",
        "description": "Port for the voice assistant server (default: 7860)"
      },
      "host": {
        "type": "string",
        "description": "Host to bind (default: 0.0.0.0 for remote access, 127.0.0.1 for local only)"
      },
      "whisperModel": {
        "type": "string",
        "enum": ["tiny", "small"],
        "description": "Whisper model size (tiny = fast, small = accurate)"
      },
      "ttsEngine": {
        "type": "string",
        "enum": ["edge", "piper", "kokoro"],
        "description": "TTS engine"
      },
      "pythonCommand": {
        "type": "string",
        "description": "Python executable (default: auto-detect python3/python)"
      }
    }
  },
  "uiHints": {
    "port": { "label": "Port", "placeholder": "7860" },
    "host": { "label": "Host", "placeholder": "0.0.0.0" },
    "whisperModel": { "label": "Whisper Model" },
    "ttsEngine": { "label": "TTS Engine" },
    "pythonCommand": { "label": "Python Command", "advanced": true }
  }
}
```

**DEPOIS:**
```json
{
  "id": "ova",
  "name": "OpenClaw Voice Assistant",
  "description": "Speech-to-Speech voice interface — talk to your agent with Whisper STT + streaming TTS",
  "version": "0.1.0",
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "port": {
        "type": "number",
        "description": "Port for the voice assistant server (default: 7860)"
      },
      "host": {
        "type": "string",
        "description": "Host to bind (default: 0.0.0.0 for remote access, 127.0.0.1 for local only)"
      },
      "whisperModel": {
        "type": "string",
        "enum": ["tiny", "small"],
        "description": "Whisper model size (tiny = fast, small = accurate)"
      },
      "ttsEngine": {
        "type": "string",
        "enum": ["edge", "piper", "kokoro"],
        "description": "TTS engine"
      },
      "pythonCommand": {
        "type": "string",
        "description": "Python executable (default: auto-detect python3/python)"
      },
      "tunnel": {
        "type": "boolean",
        "description": "HTTPS tunnel via Cloudflare (auto when host is not localhost, set false to disable)"
      }
    }
  },
  "uiHints": {
    "port": { "label": "Port", "placeholder": "7860" },
    "host": { "label": "Host", "placeholder": "0.0.0.0" },
    "whisperModel": { "label": "Whisper Model" },
    "ttsEngine": { "label": "TTS Engine" },
    "pythonCommand": { "label": "Python Command", "advanced": true },
    "tunnel": { "label": "HTTPS Tunnel", "advanced": true }
  }
}
```

**Mudança:** Adicionado `tunnel` em `properties` e `uiHints`. Default implícito é `true` (o código checa `config.tunnel !== false`).

---

### 2.13 — `.gitignore`

**Adicionar no final do arquivo:**
```
# cloudflared binary (auto-downloaded)
bin/
```

**Por que:** O binário cloudflared (~40MB) é baixado automaticamente em `pluginDir/bin/`. Não deve ser commitado.

---

## Edge cases e fallbacks

| Situação | Comportamento esperado |
|---|---|
| `cloudflared` não no PATH e download falha (sem internet, GitHub down) | Log de erro. Fallback para URL HTTP + warning na mensagem. Server Python continua funcionando normalmente. |
| `cloudflared` spawna mas não produz URL em 30s | Timeout. Processo cloudflared é matado. Fallback para URL HTTP + warning. |
| `cloudflared` morre depois do tunnel estar ativo | Exit handler limpa `tunnelProc` e `tunnelUrl`. Server Python continua rodando. URL HTTPS para de funcionar, mas server está acessível via HTTP direto. |
| Server Python morre | Exit handler mata o tunnel também. Tudo limpo. |
| `/ova stop` | Mata tunnel primeiro, depois server Python. Estado limpo. |
| Gateway shutdown | Mata tunnel primeiro, depois server Python. Estado limpo. |
| `config.tunnel === false` | Tunnel nunca inicia. Comportamento idêntico ao atual (URL HTTP). |
| Host é loopback (`127.0.0.1`, `localhost`, `::1`) | Tunnel nunca inicia. URL `http://localhost:PORT` como hoje. |
| URL do tunnel com token | Query param `?token=xxx` é preservado pelo cloudflared (confirmado: proxy HTTP transparente). |
| macOS binary (`.tgz`) | Download `.tgz`, extrai com `tar xzf`, deleta `.tgz`, `chmod +x` no binário. |
| Windows ARM64 | Usa `cloudflared-windows-amd64.exe` (Windows ARM64 emula amd64). |
| `bin/` já existe com versão antiga | `pathExists` encontra e usa. Não re-baixa. Não verifica versão (desnecessário para quick tunnel). |

---

## O que NÃO tocar

- `server_ws.py` — **ZERO mudanças.** O proxy do cloudflared é transparente. O auth funciona (query params passam). O WebSocket funciona (cloudflared faz proxy nativo de WS).
- `core/*.py` — Sem impacto.
- `tests/` — Nenhum teste quebra. Mudanças são aditivas.
- `scripts/*.sh` / `scripts/*.ps1` — Tunnel é feature do plugin (`index.ts`), não dos scripts manuais.
- `package.json` — Sem nova dependência. `cloudflared` é binário externo, não pacote npm.
- Funções auxiliares existentes no `index.ts` que NÃO mudam: `getLocalIp()`, `detectPython()`, `pathExists()`, `waitForServer()`, `killProcess()`.

---

## Checklist de verificação pós-implementação

### `static/index.html`
- [ ] Linha 796 usa `_wsProto` (protocol-relative), NÃO `ws://` hardcoded
- [ ] `_wsProto` é `'wss:'` quando `location.protocol === 'https:'`, senão `'ws:'`
- [ ] Nenhuma outra linha do HTML foi alterada

### `index.ts`
- [ ] Imports incluem `writeFile`, `mkdir`, `chmod`, `unlink` de `fs/promises`
- [ ] `tunnelProc` e `tunnelUrl` declarados como state global
- [ ] `findCloudflared()` existe e checa PATH depois `pluginDir/bin/`
- [ ] `downloadCloudflared()` existe, detecta plataforma, baixa, extrai (macOS), chmod (Unix)
- [ ] `startTunnel()` existe, spawna cloudflared, parseia URL do stderr, timeout 30s
- [ ] Shutdown handler mata `tunnelProc` ANTES de `childProc`
- [ ] STOP handler mata `tunnelProc` e limpa `tunnelUrl`
- [ ] STATUS handler mostra `Tunnel: URL` se ativo
- [ ] "Already running" mostra `tunnelUrl` se disponível
- [ ] START handler: tunnel só inicia se `!isLoopback && config.tunnel !== false`
- [ ] START handler: se tunnel falha, fallback para URL HTTP com warning
- [ ] START handler: exit handler do tunnel limpa `tunnelProc` e `tunnelUrl`
- [ ] Exit handler do Python mata tunnel se ativo
- [ ] Todos os `return` dentro do handler continuam sendo `{ text: "..." }`
- [ ] `killProcess()` NÃO foi modificada (já é genérica)

### `openclaw.plugin.json`
- [ ] Campo `tunnel` (boolean) em `configSchema.properties`
- [ ] Campo `tunnel` em `uiHints` com `"advanced": true`
- [ ] `additionalProperties: false` — confirmar que `tunnel` está listado

### `.gitignore`
- [ ] `bin/` adicionado

### Geral
- [ ] **Nenhum arquivo Python foi modificado**
- [ ] `python -m pytest tests/ -v` — todos os testes passam
- [ ] `bin/` não está no git (`git status` não mostra `bin/`)
