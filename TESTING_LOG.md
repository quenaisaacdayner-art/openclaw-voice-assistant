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
