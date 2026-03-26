# Auditoria de Plugin — OpenClaw Voice Assistant

**Auditor:** Claude Code (Claude Opus 4.6)
**Data:** 2026-03-25
**Escopo:** Investigar por que o comando `/ova` não funciona no OpenClaw

---

## Teoria geral

O comando `/ova` **falha por 3 bugs críticos que se combinam**:

1. **Sem `acceptsArgs`** → `/ova stop`, `/ova status`, `/ova start` **nunca casam** no router porque o comando não declara que aceita argumentos. O router descarta o match silenciosamente.
2. **Assinatura do handler errada** → mesmo `/ova` sozinho (sem args) **chega ao handler**, mas o handler recebe um objeto `ctx` e tenta chamar `.trim()` nele → **TypeError** → o catch genérico retorna `"Command failed"`.
3. **Tipo de retorno errado** → mesmo que o handler executasse, ele retorna strings puras em vez de `{ text: "..." }` → o sistema de delivery não consegue exibir a resposta.

Ou seja: com argumentos o comando nem é encontrado; sem argumentos ele é encontrado mas crasheia; e mesmo se não crasheasse, a resposta seria silenciosa.

---

## Bugs encontrados

### BUG 1 — `acceptsArgs` ausente (CRÍTICO — bloqueador)

**Onde:** `index.ts:135-138`

```typescript
// NOSSO CÓDIGO (index.ts:135-138)
api.registerCommand({
  name: "ova",
  description: "Voice Assistant — talk to your agent with speech",
  args: Type.Optional(Type.String()),  // ← campo errado
  async handler(rawArgs) {
```

**Problema:** O plugin define `args` (um schema TypeBox), mas o sistema de comandos do OpenClaw usa `acceptsArgs: boolean`. A propriedade `args` é ignorada pelo framework.

**Evidência — `matchPluginCommand`** (`pi-embedded-Bbou92RF.js:66132`):

```javascript
if (args && !command.acceptsArgs) return null;
```

Quando o usuário digita `/ova stop`, o router extrai `args = "stop"`. Como `command.acceptsArgs` é `undefined` (falsy), a condição é `true` e `matchPluginCommand` retorna `null`. O comando **não casa**.

**Evidência — plugins nativos que funcionam:**

```javascript
// device-pair/index.js:870-873
api.registerCommand({
  name: "pair",
  description: "Generate setup codes and approve device pairing requests.",
  acceptsArgs: true,  // ← assim que deve ser
  handler: async (ctx) => {
```

```javascript
// talk-voice/index.js:121-126
api.registerCommand({
  name: "voice",
  nativeNames: { discord: "talkvoice" },
  description: "List/set Talk provider voices...",
  acceptsArgs: true,  // ← assim que deve ser
  handler: async (ctx) => {
```

**Impacto:** `/ova stop`, `/ova status`, `/ova start` (qualquer subcomando com argumentos) **nunca executam**. O match falha silenciosamente e a mensagem vai pro handler built-in ou pro agente LLM. Apenas `/ova` sozinho (sem argumentos) passa pelo match.

**Severidade:** CRÍTICO — bloqueador total para subcomandos

**Correção proposta:**

```diff
  api.registerCommand({
    name: "ova",
    description: "Voice Assistant — talk to your agent with speech",
-   args: Type.Optional(Type.String()),
+   acceptsArgs: true,
    async handler(rawArgs) {
```

---

### BUG 2 — Handler recebe `ctx` (objeto), não `rawArgs` (string) (CRÍTICO — bloqueador)

**Onde:** `index.ts:139-140`

```typescript
// NOSSO CÓDIGO
async handler(rawArgs) {
  const subcommand = (rawArgs || "start").trim().toLowerCase();
```

**Problema:** O `executePluginCommand` chama `command.handler(ctx)` onde `ctx` é um **objeto** com propriedades `{ senderId, channel, args, commandBody, config, ... }` (vide `pi-embedded-Bbou92RF.js:66204-66245`). O handler recebe esse objeto no parâmetro `rawArgs`.

