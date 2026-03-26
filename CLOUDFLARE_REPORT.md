# CLOUDFLARE_REPORT.md — Análise de Viabilidade

> Data: 2026-03-25
> Autor: Claude Code (análise técnica)

---

## 1. VEREDICTO: ✅ VIÁVEL — Recomendação: Implementar

A integração do Cloudflare Quick Tunnel no OVA é viável, de baixa complexidade, e resolve completamente o problema de acesso ao microfone em cenários remotos (celular, outro dispositivo na rede). A mudança é cirúrgica — ~100 linhas de código novo em `index.ts`, 2 linhas alteradas no frontend, 0 mudanças no `server_ws.py`.

**Justificativa técnica:**
- cloudflared é um binário estático (~40MB), sem dependências, com download automático via GitHub Releases
- Quick Tunnel não exige conta Cloudflare, não exige domínio, não exige configuração
- WebSocket é suportado nativamente (proxy transparente via QUIC)
- Query parameters (token auth) passam intactos pelo tunnel
- O servidor Python não precisa de nenhuma mudança — cloudflared faz proxy reverso transparente

---

## 2. MAPA DE MUDANÇAS

### 2.1 `static/index.html` — 2 linhas (CRÍTICA, mas trivial)

**Problema encontrado:** A URL do WebSocket está hardcoded como `ws://`:

```javascript
// Linha 796 — ATUAL
const WS_URL = `ws://${window.location.host}/ws${_token ? '?token=' + encodeURIComponent(_token) : ''}`;
```

Quando o browser acessa via `https://random.trycloudflare.com`, ele tenta `ws://` que é bloqueado (mixed content). Precisa ser `wss://` para HTTPS.

**Correção:**

```javascript
// Linha 796 — NOVO
const _wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${_wsProto}//${window.location.host}/ws${_token ? '?token=' + encodeURIComponent(_token) : ''}`;
```

> **Nota:** Esta correção é necessária INDEPENDENTE de usarmos cloudflared, ngrok, ou qualquer outro tunnel HTTPS. É um bug latente — qualquer proxy HTTPS quebraria o WebSocket hoje.

### 2.2 `index.ts` — ~80-100 linhas novas

| Função/Seção | Mudança | Linhas |
|---|---|---|
| **Estado global** (L7-11) | Adicionar `let tunnelProc: ChildProcess \| null = null;` e `let tunnelUrl: string \| null = null;` | +2 |
| **`findCloudflared()`** (nova) | Verificar se `cloudflared` está no PATH via `execFile("cloudflared", ["version"])`. Se não, verificar se existe em `pluginDir/bin/cloudflared[.exe]`. | +15 |
| **`downloadCloudflared()`** (nova) | Baixar binário de `github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-{os}-{arch}[.ext]` para `pluginDir/bin/`. Detectar plataforma via `process.platform` + `process.arch`. | +30 |
| **`startTunnel(port)`** (nova) | Spawnar `cloudflared tunnel --url http://localhost:{port}`. Parsear stderr com regex `/https:\/\/[-a-zA-Z0-9]+\.trycloudflare\.com/` para capturar URL. Retornar Promise\<string\> com a URL. | +25 |
| **`killProcess`** (L87-110) | Sem mudança — já é genérica o suficiente para matar qualquer ChildProcess. | 0 |
| **STOP handler** (L159-169) | Adicionar `if (tunnelProc) await killProcess(tunnelProc); tunnelProc = null; tunnelUrl = null;` | +3 |
| **Shutdown handler** (L123-130) | Adicionar kill do tunnelProc junto com childProc. | +3 |
| **START handler** (L292-310) | Após `waitForServer()`: se `!isLoopback && config.tunnel !== false`, chamar `startTunnel(port)`. Se obtiver URL, substituir a URL HTTP pela HTTPS do tunnel + token. | +15 |
| **STATUS handler** (L142-156) | Mostrar `tunnelUrl` se ativo. | +2 |
| **`exit` handler** (L264-272) | Adicionar cleanup do tunnelProc. | +2 |

**Total estimado: ~100 linhas novas/modificadas em `index.ts`.**

