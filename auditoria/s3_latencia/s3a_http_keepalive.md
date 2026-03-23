# Registro — S3-A: HTTP Keep-Alive com requests.Session

> Executada: 23/03/2026
> Prompt: `prompts/s3_latencia/s3_completo.md` (Otimizacao 1)
> Objetivo: Reutilizar conexao TCP entre chamadas ao gateway OpenClaw, eliminando ~100-200ms de handshake por turno

## Resultado dos Testes

- **227 passed, 18 skipped, 0 failed**
- Sem regressao

## Prompt seguido?

**Sim, 100%.** Todas as instrucoes da Otimizacao 1 foram seguidas fielmente.

### Mudancas em `core/llm.py` — Checklist

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Criar `_session = requests.Session()` como variavel de modulo | Sim | Linha 11: `_session = requests.Session()` |
| Trocar `requests.post()` por `_session.post()` em `ask_openclaw()` | Sim | Linha 24: `resp = _session.post(...)` |
| Trocar `requests.post()` por `_session.post()` em `ask_openclaw_stream()` | Sim | Linha 45: `resp = _session.post(...)` |
| Manter mesma assinatura e comportamento das funcoes | Sim | Apenas troca de requests.post por _session.post |

### Mudancas em `server_ws.py` — Warmup via session — Checklist

| Instrucao do prompt | Seguida? | Notas |
|---------------------|----------|-------|
| Importar `_session as llm_session` de `core.llm` | Sim | Linha 21: `from core.llm import ... _session as llm_session` |
| Trocar `requests.get()` por `llm_session.get()` no warmup | Sim | Linha 43: `_gw_resp = llm_session.get(...)` |
| Remover import de `requests` no server_ws | Sim | `import requests` removido (nao mais necessario) |
| Log com "(keep-alive)" no warmup | Sim | Linha 45: `print(f"[WARMUP] Gateway OK em {_gw_elapsed:.1f}s (keep-alive)")` |

### Atualizacao dos testes

| Arquivo de teste | Mudanca | Motivo |
|-----------------|---------|--------|
| `tests/test_cli.py` | `core.llm.requests` → `core.llm._session` | Mock precisa apontar pro objeto que faz o POST |
| `tests/test_cli_extended.py` | idem | idem |
| `tests/test_shared_logic.py` | idem | idem |
| `tests/test_bugs_documented.py` | idem | idem |
| `tests/test_vps_extended.py` | idem | idem |

## Diferencas vs prompt

Nenhuma diferenca significativa. O prompt pedia exatamente `_session = requests.Session()` + troca de `requests.post` por `_session.post`, e foi isso que foi feito. A unica acao adicional foi atualizar os mocks dos testes que apontavam para `core.llm.requests.post` (necessario pra manter testes funcionando).
