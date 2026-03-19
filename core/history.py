"""Gerenciamento de histórico de conversa."""

MAX_HISTORY = 10  # exchanges (20 mensagens)


def build_api_history(chat_history):
    """Converte histórico do Gradio pra mensagens da API OpenClaw."""
    messages = []
    for msg in chat_history:
        if msg["role"] in ("user", "assistant"):
            content = msg.get("content", "")
            if not content:
                continue
            # Remove prefixo de voz "[🎤 Voz]: " mas mantém o conteúdo
            if content.startswith("[🎤"):
                idx = content.find("]: ")
                if idx != -1:
                    content = content[idx + 3:]
                # Se não tem "]: ", mantém como está
            if content:
                messages.append({"role": msg["role"], "content": content})
    # Manter últimas N
    return messages[-(MAX_HISTORY * 2):]
