# Auditoria de Plugin — OpenClaw Voice Assistant

## Tua tarefa

Investigar por que este plugin do OpenClaw **não funciona** e mapear todos os bugs que encontrar. Criar o arquivo `AUDIT_CLAUDECODE.md` neste mesmo diretório com teus achados.

---

## ⛔ REGRA ABSOLUTA

**NÃO leia o arquivo `FIX_PLUGIN.md` deste projeto. Sob nenhuma circunstância.** Ele contém uma análise feita por outro agente e a comparação dos resultados depende de você fazer uma investigação independente. Se você ler esse arquivo, o experimento perde o valor.

---

## Contexto do projeto

### O que é
Um Voice Assistant Speech-to-Speech que funciona como **plugin do OpenClaw**. O OpenClaw é uma plataforma de agentes IA que suporta plugins em TypeScript. Este plugin registra o comando `/ova` para que, quando o usuário digitar no chat (Telegram, webchat, Discord), inicie um servidor Python local com conversação por voz via WebSocket.

### O que deveria acontecer
1. Usuário instala o plugin (copiando pra `~/.openclaw/extensions/ova/` ou via `openclaw plugins install`)
2. OpenClaw descobre e carrega o plugin automaticamente
3. Usuário digita `/ova` em qualquer canal → plugin executa, inicia o servidor Python, retorna link no chat
4. Usuário digita `/ova stop` → para o servidor
5. Usuário digita `/ova status` → mostra estado atual

### O que acontece na prática
O plugin **carrega** no OpenClaw (aparece nos logs como carregado), mas quando o usuário digita `/ova`, o comando **não funciona**. Não executa o que deveria.

Não vou te dar mais detalhes sobre o erro. Tua tarefa é descobrir **por quê**.

---

## Arquivos do plugin (LEIA ESTES)

Todos estão neste diretório (`C:\Users\quena\projects\openclaw-voice-assistant\`):

| Arquivo | O que é | Ler? |
|---------|---------|------|
| `index.ts` | Entry point TypeScript — registra o comando `/ova` | ✅ LER |
| `package.json` | Manifesto npm do pacote | ✅ LER |
| `openclaw.plugin.json` | Manifesto do plugin pro OpenClaw | ✅ LER |
| `FIX_PLUGIN.md` | ⛔ PROIBIDO | ❌ **NÃO LER** |
| Tudo em `core/`, `tests/`, `web/` | Código Python, testes, frontend | Não precisa — funciona |

---

## Como investigar

### Fontes de verdade — plugins nativos que FUNCIONAM

O OpenClaw tem plugins bundled que usam o mesmo sistema e funcionam. Compare nosso código com eles:

- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\dist\extensions\device-pair\index.js`
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\dist\extensions\talk-voice\index.js`

### Código fonte do command router do OpenClaw

O sistema que processa comandos de plugins está em:
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\dist\pi-embedded-Bbou92RF.js`

Funções relevantes (busque por nome):
- `matchPluginCommand` — como o OpenClaw decide se um comando digitado corresponde a um plugin
- `executePluginCommand` — como o handler é chamado e o resultado processado
- `registerPluginCommand` — como o comando é registrado internamente
- `validatePluginCommandDefinition` — validação do registro

⚠️ Este arquivo é enorme (178K+ linhas). Use busca por nome de função, não leia sequencialmente.

### Documentação oficial de plugins

- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\docs\plugins\building-plugins.md`
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\docs\plugins\sdk-entrypoints.md`
- `C:\Users\quena\AppData\Roaming\npm\node_modules\openclaw\docs\plugins\sdk-overview.md`

---

## O que entregar

Crie o arquivo **`AUDIT_CLAUDECODE.md`** neste diretório com:

1. **Lista de bugs encontrados** — cada um com:
   - Descrição do problema
   - Onde está no código (arquivo + linha/trecho)
   - Por que causa falha (com evidência do código fonte do OpenClaw ou dos plugins nativos)
   - Severidade (crítico / médio / baixo)
   - Correção proposta (antes/depois)

2. **Ranking de severidade** — quais bugs são bloqueadores vs. cosméticos

3. **Teoria geral** — tua explicação de por que o comando falha, conectando todos os bugs encontrados

Seja exaustivo. Se encontrar algo que PODE ser problema mas não tem certeza, inclua como "possível issue" com tua reasoning.

---

## O que NÃO fazer

- ❌ NÃO ler `FIX_PLUGIN.md`
- ❌ NÃO modificar nenhum arquivo do projeto (só criar `AUDIT_CLAUDECODE.md`)
- ❌ NÃO modificar código Python, testes, ou frontend
- ❌ NÃO adivinhar sem evidência — se afirmar algo, mostrar o código que prova