### 2.3 `openclaw.plugin.json` — 5 linhas

Adicionar campo `tunnel` ao `configSchema`:

```json
"tunnel": {
  "type": "boolean",
  "description": "Enable Cloudflare Quick Tunnel for HTTPS access (auto when host ≠ localhost, set false to disable)"
}
```

E em `uiHints`:

```json
"tunnel": { "label": "HTTPS Tunnel", "advanced": true }
```

### 2.4 `server_ws.py` — 0 linhas

**Nenhuma mudança necessária.** Razões:
- cloudflared faz proxy reverso transparente — o server vê requisições vindas de `localhost`
- WebSocket upgrade é feito pelo cloudflared antes de chegar no FastAPI
- O auth token passa via query string, que o cloudflared preserva intacto
- O `_is_loopback()` check usa `SERVER_HOST` (env var), não o IP da requisição — continua correto

### 2.5 Outros arquivos — 0 linhas

- `core/config.py` — sem mudança
- `scripts/*.sh` — sem mudança (tunnel é feature do plugin, não dos scripts manuais)
- `tests/` — nenhum teste existente quebra (tunnel é feature aditiva no index.ts)

### Resumo

| Arquivo | Linhas alteradas | Linhas novas | Complexidade |
|---------|:---:|:---:|:---:|
| `static/index.html` | 2 | 0 | Trivial |
| `index.ts` | ~10 | ~90 | Moderada |
| `openclaw.plugin.json` | 0 | 5 | Trivial |
| `server_ws.py` | 0 | 0 | — |
| **Total** | **~12** | **~95** | **Moderada** |

---

## 3. RISCOS CLASSIFICADOS

### 🟢 BAIXO

| Risco | Descrição | Mitigação |
|---|---|---|
| **Frontend WS protocol** | Hardcode `ws://` quebra com qualquer proxy HTTPS | Fix de 2 linhas (protocol-relative), retrocompatível |
| **Latência do tunnel** | cloudflared adiciona ~10-50ms por roundtrip | Irrelevante — STT leva 1-5s, TTS leva 0.5-2s. O overhead do tunnel é <1% do pipeline total |
| **Cenários 1 e 2 intactos** | Tunnel só ativa para host ≠ loopback | Lógica condicional explícita: `if (!isLoopback && config.tunnel !== false)` |
| **Auth com tunnel** | Token precisa chegar ao server | Confirmado: cloudflared preserva query params intactos |
| **Cleanup de processos** | Dois processos (Python + cloudflared) para gerenciar | `killProcess()` já é genérica; shutdown handler já existe. Adicionar tunnelProc no mesmo padrão |

### 🟡 MÉDIO

| Risco | Descrição | Mitigação |
|---|---|---|
| **URL muda a cada restart** | Quick Tunnel gera URL aleatória (`random-words.trycloudflare.com`) em cada execução | Exibir nova URL claramente no output do `/ova`. Não há como evitar sem conta Cloudflare |
| **Download do binário (~40MB)** | Se cloudflared não estiver instalado, precisa baixar. Pode ser lento, pode falhar | 1. Tentar PATH primeiro. 2. Download com timeout + mensagem de progresso. 3. Cache em `pluginDir/bin/`. 4. Se falhar, degradar graciosamente (entregar URL HTTP + aviso) |
| **Tunnel caindo** | Quick tunnel tem 1 conexão (sem HA), sem SLA | cloudflared tem auto-reconnect com backoff. Se cair, server Python continua rodando — só o tunnel precisa ser restabelecido. Pior caso: URL HTTP funciona como fallback |
| **macOS binary é .tgz** | Windows e Linux são binários diretos; macOS precisa extrair `.tgz` | Tratar especificamente: baixar `.tgz`, extrair com `tar xzf`, mover binário |

### 🔴 ALTO

| Risco | Descrição | Mitigação |
|---|---|---|
| **Nenhum risco alto identificado** | — | — |

---

## 4. ALTERNATIVAS ANALISADAS

### 4.1 Self-signed certificate

