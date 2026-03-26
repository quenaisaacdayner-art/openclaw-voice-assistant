# CLOUDFLARE_ANALYSIS.md — Análise para Claude Code

## CONTEXTO

Este é o **OpenClaw Voice Assistant** — um plugin do OpenClaw que dá interface de voz (Speech-to-Speech) ao agente. O usuário fala no mic do browser, Whisper transcreve, OpenClaw responde via streaming, TTS gera áudio. Funciona via WebSocket.

### Arquitetura atual
- **`index.ts`** — Plugin OpenClaw que registra o comando `/ova`. Quando executado: detecta Python, cria venv, instala dependências, spawna `server_ws.py`, espera servidor subir, gera URL e entrega ao usuário.
- **`server_ws.py`** — Servidor FastAPI + WebSocket. Roda na porta 7860. Gera token de auth e salva em `.ova_token`.
- **`core/config.py`** — Configuração centralizada (gateway URL, model, TTS, etc.)
- **`static/index.html`** — Frontend com Web Audio API, VAD, WebSocket client.

### O problema que estamos resolvendo
O browser (Chrome/Safari/Firefox) **bloqueia acesso ao microfone** (`navigator.mediaDevices`) em páginas HTTP quando o host NÃO é `localhost`. Isso é política de segurança do browser, não bug do código.

**Cenários afetados:**

| # | Onde roda o OVA | Onde acessa o browser | URL gerada | Mic funciona? |
|---|-----------------|----------------------|------------|:---:|
| 1 | Laptop local | Laptop browser | `http://localhost:7860` | ✅ |
| 2 | VPS | Laptop browser (via SSH tunnel) | `http://localhost:7860` (manual) | ✅ (mas user precisa trocar IP→localhost) |
| 3 | Laptop local | Celular na mesma rede | `http://192.168.X.X:7860` | ❌ |
| 4 | VPS | Celular | `http://IP_PUBLICO:7860` | ❌ |

Cenários 3 e 4 são impossíveis sem HTTPS. SSH tunnel não é opção no celular (sem terminal).

## PROPOSTA: Integrar Cloudflare Quick Tunnel

[Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) cria um tunnel HTTPS gratuito sem conta, sem domínio, sem configuração. Roda um binário (`cloudflared`) que gera URL tipo `https://random-name.trycloudflare.com`.

**Fluxo proposto:**
```
/ova → sobe Gradio (server_ws.py) na porta 7860
    → detecta: host é localhost?
        → SIM: entrega http://localhost:7860 (cenário 1, mic funciona)
        → NÃO: sobe cloudflared tunnel → captura URL HTTPS → entrega ao usuário
    → usuário acessa URL HTTPS → mic funciona em qualquer dispositivo
```

**Quando usar tunnel:**
- Host é `0.0.0.0` ou IP não-loopback → automaticamente sobe tunnel
- Host é `127.0.0.1` / `localhost` / `::1` → NÃO precisa de tunnel (cenário 1)
- **Plugin config override:** `"tunnel": false` pra desabilitar explicitamente

## TUA TAREFA

**Analisar a viabilidade técnica desta proposta e entregar um relatório ANTES de implementar qualquer coisa.**

### O que analisar

1. **Viabilidade da integração no `index.ts`:**
   - É possível spawnar `cloudflared` como child process junto com o `server_ws.py`?
   - Como capturar a URL HTTPS gerada pelo `cloudflared`? (ele printa no stderr)
   - Como garantir que ambos processos (Python + cloudflared) morrem no `/ova stop`?
   - O que acontece se `cloudflared` não estiver instalado? (auto-install? erro claro?)

2. **Impacto no código existente:**
   - Quais linhas/funções do `index.ts` precisam mudar?
   - O `server_ws.py` precisa de alguma mudança? (WebSocket funciona atrás de proxy?)
   - O token de auth (`.ova_token`) funciona com cloudflared? (query params passam?)
   - O frontend (`static/index.html`) precisa de mudança? (WSS vs WS?)

3. **Riscos:**
   - Latência adicionada pelo tunnel (estimativa)
   - Estabilidade do quick tunnel (timeout? reconexão?)
   - O que quebra se Cloudflare estiver indisponível?
   - Conflito com o fluxo atual (cenário 1 e 2 continuam funcionando?)

4. **Complexidade real:**
   - Quantas linhas de código mudam?
   - Quantos novos edge cases introduz?
   - É possível fazer sem quebrar nenhum teste existente?

5. **Alternativas que considerar:**
   - Existe alternativa ao cloudflared que seja mais simples?
   - Self-signed cert + bypass no browser é viável? (spoiler: não pra celular, mas analise)
   - ngrok, localtunnel, bore — são melhores?

### O que entregar

Criar arquivo `CLOUDFLARE_REPORT.md` no diretório raiz do projeto (`C:\Users\quena\projects\openclaw-voice-assistant\`) com:

1. **Veredicto:** Viável ou não viável? Com justificativa técnica.
2. **Mapa de mudanças:** Quais arquivos, quais funções, estimativa de linhas.
3. **Riscos classificados:** Alto/Médio/Baixo com mitigação.
4. **Alternativas:** Se cloudflared não for a melhor opção, qual é?
5. **Recomendação:** Implementar ou não? Se sim, qual abordagem exata?

### Restrições

- **NÃO implementar nada.** Só analisar e reportar.
- **NÃO ler `FIX_PLUGIN.md`** — é arquivo interno de outra tarefa, irrelevante aqui.
- Leia o código dos arquivos mencionados acima pra entender a arquitetura real.
- Se precisar ver como `cloudflared` funciona, pesquise a documentação oficial.
- Seja honesto sobre riscos. Se a complexidade for alta demais, diga.

### Referências no código

- URL generation logic: `index.ts` linhas ~293-316 (seção "Read auth token and build URL")
- Process management: `index.ts` (killProcess, shutdown handler, stop subcommand)
- Server startup: `index.ts` linhas ~180-290
- Auth system: `server_ws.py` linhas 1-50 (`_load_or_create_token`, `_is_loopback`)
- WebSocket endpoint: `server_ws.py` `/ws` route
- Config schema: `openclaw.plugin.json` (pode precisar de novo campo `tunnel`)
- Scripts de cenário: `scripts/run_vps.sh`, `scripts/run_local.sh`
- README cenários: `README.md` seção "3 Cenários de uso"
