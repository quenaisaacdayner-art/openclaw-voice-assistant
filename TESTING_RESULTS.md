# Resultados dos Testes — 3 Cenários (2026-03-20)

> Testes manuais por Dayner. Métricas de latência baseadas em observação + dados da sessão de benchmarks anterior (19/03).
> Nenhum cenário quebrou o código — todos os erros foram de config/infra.

---

## Resumo Rápido

| | Cenário 1 (Local) | Cenário 2 (VPS) | Cenário 3 (Local→VPS) |
|---|---|---|---|
| **Voice app** | Laptop | VPS | Laptop |
| **Gateway/LLM** | Laptop (Opus 4) | VPS (Sonnet 4) | VPS via tunnel (Sonnet 4) |
| **Whisper** | Laptop (tiny) | VPS (tiny) | Laptop (tiny) |
| **TTS** | Edge TTS (laptop) | Edge TTS (VPS) | Edge TTS (laptop) |
| **STT funciona** | ✅ | ✅ | ✅ |
| **LLM responde** | ✅ | ✅ (após fix porta) | ✅ |
| **TTS funciona** | ✅ | ✅ | ✅ |
| **Barge-in** | ✅ | ✅ | ✅ |
| **1ª resposta** | Lenta (~30-40s) | Lenta | Lenta |
| **2ª+ respostas** | Fluida | Fluida | Fluida |

---

## Cenário 1: Tudo Local

- **Setup:** `scripts/run_local.ps1` no laptop
- **Gateway:** OpenClaw local, porta 18789, modelo Opus 4
- **Resultado:** ✅ Funcional completo
- **Erros encontrados:** Nenhum (gateway local já configurado)

### Observações
- Whisper tiny transcreve rápido (~1-2s) mas perde gírias/sotaque
- 1ª resposta lenta — bottleneck é o TTFT do Opus 4 (~31s medido em 19/03)
- A partir da 2ª mensagem, conversação fluida (LLM já "aqueceu", cache?)
- TTS Edge funciona bem, latência baixa

---

## Cenário 2: Tudo na VPS

- **Setup:** `scripts/run_vps.sh` na VPS, acesso via tunnel SSH (porta 7860)
- **Gateway:** OpenClaw VPS, porta 19789, modelo Sonnet 4
- **Resultado:** ✅ Funcional (após corrigir 3 erros de config)

### Erros encontrados (todos corrigidos)
1. **`python` não encontrado** — VPS limpa só tem `python3` → Fix: `setup.sh` + venv
2. **Porta 7860 ocupada** — processo antigo rodando → Fix: `kill $(lsof -ti:7860)`
3. **Porta gateway errada** — scripts tinham 18789, VPS usa 19789 → Fix: auto-detecção de porta

### Observações
- Whisper tiny na VPS: funciona igual (CPU diferente, resultado similar)
- LLM: modelo da VPS (Sonnet 4) pode ter TTFT diferente do Opus 4 local
- 1ª resposta lenta, depois fluida (mesmo padrão do Cenário 1)
- TTS Edge: funciona (VPS tem internet)

---

## Cenário 3: Voice App Local → Gateway VPS

- **Setup:** `scripts/run_local_remote_gateway.ps1` no laptop + tunnel SSH pra porta 19789
- **Gateway:** OpenClaw VPS via tunnel, porta 19789, modelo Sonnet 4
- **Resultado:** ✅ Funcional completo

### Erros encontrados
- Nenhum novo (o fix de auto-detecção de porta dos scripts anteriores já cobriu)

### Observações
- Whisper local (mesmo do Cenário 1) — transcrição igual
- LLM via tunnel: adiciona latência de rede (~30-50ms por hop) mas imperceptível
- TTS local: mesmo comportamento
- **1ª resposta lenta, depois fluida** — padrão consistente nos 3 cenários

---

## Análise: Por que a 1ª resposta demora?

### Causa provável (múltiplos fatores na 1ª chamada)
1. **TTFT do LLM** — maior bottleneck. Opus 4 medido em 31.4s (19/03). Sonnet 4 deve ser mais rápido mas ainda >5s
2. **Cold start do Whisper** — carrega modelo na 1ª transcrição (~3-5s com tiny)
3. **Cold start do TTS** — 1ª geração mais lenta (Edge TTS: conexão WebSocket inicial)
4. **Handshake HTTP/SSL** — 1ª request pro gateway abre conexão

### Por que a 2ª é fluida?
- Whisper já carregado em memória
- TTS já conectado
- Conexão HTTP keep-alive pro gateway
- LLM pode ter cache de contexto (menos tokens pra processar prefill)

### Onde otimizar (pra Claude Code)
1. **Pre-warm Whisper** — carregar modelo no startup, não na 1ª transcrição
2. **Pre-warm TTS** — fazer uma geração silenciosa no startup
3. **Pre-warm gateway** — enviar um ping/health-check pro gateway ao iniciar
4. **Modelo mais leve** — Sonnet 4 ou Haiku em vez de Opus pra voz (TTFT < 5s)
5. **Logging de latência** — adicionar timestamps por fase (STT, LLM TTFT, LLM total, TTS) no server pra medir de verdade

---

## Erros Totais Encontrados

| # | Erro | Cenário | Causa | Status |
|---|------|---------|-------|--------|
| 1 | `python` não encontrado | 2 | VPS sem alias python → python3 | ✅ Fix: setup.sh + venv |
| 2 | Porta 7860 ocupada | 2 | Processo antigo rodando | ✅ Fix: documentado |
| 3 | Porta gateway errada | 2,3 | 18789 hardcoded, VPS usa 19789 | ✅ Fix: auto-detecção |
| 4 | Porta laptop ocupada | 2 | Cenário 1 deixou processo na 7860 | ✅ Fix: documentado |

### Padrão: ZERO erros de código. Todos são config/infra.

---

## Próximos Passos (pra Claude Code)

1. [ ] **Pre-warm** — Whisper + TTS + gateway ping no startup
2. [ ] **Logging de latência** — timestamps por fase em cada request
3. [ ] **Check de porta** — scripts matam processo anterior se porta ocupada
4. [ ] **Modelo de voz** — testar Sonnet/Haiku como opção rápida pra modo voz
5. [ ] **Commit** — todas as mudanças de scripts + docs
6. [ ] Bugs pendentes de `BUGS_PENDENTES.md` (código duplicado, testes flaky)