| Aspecto | Avaliação |
|---|---|
| Como funciona | Gerar cert com `mkcert` ou `openssl`, servir HTTPS diretamente |
| Prós | Zero latência extra, sem dependência externa |
| Contras | **Inviável no celular**: não é possível instalar CA custom facilmente no iOS/Android. Chrome mostra warning. WebSocket via WSS com cert self-signed é rejeitado silenciosamente em muitos browsers. |
| **Veredicto** | ❌ Não resolve o cenário principal (celular) |

### 4.2 ngrok

| Aspecto | Avaliação |
|---|---|
| Como funciona | Similar ao cloudflared — binário que cria tunnel HTTPS |
| Prós | Muito popular, boa documentação, WebSocket suportado |
| Contras | **Requer conta** (gratuita, mas precisa signup + authtoken). Free tier tem limite de 1 tunnel. Binário similar em tamanho. |
| **Veredicto** | ⚠️ Funcional, mas exige conta — friction desnecessária vs cloudflared |

### 4.3 localtunnel (npm)

| Aspecto | Avaliação |
|---|---|
| Como funciona | Pacote npm (`lt --port 7860`), servidores do localtunnel.me |
| Prós | Instalação via npm (já temos Node.js), leve |
| Contras | Servidores instáveis (downtime frequente), não é mantido ativamente (último commit significativo em 2022), WebSocket support inconsistente, sem garantia de que HTTPS termina corretamente |
| **Veredicto** | ❌ Instável demais para uso confiável |

### 4.4 bore (Rust)

| Aspecto | Avaliação |
|---|---|
| Como funciona | Binário Rust que cria tunnel TCP |
| Prós | Leve (~5MB), rápido |
| Contras | **Só TCP, sem HTTPS termination.** O browser vê HTTP, não HTTPS — o mic continua bloqueado. Precisaria de proxy HTTPS separado. |
| **Veredicto** | ❌ Não resolve o problema (sem HTTPS) |

### 4.5 Serveo / localhost.run (SSH-based)

| Aspecto | Avaliação |
|---|---|
| Como funciona | SSH reverse tunnel para servidor público |
| Prós | Sem binário extra — usa `ssh` que já existe |
| Contras | Latência alta (SSH é TCP-over-TCP), instabilidade, sem controle de domínio, `serveo.net` frequentemente indisponível |
| **Veredicto** | ❌ Instável, latência |

### Comparação resumida

| Solução | Sem conta | HTTPS | WebSocket | Estável | Binário único | Auto-download |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **cloudflared** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ngrok | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| localtunnel | ✅ | ✅ | ⚠️ | ❌ | — | — |
| bore | ✅ | ❌ | — | ✅ | ✅ | ✅ |
| Self-signed | ✅ | ⚠️ | ⚠️ | ✅ | — | — |

**cloudflared é a melhor opção em todas as dimensões relevantes.**

---

## 5. RECOMENDAÇÃO: Implementar em 2 fases

### Fase 1 — Fix do WebSocket protocol (URGENTE, independente do tunnel)

Corrigir o hardcode `ws://` no frontend para protocol-relative. Isso é um bug latente que afeta qualquer cenário futuro com HTTPS (não só cloudflared). **2 linhas, zero risco, deveria ser feito independente da decisão sobre tunnel.**

```javascript
const _wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${_wsProto}//${window.location.host}/ws${...}`;
```

### Fase 2 — Integração do cloudflared no `index.ts`

**Abordagem exata:**

1. **Detecção**: Procurar `cloudflared` no PATH. Se não encontrar, verificar `pluginDir/bin/cloudflared[.exe]`.
2. **Auto-download** (se não encontrado): Baixar de `github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-{os}-{arch}[.ext]` para `pluginDir/bin/`. Mostrar mensagem "Downloading cloudflared..." com spinner.
3. **Decisão**: Iniciar tunnel SOMENTE se `!isLoopback && config.tunnel !== false`.
4. **Spawn**: `cloudflared tunnel --url http://localhost:{port}` — parsear stderr para capturar URL HTTPS.
5. **URL**: Substituir URL HTTP pela URL do tunnel + token: `https://random.trycloudflare.com?token=xxx`.
6. **Lifecycle**: Matar tunnelProc junto com childProc no stop/shutdown.
7. **Fallback**: Se cloudflared falhar (download, spawn, ou captura de URL), **não bloquear** — entregar URL HTTP normal com aviso de que mic não funciona em devices remotos.