A linha `(rawArgs || "start").trim()`:
- `rawArgs` é um objeto → truthy → `rawArgs || "start"` retorna o objeto
- `.trim()` em um objeto → **TypeError: rawArgs.trim is not a function**
- O `try/catch` em `executePluginCommand` (linha 66251-66254) captura o erro e retorna a mensagem genérica: `"⚠️ Command failed. Please try again later."`

**Evidência — `executePluginCommand`** (`pi-embedded-Bbou92RF.js:66204-66254`):

```javascript
const ctx = {
  senderId,
  channel,
  channelId: params.channelId,
  isAuthorizedSender,
  gatewayClientScopes: params.gatewayClientScopes,
  args: sanitizedArgs,      // ← os args ficam AQUI
  commandBody,
  config,
  from: params.from,
  to: params.to,
  // ...
};
// ...
const result = await command.handler(ctx);  // ← ctx inteiro é passado
```

**Evidência — plugins nativos:**

```javascript
// device-pair/index.js:874-876
handler: async (ctx) => {
  const tokens = (ctx.args?.trim() ?? "").split(/\s+/).filter(Boolean);
  const action = tokens[0]?.toLowerCase() ?? "";
```

```javascript
// talk-voice/index.js:126-129
handler: async (ctx) => {
  const commandLabel = resolveCommandLabel(ctx.channel);
  const tokens = (ctx.args?.trim() ?? "").split(/\s+/).filter(Boolean);
  const action = (tokens[0] ?? "status").toLowerCase();
```

Ambos usam `ctx.args` — o campo `args` do objeto contexto.

**Impacto:** **Todo** uso do comando (mesmo `/ova` sem args) resulta em TypeError e mensagem genérica de erro. O handler nunca completa.

**Severidade:** CRÍTICO — bloqueador total

**Correção proposta:**

```diff
- async handler(rawArgs) {
-   const subcommand = (rawArgs || "start").trim().toLowerCase();
+ async handler(ctx) {
+   const subcommand = (ctx.args?.trim() || "start").toLowerCase();
```

---

### BUG 3 — Retorno é `string` em vez de `{ text: string }` (CRÍTICO)

**Onde:** Todas as cláusulas `return` do handler em `index.ts:145, 150-156, 161-169, 174, 180-181, 193, 226, 290, 314-321`

```typescript
// NOSSO CÓDIGO — exemplos
return "Voice assistant is not running.";                    // linha 145
return `Unknown subcommand: ${subcommand}...`;              // linha 174
return `Voice assistant already running at http://...`;      // linha 180
return "Voice assistant stopped.";                           // linha 169
return [...].join("\n");                                      // linhas 314-321
```

**Problema:** O sistema de delivery do OpenClaw espera que o handler retorne um objeto `{ text: string }`. Quando recebe uma string pura, `result.text` é `undefined`, e `result.isError` também é `undefined`.

**Evidência — uso do resultado** (`pi-embedded-Bbou92RF.js:161384-161392`):

```javascript
const result = await executePluginCommand({ ... });
// result é passado diretamente para deliverReplies:
await deliverReplies({
  replies: [result],
  ...deliveryBaseOptions,
  silent: ... && result.isError === true
});
```

O framework trata `result` como um objeto com `.text`, `.isError`, etc. Uma string pura não tem essas propriedades.

**Evidência — plugins nativos (TODOS retornam `{ text: "..." }`):**

```javascript
// device-pair — 100% dos returns:
return { text: formatPendingRequests(...) };
return { text: "No pending device pairing requests." };
return { text: `✅ Paired ${label}...` };

// talk-voice — 100% dos returns:
return { text: "Talk voice is not configured.\n\n..." };
return { text: `Talk voice status:\n- provider: ...` };
return { text: formatVoiceList(...) };
```

**Impacto:** Mesmo que os Bugs 1 e 2 fossem corrigidos, o usuário veria uma mensagem vazia ou o delivery falharia silenciosamente.

**Severidade:** CRÍTICO — a resposta nunca chega ao usuário

**Correção proposta (exemplo para cada return):**

```diff
  // STATUS (linha 145)
- return "Voice assistant is not running.";
+ return { text: "Voice assistant is not running." };

  // STATUS rodando (linhas 150-156)
- return [
-   `Voice Assistant running`,
-   ...
- ].join("\n");
+ return { text: [
+   `Voice Assistant running`,
+   ...
+ ].join("\n") };

  // STOP (linha 169)
