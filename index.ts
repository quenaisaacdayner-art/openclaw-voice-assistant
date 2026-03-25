import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "@sinclair/typebox";
import { spawn, ChildProcess, execFile } from "child_process";
import { readFile, access } from "fs/promises";
import { join } from "path";
import { networkInterfaces } from "os";

// ─── State ──────────────────────────────────────────────────────────────────

let childProc: ChildProcess | null = null;
let startedAt: number | null = null;
let activePort: number | null = null;
let activeHost: string | null = null;

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
      args: Type.Optional(Type.String()),
      async handler(rawArgs) {
        const subcommand = (rawArgs || "start").trim().toLowerCase();

        // ── STATUS ──────────────────────────────────────────────────────
        if (subcommand === "status") {
          if (!childProc || childProc.killed) {
            return "Voice assistant is not running.";
          }
          const uptime = Math.round((Date.now() - (startedAt || 0)) / 1000);
          const mins = Math.floor(uptime / 60);
          const secs = uptime % 60;
          return [
            `Voice Assistant running`,
            `  Port: ${activePort}`,
            `  Host: ${activeHost}`,
            `  PID:  ${childProc.pid}`,
            `  Uptime: ${mins}m ${secs}s`,
          ].join("\n");
        }

        // ── STOP ────────────────────────────────────────────────────────
        if (subcommand === "stop") {
          if (!childProc || childProc.killed) {
            return "Voice assistant is not running.";
          }
          await killProcess(childProc);
          childProc = null;
          startedAt = null;
          activePort = null;
          activeHost = null;
          return "Voice assistant stopped.";
        }

        // ── START ───────────────────────────────────────────────────────
        if (subcommand !== "start") {
          return `Unknown subcommand: ${subcommand}. Use: /ova [start|stop|status]`;
        }

        // Already running?
        if (childProc && !childProc.killed) {
          const displayHost = activeHost === "0.0.0.0" ? getLocalIp() : activeHost;
          return `Voice assistant already running at http://${displayHost}:${activePort}`;
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
          return err.message;
        }

        // 2. Check venv, run setup if needed
        const venvCheck = isWindows
          ? join(pluginDir, "venv", "Scripts")
          : join(pluginDir, "venv", "bin");

        if (!(await pathExists(venvCheck))) {
          logger.info("[OVA] venv not found — running setup...");
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
            return `Setup failed: ${err.message}`;
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
        try {
          await waitForServer(host, port);
        } catch {
          await killProcess(proc);
          childProc = null;
          startedAt = null;
          return "Voice assistant failed to start (timeout after 30s). Check logs.";
        }

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
        return [
          "\uD83C\uDF99\uFE0F Voice Assistant active",
          "",
          `\uD83D\uDD17 ${url}`,
          "",
          "Open the link in your browser to talk.",
          "To stop: /ova stop",
        ].join("\n");
      },
    });
  },
});
