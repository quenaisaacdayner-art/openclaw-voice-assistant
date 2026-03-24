# prompts/ — Estrutura de Prompts pro Claude Code

> Cada pasta = 1 subtítulo do ROADMAP.md
> **Usar os arquivos `_completo.md`** — prompts unificados com todas as features do subtítulo
> Os arquivos individuais (s1a, s1b...) são referência detalhada mas NÃO precisam ser executados separadamente

## Como executar

```
Abrir Claude Code no projeto →
"Leia prompts/s1_interface/s1_completo.md e execute"
→ testar → comitar →
"Leia prompts/s2_pipeline_audio/s2_completo.md e execute"
→ e assim por diante
```

## Organização

```
prompts/
├── README.md                         ← Este arquivo
├── _historico/                       ← Fases 1-9 (já executados)
│
├── s1_interface/
│   ├── s1_completo.md                ← 🎯 USAR ESTE (8 features)
│   ├── s1a_disconnect_interrupt.md   ← Referência detalhada
│   ├── s1b_text_input.md
│   ├── s1c_timer_mute_visual.md
│   ├── s1d_esfera_pulsante.md
│   └── s1e_markdown_config.md
│
├── s2_pipeline_audio/
│   ├── s2_completo.md                ← 🎯 USAR ESTE (3 features)
│   ├── s2a_whisper_small_banner.md   ← Referência detalhada
│   ├── s2b_seletor_vozes.md
│   └── s2c_velocidade_tts.md
│
├── s3_latencia/
│   └── s3_completo.md                ← 🎯 USAR ESTE (4 otimizações)
│
├── s4_transporte/
│   └── s4_completo.md                ← 🎯 USAR ESTE (3 features: backoff, keepalive, session)
│
├── s5_robustez/
│   └── s5_completo.md                ← 🎯 USAR ESTE (5 fixes: markdown TTS, timeout, race, cleanup, aviso)
│
├── s6_deploy/
├── s7_seguranca/
└── s8_conversacao/
```

## Ordem de execução

1. **S1** ✅ Interface & Interação (8 features)
2. **S2** ✅ Pipeline de Áudio (3 features)
3. **S3** ✅ Latência (4 otimizações)
4. **S4** ✅ Transporte & Conexão (backoff, keepalive, session persistence)
5. **S5** ✅ Robustez (markdown TTS, timeout LLM, race condition, cleanup, aviso sessão)
6. **S6** ✅ Deploy & Distribuição (setup Windows, CI, README, limpeza)
7. **S7** ✅ Segurança (auth token, XSS fix, rate limit, buffer limit, input validation, erros genéricos, CDN local)
8. **S8** ← PRÓXIMO (conversação: timestamps, export JSON)

## Regras

1. **1 prompt completo = 1 sessão do Claude Code**
2. **Commit após cada prompt executado com sucesso**
3. **Testes:** `python -m pytest tests/ -v` após cada prompt
4. **Se quebrar:** reverter e investigar antes de prosseguir
5. NÃO paralelizar S1 e S2 (tocam os mesmos arquivos)