- return "Voice assistant stopped.";
+ return { text: "Voice assistant stopped." };

  // START — resultado final (linhas 314-321)
- return [
-   "🎙️ Voice Assistant active",
-   ...
- ].join("\n");
+ return { text: [
+   "🎙️ Voice Assistant active",
+   ...
+ ].join("\n") };

  // (aplicar o mesmo padrão para TODOS os returns do handler)
```

---

### BUG 4 — `args` com TypeBox schema em vez de `acceptsArgs: boolean` (BAIXO)

**Onde:** `index.ts:138`

```typescript
args: Type.Optional(Type.String()),
```

**Problema:** A propriedade `args` não existe na interface de `registerCommand`. O framework usa `acceptsArgs: boolean`. O schema TypeBox é simplesmente ignorado — não causa erro, mas também não faz nada.

O import de `Type` de `@sinclair/typebox` no topo do arquivo (linha 2) é usado apenas para essa propriedade inútil. Após a correção dos bugs, esse import pode ser removido se não for usado em outro lugar.

**Severidade:** BAIXO — não causa falha diretamente, mas indica que a API foi confundida com a de `registerTool` (que usa TypeBox para `parameters`)

**Correção proposta:** Remover a propriedade `args` e substituir por `acceptsArgs: true` (já coberto no Bug 1). Remover import de `@sinclair/typebox` se não for mais usado.

---

## Possíveis issues adicionais

### POSSÍVEL ISSUE 1 — `api.config?.gateway?.port` pode não existir

**Onde:** `index.ts:241`

```typescript
const gatewayPort = api.config?.gateway?.port || 18789;
```

Na documentação do SDK (`sdk-overview.md:165`), `api.config` é do tipo `OpenClawConfig`. O campo `gateway.port` pode existir ou não. Se o schema da config mudou, isso pode falhar silenciosamente e usar o fallback 18789, que seria correto. **Provavelmente não é um bug**, mas vale verificar que a estrutura `config.gateway.port` existe no runtime.

### POSSÍVEL ISSUE 2 — `api.config?.gateway?.auth?.token` pode não ser o caminho correto

**Onde:** `index.ts:242`

```typescript
const gatewayToken = api.config?.gateway?.auth?.token;
```

Se o token do gateway estiver em um path diferente na config (ex: `api.config.gateway.auth.apiKey`), o token não seria passado ao processo Python. O processo Python tentaria ler de `~/.openclaw/openclaw.json` como fallback (via `load_token` em `core/config.py`), o que pode funcionar, mas vale verificar a estrutura exata.

---

## Ranking de severidade

| # | Bug | Severidade | Tipo |
|---|-----|------------|------|
| 1 | `acceptsArgs` ausente | **CRÍTICO** | Bloqueador — subcomandos nunca casam |
| 2 | Handler recebe `ctx` objeto, trata como string | **CRÍTICO** | Bloqueador — TypeError em toda execução |
| 3 | Retorno `string` em vez de `{ text: string }` | **CRÍTICO** | Bloqueador — resposta nunca chega ao usuário |
| 4 | `args` com TypeBox schema (inócuo) | BAIXO | Cosmético — propriedade ignorada |

**Os 3 bugs críticos são independentes e cada um sozinho impede o funcionamento do comando.** Todos os 3 precisam ser corrigidos para o plugin funcionar.

---

## Resumo das correções necessárias

```typescript
// ANTES (index.ts:135-140)
api.registerCommand({
  name: "ova",
  description: "Voice Assistant — talk to your agent with speech",
  args: Type.Optional(Type.String()),
  async handler(rawArgs) {
    const subcommand = (rawArgs || "start").trim().toLowerCase();
    // ... returns "string"
  },
});

// DEPOIS
api.registerCommand({
  name: "ova",
  description: "Voice Assistant — talk to your agent with speech",
  acceptsArgs: true,
  async handler(ctx) {
    const subcommand = (ctx.args?.trim() || "start").toLowerCase();
    // ... returns { text: "string" }
  },
});
```

E mudar todos os `return "..."` para `return { text: "..." }` dentro do handler.
