# Testing Log — Erros encontrados nos testes de cenário

> Cada erro encontrado durante testes manuais é documentado aqui.
> Quando corrigido, o fix é descrito e o erro marcado como resolvido.

---

## Erro #1: `python` não encontrado na VPS (Cenário 2)

- **Data:** 2026-03-20
- **Cenário:** 2 (tudo na VPS)
- **Sintoma:** `bash scripts/run_vps.sh` → `python: command not found`
- **Causa:** VPS limpa (Ubuntu) só tem `python3`, não `python`. Os scripts usam `python` direto.
- **Impacto:** Qualquer pessoa clonando numa VPS/servidor limpo não consegue rodar.
- **Fix:**
  - Criado `setup.sh` — detecta OS, instala Python se necessário, cria virtualenv, instala deps
  - Criado `scripts/_activate_venv.sh` — auto-ativa venv (ou roda setup.sh se não existe)
  - Todos os `scripts/run_*.sh` agora incluem `source _activate_venv.sh` antes de rodar
  - Dentro do venv, `python` sempre existe (aponta pra python3)
- **Status:** ✅ Corrigido

## Erro #2: Processo antigo ocupando porta 7860 (Cenário 2)

- **Data:** 2026-03-20
- **Cenário:** 2 (tudo na VPS)
- **Sintoma:** Interface antiga (Gradio) aparece em vez da nova (WebSocket S2S)
- **Causa:** `voice_assistant_vps.py` de sessão anterior (PID 662384) ainda rodando na porta 7860
- **Impacto:** Novo server não sobe ou sobe sem aviso — usuário vê interface errada sem entender porquê
- **Fix pendente:** Adicionar check de porta ocupada nos scripts `run_*.sh` — se processo antigo na 7860, matar antes de iniciar
- **Workaround manual:** `kill $(lsof -ti:7860)` antes de rodar o script
- **Status:** 🟡 Documentado, fix pendente

## Erro #3: Gateway OpenClaw — porta errada + token (Cenário 2)

- **Data:** 2026-03-20
- **Cenário:** 2 (tudo na VPS)
- **Sintoma:** Whisper transcreve o áudio corretamente, mas o LLM não responde — conexão recusada ao gateway
- **Causa real (2 problemas):**
  1. **Porta hardcoded errada:** Scripts tinham `18789` fixo, mas a VPS usa porta `19789` (configurada em `openclaw.json`)
  2. **Token:** O código Python (`core/config.py` → `load_token()`) JÁ lê o token de `~/.openclaw/openclaw.json` automaticamente — isso NÃO era o problema
- **Impacto:** Qualquer pessoa com porta diferente de 18789 vai ter o mesmo erro
- **Fix aplicado:** Todos os 6 scripts (`run_local.sh/.ps1`, `run_vps.sh/.ps1`, `run_local_remote_gateway.sh/.ps1`) agora auto-detectam a porta de `~/.openclaw/openclaw.json` — se não encontrar, usa 18789 como fallback
- **Status:** ✅ Corrigido

---

## Erro #4: Porta 7860 ocupada no laptop impede tunnel SSH (Cenário 2)

- **Data:** 2026-03-20
- **Cenário:** 2 (tudo na VPS, acesso via tunnel)
- **Sintoma:** `ssh -N -L 7860:...` falha com `bind: Address already in use`
- **Causa:** Teste do Cenário 1 deixou processo local (Gradio/server) rodando na porta 7860
- **Impacto:** Tunnel não sobe, usuário não consegue acessar a interface da VPS
- **Fix manual:** `netstat -ano | findstr :7860` → `taskkill /PID <PID> /F` → tentar tunnel de novo
- **Fix ideal (futuro):** Adicionar check de porta ocupada nos scripts + documentar no README que precisa liberar a porta antes do tunnel
- **Status:** 🟡 Documentado, workaround manual

---

## Template para novos erros

```
## Erro #N: [descrição curta]

- **Data:** YYYY-MM-DD
- **Cenário:** 1/2/3
- **Sintoma:** o que aconteceu
- **Causa:** por quê
- **Impacto:** quem afeta
- **Fix:** o que foi feito / o que precisa ser feito
- **Status:** ✅ Corrigido / 🟡 Pendente / 🔴 Bloqueado
```