**Fluxo resultante:**

```
/ova start
  → Detecta Python ✓
  → Verifica venv ✓
  → Spawna server_ws.py na porta 7860 ✓
  → waitForServer() ✓
  → host é loopback?
      SIM → entrega http://localhost:7860 (como hoje)
      NÃO → cloudflared está disponível?
          SIM → spawna tunnel → captura URL HTTPS
               → entrega https://random.trycloudflare.com?token=xxx
          NÃO → tenta auto-download
               → sucesso → spawna tunnel (como acima)
               → falha → entrega http://IP:7860?token=xxx + warning
```

**Cenários de uso resultantes:**

| # | Onde roda | Host config | Tunnel | URL entregue | Mic |
|---|---|---|---|---|:---:|
| 1 | Local, browser local | `127.0.0.1` | Não inicia | `http://localhost:7860` | ✅ |
| 2 | VPS, SSH tunnel | `127.0.0.1` | Não inicia | `http://localhost:7860` | ✅ |
| 3 | Local, celular na rede | `0.0.0.0` | **Auto** | `https://xxx.trycloudflare.com?token=yyy` | ✅ |
| 4 | VPS, celular | `0.0.0.0` | **Auto** | `https://xxx.trycloudflare.com?token=yyy` | ✅ |
| 5 | Qualquer, tunnel=false | `0.0.0.0` | Desabilitado | `http://IP:7860?token=yyy` | ❌ (warning) |

---

## 6. EDGE CASES E QUESTÕES SECUNDÁRIAS

### cloudflared já instalado vs auto-download

Prioridade: PATH > `pluginDir/bin/` > download. Nunca baixar se já existe. Verificar versão não é necessário para quick tunnel (não há requisito mínimo).

### Tempo de propagação do tunnel

Após cloudflared printar a URL, pode levar 2-5 segundos para DNS propagar. O `waitForServer()` atual espera o Python subir (timeout 30s). Sugestão: adicionar pequeno delay (3s) ou retry no fetch da URL do tunnel antes de entregar ao usuário.

### `.gitignore`

Adicionar `bin/` ao `.gitignore` para não commitar o binário do cloudflared (~40MB).

### Windows-specific

`taskkill /F /T /PID` já é usado no `killProcess()` para matar árvore de processos no Windows. cloudflared no Windows é um `.exe` — spawnar normalmente com `spawn()`.

### Token na URL HTTPS

O token aparece na URL como query param: `https://xxx.trycloudflare.com?token=yyy`. Isso é visível no browser history, mas é o mesmo comportamento atual com HTTP. O tunnel usa HTTPS, então o token está encrypted in transit. Não é pior que o cenário atual.

### `.ova_token` com tunnel

O server gera o token em `.ova_token` independente de tunnel. O `index.ts` lê o token e inclui na URL. O tunnel não interfere nesse fluxo.

---

## 7. COMPLEXIDADE REAL

| Métrica | Valor |
|---|---|
| Arquivos modificados | 3 (`index.html`, `index.ts`, `openclaw.plugin.json`) |
| Linhas novas | ~95 |
| Linhas alteradas | ~12 |
| Funções novas | 3 (`findCloudflared`, `downloadCloudflared`, `startTunnel`) |
| Novos edge cases | 3 (download falha, tunnel não inicia, URL não capturada) — todos com fallback gracioso |
| Testes existentes quebram | 0 (tunnel é aditivo, frontend fix é retrocompatível) |
| Novos testes necessários | Opcionais — as funções novas são I/O puro (spawn + network), difíceis de testar unitariamente |
| Dependências novas | 0 (cloudflared é binário externo, não dependency do projeto) |

**Complexidade: BAIXA-MODERADA.** O grosso do trabalho é spawnar um processo e parsear stderr — padrão idêntico ao que já fazemos com o Python server.
