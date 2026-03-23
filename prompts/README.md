# prompts/ — Estrutura de Prompts pro Claude Code

> Cada pasta = 1 subtítulo do ROADMAP.md
> Cada arquivo = 1 prompt auto-contido (Claude Code lê e executa)
> Ordem de execução: dentro de cada pasta, seguir a numeração (A, B, C...)

## Organização

```
prompts/
├── README.md                    ← Este arquivo
├── _historico/                  ← Prompts das fases 1-9 (já executados)
│   ├── fase1.md
│   ├── fase1_otimizacao.md
│   ├── fase2.md
│   ├── ...
│   └── fase9_autodetect_port.md
│
├── s1_interface/                ← Subtítulo 1: Interface & Interação
│   ├── s1a_disconnect_interrupt.md
│   ├── s1b_text_input.md
│   ├── s1c_timer_mute_visual.md
│   ├── s1d_esfera_pulsante.md
│   └── s1e_markdown_config.md
│
├── s2_pipeline_audio/           ← Subtítulo 2: Pipeline de Áudio (STT + TTS)
│   └── (a definir)
│
├── s3_latencia/                 ← Subtítulo 3: Latência End-to-End
│   └── (a definir)
│
├── s4_transporte/               ← Subtítulo 4: Transporte & Conexão
│   └── (a definir)
│
├── s5_robustez/                 ← Subtítulo 5: Robustez & Stress Test
│   └── (a definir)
│
├── s6_deploy/                   ← Subtítulo 6: Deploy & Distribuição
│   └── (a definir)
│
├── s7_seguranca/                ← Subtítulo 7: Segurança
│   └── (a definir)
│
└── s8_conversacao/              ← Subtítulo 8: Conversação & Contexto
    └── (a definir)
```

## Regras

1. **Ordem:** dentro de cada sN_xxx/, executar A → B → C (sequencial)
2. **Paralelo:** entre pastas diferentes PODE ser paralelo, MAS só se os prompts tocam arquivos diferentes
3. **Como executar:** Abrir Claude Code → "Leia prompts/s1_interface/s1a_disconnect_interrupt.md e execute"
4. **Commit:** após cada prompt executado com sucesso
5. **Testes:** rodar `python -m pytest tests/ -v` após cada prompt
6. **Se falhar:** reverter, investigar, não pular pra próximo
