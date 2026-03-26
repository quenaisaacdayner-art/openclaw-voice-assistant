# FIX_PLUGIN.md — Correções de compatibilidade com OpenClaw Plugin System

---

## Contexto: o que é este projeto

Este projeto é um **Voice Assistant Speech-to-Speech** que funciona como plugin do OpenClaw. O OpenClaw é uma plataforma de agentes IA que suporta plugins em TypeScript. Nosso plugin registra o comando `/ova` que, quando digitado pelo usuário em qualquer canal (Telegram, webchat, Discord), inicia um servidor Python local com WebSocket para conversação por voz.

O código Python (STT via Whisper, TTS, WebSocket server, frontend) **já funciona perfeitamente** — 118 testes passando. O problema é exclusivamente na **integração TypeScript** com o sistema de plugins do OpenClaw.

### Arquitetura do plugin

```
Usuário digita /ova no chat
  → OpenClaw intercepta o comando (não vai pro LLM)
  → Carrega nosso plugin (index.ts)
  → Roda o handler registrado via api.registerCommand()
  → Handler retorna resultado → OpenClaw exibe no chat
```

Arquivos relevantes do plugin:
- `index.ts` — Entry point TypeScript, registra o comando `/ova` via `definePluginEntry` + `api.registerCommand()`
- `package.json` — Manifesto npm, metadados do pacote
- `openclaw.plugin.json` — Manifesto do OpenClaw, define id, nome, configSchema
- Todo o resto (Python, testes, frontend) — **NÃO TOCAR**, funciona

---

## O que aconteceu: histórico do problema

1. **Construímos o plugin** seguindo a documentação do OpenClaw (`definePluginEntry`, `registerCommand`, etc.)
2. **Colocamos em `~/.openclaw/extensions/ova/`** — o OpenClaw auto-descobre plugins nessa pasta
3. **O plugin carrega** — nos logs aparece `[plugins] ova: loaded without install/load-path provenance`
4. **Mas `/ova` falha** — o comando não executa, retorna erro silencioso ou "Command failed"

### O que os logs mostraram

```
WARN: plugin id mismatch (manifest uses "ova", entry hints "openclaw-voice-assistant")
INFO: [plugins] loaded without install/load-path provenance
```

O plugin carrega mas o comando não funciona.

### O que investigamos

Comparamos nosso `index.ts` com os **plugins nativos do OpenClaw que funcionam** (`device-pair` e `talk-voice`, localizados em `node_modules/openclaw/dist/extensions/`). Também lemos o código fonte do command router do OpenClaw (`pi-embedded-Bbou92RF.js`, funções `matchPluginCommand`, `executePluginCommand`, `registerPluginCommand`). Encontramos 5 diferenças críticas.

---

## Problemas encontrados (5 fixes)

### FIX 1 — CRÍTICO: handler retorna tipo errado

**O que está errado:** O handler do `registerCommand` retorna strings cruas (`return "mensagem"`). O OpenClaw command router passa o resultado DIRETO para `deliverReplies` como `{ replies: [result] }`. O sistema espera `result.text` — quando `result` é uma string, `.text` é `undefined` → mensagem vazia → erro.

**Prova no código fonte do OpenClaw** (pi-embedded-Bbou92RF.js, linhas 161371-161394):
```js
const result = await executePluginCommand({ command: match.command, args: match.args, ... });
await deliverReplies({ replies: [result], ...deliveryBaseOptions });
```

**Todos os plugins nativos retornam objetos:**
```ts
// device-pair/index.js (FUNCIONA)
return { text: "Usage: /pair notify on|off|once|status" };

// talk-voice/index.js (FUNCIONA)
return { text: "Talk voice is not configured.\n\nMissing: talk.provider..." };
```

**Nosso código (QUEBRADO):**
```ts
return "Voice assistant is not running.";
return [...].join("\n");
```

**Correção:** Trocar TODOS os returns dentro do handler do `registerCommand` de `return "string"` para `return { text: "string" }`.

**IMPORTANTE:** Só mudar os returns dentro do `handler` do `registerCommand`. NÃO mudar returns de funções auxiliares (`detectPython`, `waitForServer`, `killProcess`, etc.).

---

### FIX 2 — CRÍTICO: handler recebe `ctx` (objeto), não `rawArgs` (string)

**O que está errado:** Nosso handler é declarado como `async handler(rawArgs)` e faz `(rawArgs || "start").trim()`. Mas o OpenClaw NÃO passa os argumentos como string — passa um objeto `ctx` com múltiplas propriedades.

**Prova no código fonte do OpenClaw** (pi-embedded-Bbou92RF.js, linhas 66190-66248):
```js
const ctx = {
  senderId,
  channel,
  channelId,
  isAuthorizedSender,
  args: sanitizedArgs,       // ← os argumentos estão AQUI
  commandBody,
  config,
  from,
  to,
  accountId,
  messageThreadId,
  requestConversationBinding,
  detachConversationBinding,
  getCurrentConversationBinding,
};
const result = await command.handler(ctx);  // ← passa o OBJETO ctx
```

**Plugins nativos:**
```ts
// device-pair/index.js (FUNCIONA)
handler: async (ctx) => {
  const tokens = (ctx.args?.trim() ?? "").split(/\s+/).filter(Boolean);
  // ...
}

// talk-voice/index.js (FUNCIONA)
handler: async (ctx) => {
  const tokens = (ctx.args?.trim() ?? "").split(/\s+/).filter(Boolean);
  // ...
}
```

