import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawn, ChildProcess, execFile } from "child_process";
import { readFile, writeFile, access, mkdir, chmod, unlink } from "fs/promises";
import { join } from "path";
import { networkInterfaces } from "os";

// ─── State ──────────────────────────────────────────────────────────────────

let childProc: ChildProcess | null = null;
let startedAt: number | null = null;
let activePort: number | null = null;
let activeHost: string | null = null;
let tunnelProc: ChildProcess | null = null;
let tunnelUrl: string | null = null;

// ─── Helpers ────────────────────────────────────────────────────────────────

const isWindows = process.platform === "win32";

function getLocalIp(): string {
  try {
    const nets = networkInterfaces();
    for (const name of Object.keys(nets)) {
      for (const net of nets[name] || []) {
        if (net.family === "IPv4" && !net.internal) {
          return net.address;
        }
      }
    }
  } catch {}
  return "localhost";
}

async function detectPython(preferred?: string): Promise<string> {
  const candidates = preferred
    ? [preferred]
    : isWindows
      ? ["python3", "python", "py"]
      : ["python3", "python"];

  for (const cmd of candidates) {
    try {
      const version = await new Promise<string>((resolve, reject) => {
        execFile(cmd, ["--version"], { timeout: 5000 }, (err, stdout, stderr) => {
          if (err) return reject(err);
          resolve((stdout || stderr).trim());
        });
      });
      // Check >= 3.10
      const match = version.match(/Python (\d+)\.(\d+)/);
      if (match) {
        const major = parseInt(match[1], 10);
        const minor = parseInt(match[2], 10);
        if (major === 3 && minor >= 10) return cmd;
      }
    } catch {
      // try next
    }
  }
  throw new Error(
    "Python 3.10+ not found. Install from https://python.org"
  );
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

async function waitForServer(host: string, port: number, timeoutMs = 30000): Promise<void> {
  const url = `http://${host === "0.0.0.0" ? "127.0.0.1" : host}:${port}`;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const resp = await fetch(url, { signal: AbortSignal.timeout(2000) });
      if (resp.ok || resp.status === 403) return; // server is up (403 = auth required)
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Server did not start within ${timeoutMs / 1000}s`);
}

function killProcess(proc: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    if (!proc || proc.killed) return resolve();

    proc.once("exit", () => resolve());

    if (isWindows) {
      // On Windows, SIGTERM doesn't work reliably — use taskkill
      if (proc.pid) {
        spawn("taskkill", ["/F", "/T", "/PID", String(proc.pid)], { stdio: "ignore" });
      }
    } else {
      proc.kill("SIGTERM");
    }

    // Force kill after 5s
    setTimeout(() => {
      if (!proc.killed) {
        try { proc.kill("SIGKILL"); } catch { /* already dead */ }
      }
      resolve();
    }, 5000);
  });
}

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

// ─── Plugin Entry ───────────────────────────────────────────────────────────

export default definePluginEntry({
  id: "ova",
  name: "OpenClaw Voice Assistant",
  description: "Speech-to-Speech voice interface — talk to your agent",
  register(api) {
    const pluginDir = api.rootDir;
    const logger = api.logger;

    // Cleanup on gateway shutdown
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

    // ─── /ova command ───────────────────────────────────────────────────────

    api.registerCommand({
      name: "ova",
      description: "Voice Assistant — talk to your agent with speech",
      acceptsArgs: true,
      async handler(ctx) {
        const subcommand = (ctx.args || "start").trim().toLowerCase();

        // ── STATUS ──────────────────────────────────────────────────────
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

        // ── STOP ────────────────────────────────────────────────────────
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

        // ── START ───────────────────────────────────────────────────────
        if (subcommand !== "start") {
          return { text: `Unknown subcommand: ${subcommand}. Use: /ova [start|stop|status]` };
        }

        // Already running?
        if (childProc && !childProc.killed) {
          const displayUrl = tunnelUrl || `http://${activeHost === "0.0.0.0" ? getLocalIp() : activeHost}:${activePort}`;
          return { text: `Voice assistant already running at ${displayUrl}` };
        }

        const config = api.pluginConfig || {};
        const host: string = config.host || "0.0.0.0";
        const port: number = config.port || 7860;

        // 1. Detect Python
        let pythonCmd: string;
        try {
          pythonCmd = await detectPython(config.pythonCommand);
          logger.info(`[OVA] Python found: ${pythonCmd}`);
        } catch (err: any) {
          return { text: err.message };
        }

        // 2. Check venv, run setup if needed
        const venvCheck = isWindows
          ? join(pluginDir, "venv", "Scripts")
          : join(pluginDir, "venv", "bin");

        let freshSetup = false;
        if (!(await pathExists(venvCheck))) {
          logger.info("[OVA] venv not found — running setup...");
          freshSetup = true;
          try {
            await new Promise<void>((resolve, reject) => {
              const setupCmd = isWindows
                ? spawn("powershell", ["-File", join(pluginDir, "setup.ps1")], {
                    cwd: pluginDir,
                    stdio: ["ignore", "pipe", "pipe"],
                  })
                : spawn("bash", [join(pluginDir, "setup.sh")], {
                    cwd: pluginDir,
                    stdio: ["ignore", "pipe", "pipe"],
                  });

              let output = "";
              setupCmd.stdout?.on("data", (d) => { output += d; });
              setupCmd.stderr?.on("data", (d) => { output += d; });
              setupCmd.on("exit", (code) => {
                if (code === 0) resolve();
                else reject(new Error(`Setup failed (exit ${code}):\n${output}`));
              });
              setupCmd.on("error", (err) => reject(err));
            });
            logger.info("[OVA] Setup completed");
          } catch (err: any) {
            return { text: `Setup failed: ${err.message}` };
          }
        }

        // 3. Determine venv Python
        const venvPython = isWindows
          ? join(pluginDir, "venv", "Scripts", "python.exe")
          : join(pluginDir, "venv", "bin", "python");

        // 4. Build command args
        const args = ["-m", "core", "--host", host, "--port", String(port), "--no-browser"];
        if (config.whisperModel) args.push("--whisper", config.whisperModel);
        if (config.ttsEngine) args.push("--tts-engine", config.ttsEngine);

        // 5. Build env vars
        const gatewayPort = api.config?.gateway?.port || 18789;
        const gatewayToken = api.config?.gateway?.auth?.token;
        const env: Record<string, string> = {
          ...process.env as Record<string, string>,
          OPENCLAW_GATEWAY_URL: `http://127.0.0.1:${gatewayPort}/v1/chat/completions`,
        };
        if (gatewayToken) {
          env.OPENCLAW_GATEWAY_TOKEN = gatewayToken;
        }

        // 6. Spawn process
        logger.info(`[OVA] Starting: ${venvPython} ${args.join(" ")}`);
        const proc = spawn(venvPython, args, {
          cwd: pluginDir,
          stdio: ["ignore", "pipe", "pipe"],
          env,
        });

        proc.stdout?.on("data", (data) => {
          logger.info(`[OVA] ${data.toString().trimEnd()}`);
        });
        proc.stderr?.on("data", (data) => {
          logger.error(`[OVA] ${data.toString().trimEnd()}`);
        });
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
        proc.on("error", (err) => {
          logger.error(`[OVA] Process error: ${err.message}`);
        });

        childProc = proc;
        startedAt = Date.now();
        activePort = port;
        activeHost = host;

        // 7. Wait for server to be ready
        // First run: Whisper model download + load can take 60-120s
        const serverTimeout = freshSetup ? 120000 : 30000;
        try {
          await waitForServer(host, port, serverTimeout);
        } catch {
          await killProcess(proc);
          childProc = null;
          startedAt = null;
          return { text: `Voice assistant failed to start (timeout after ${serverTimeout / 1000}s). Check logs.` };
        }

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
      },
    });
  },
});
