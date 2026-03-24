# Segurança — OpenClaw Voice Assistant

## Modelo de autenticação

| Cenário | Host | Auth | Comportamento |
|---------|------|------|---------------|
| Local (padrão) | `127.0.0.1` | Nenhuma | Acesso direto — mesmo modelo do OpenClaw |
| VPS / Rede | `0.0.0.0` | Token auto-gerado | URL com token printada no terminal |

### Como funciona

1. Se `SERVER_HOST` é loopback → sem auth (quem acessa o terminal já controla a máquina)
2. Se `SERVER_HOST` não é loopback → token gerado automaticamente em `.ova_token`
3. Terminal printa: `http://<host>:<port>?token=<token>`
4. Token passado via query param no WebSocket handshake
5. Conexão recusada com código 4003 se token inválido

### Regenerar token

Deletar `.ova_token` e reiniciar o server. Um novo token será gerado.

## Proteções implementadas

| Proteção | Descrição |
|----------|-----------|
| XSS | HTML no markdown é escapado (marked.js renderer customizado) |
| Rate limit | 2s entre mensagens de texto, 1s entre speech_end |
| Buffer limit | Áudio máximo 10MB (~5 min) — descartado se exceder |
| Input truncation | Texto truncado em 2000 chars server-side |
| Erros genéricos | Detalhes de erro só nos logs do server, client recebe mensagem genérica |
| CDN removida | marked.js servido localmente (sem dependência externa em runtime) |

## Riscos aceitos (documentados)

### Prompt injection via voz

Alguém pode falar comandos que manipulam o LLM ("ignore suas instruções anteriores..."). Isso é inerente a qualquer aplicação LLM e não tem solução simples. Mitigação: o assistente não tem acesso a ferramentas perigosas (não executa código, não acessa filesystem).

### HTTP em localhost

Tráfego em localhost não passa pela rede — risco de interceptação é negligível. Para acesso remoto, usar SSH tunnel:

```bash
ssh -N -L 7860:127.0.0.1:7860 root@<VPS_IP>
```

### HTTPS para produção

Se quiser expor diretamente na internet (sem SSH tunnel), use nginx como reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name voice.seudominio.com;

    ssl_certificate /etc/letsencrypt/live/voice.seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/voice.seudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

O navegador exige HTTPS para acessar o microfone (exceto em localhost).

### Arquivo temporário STT

O Whisper salva WAV temporário em `/tmp/` com nome aleatório, deletado imediatamente após transcrição. Risco mínimo em máquina single-user.