**Nosso código (QUEBRADO):**
```ts
async handler(rawArgs) {
  const subcommand = (rawArgs || "start").trim().toLowerCase();
```

`rawArgs` recebe o objeto `ctx` inteiro. `ctx || "start"` = sempre `ctx` (truthy). `ctx.trim()` → crash ou `"[object Object]"`. O subcommand nunca é "start", "stop" ou "status".

**Correção:**
```ts
// ANTES:
async handler(rawArgs) {
  const subcommand = (rawArgs || "start").trim().toLowerCase();

// DEPOIS:
async handler(ctx) {
  const subcommand = (ctx.args || "start").trim().toLowerCase();
```

---

### FIX 3 — CRÍTICO: falta `acceptsArgs: true`

**O que está errado:** Sem `acceptsArgs: true`, o OpenClaw **rejeita o match** quando o usuário digita `/ova start`, `/ova stop`, ou `/ova status`.

**Prova no código fonte** (pi-embedded-Bbou92RF.js, `matchPluginCommand`):
```js
if (args && !command.acceptsArgs) return null;
```

Se o usuário digita `/ova stop` → `args = "stop"` → `!command.acceptsArgs` = `true` → retorna `null` → comando não encontrado → mensagem vai pro LLM em vez de executar o handler.

**Plugins nativos:**
```ts
// device-pair/index.js (FUNCIONA)
api.registerCommand({
  name: "pair",
  description: "Generate setup codes...",
  acceptsArgs: true,        // ← PRESENTE
  handler: async (ctx) => { ... }
});

// talk-voice/index.js (FUNCIONA)
api.registerCommand({
  name: "voice",
  description: "List/set Talk provider voices...",
  acceptsArgs: true,        // ← PRESENTE
  handler: async (ctx) => { ... }
});
```

**Nosso código (FALTA):**
```ts
api.registerCommand({
  name: "ova",
  description: "Voice Assistant — talk to your agent with speech",
  args: Type.Optional(Type.String()),   // ← isso NÃO é acceptsArgs
  async handler(rawArgs) { ... }
});
```

`args: Type.Optional(Type.String())` é um schema de validação que o command router **não usa**. O campo que controla o matcher é `acceptsArgs: true`.

**Correção:** Adicionar `acceptsArgs: true` e remover `args: Type.Optional(Type.String())`:
```ts
api.registerCommand({
  name: "ova",
  description: "Voice Assistant — talk to your agent with speech",
  acceptsArgs: true,                    // ← ADICIONAR
  // REMOVER: args: Type.Optional(Type.String()),
  async handler(ctx) { ... }
});
```

---

### FIX 4 — package.json: name desalinhado com manifest id

**O que está errado:** `package.json` tem `"name": "openclaw-voice-assistant"` mas `openclaw.plugin.json` tem `"id": "ova"`. O OpenClaw compara e mostra warning.

**Log:**
```
WARN: plugin id mismatch (manifest uses "ova", entry hints "openclaw-voice-assistant")
```

**Correção:** Em `package.json`, mudar:
```json
"name": "openclaw-voice-assistant"
```
Para:
```json
"name": "openclaw-ova"
```

---

### FIX 5 — package.json: devDependencies fantasma

**O que está errado:** `devDependencies` lista `@sinclair/typebox` mas o `index.ts` não precisa dela após a remoção do `args: Type.Optional(Type.String())` do FIX 3. Também remover o `import { Type } from "@sinclair/typebox"` no topo do `index.ts`.

**Correção:**

Em `package.json`, remover:
```json
"devDependencies": {
  "@sinclair/typebox": "^0.34.0"
}
```

Em `index.ts`, remover a linha:
```ts
import { Type } from "@sinclair/typebox";
```

Também deletar `node_modules/` e `package-lock.json` se existirem na raiz do projeto.

---

## Checklist de verificação pós-fix

1. **`index.ts`:**
   - [ ] ZERO `return "..."` ou `return [...].join(...)` soltos dentro do handler → todos são `return { text: "..." }`
   - [ ] Handler declarado como `handler(ctx)` não `handler(rawArgs)`
   - [ ] Usa `ctx.args` para ler argumentos
   - [ ] Sem `import { Type }` do typebox
   - [ ] `acceptsArgs: true` presente no `registerCommand`
   - [ ] Sem `args: Type.Optional(...)` no `registerCommand`

2. **`package.json`:**
   - [ ] `"name": "openclaw-ova"`
   - [ ] Sem bloco `devDependencies`

3. **`openclaw.plugin.json`:**
   - [ ] `"id": "ova"` (sem mudança)

4. **Geral:**
   - [ ] Sem `node_modules/` nem `package-lock.json` na raiz
   - [ ] Nenhum arquivo Python foi modificado
   - [ ] `python -m pytest tests/ -v` — 118 testes passam

---

## Arquivos de referência

Plugins nativos do OpenClaw (usar como modelo):
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\dist\extensions\device-pair\index.js`
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\dist\extensions\talk-voice\index.js`

Código fonte do command router:
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\dist\pi-embedded-Bbou92RF.js` (funções: `matchPluginCommand`, `executePluginCommand`, `registerPluginCommand`, `validatePluginCommandDefinition`)

Documentação oficial:
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\docs\plugins\building-plugins.md`
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\docs\plugins\sdk-entrypoints.md`
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\docs\plugins\sdk-overview.md`
