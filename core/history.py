"""Gerenciamento de histórico de conversa."""

MAX_HISTORY = 10  # exchanges (20 mensagens)


def build_api_history(chat_history):
    """Converte histórico do Gradio pra mensagens da API OpenClaw."""
    messages = []
    for msg in chat_history:
        if msg["role"] in ("user", "assistant"):
            content = msg.get("content", "")
            # BUG CONHECIDO: filtra mensagens [🎤 inteiras (Fase 2 vai corrigir)
            if content and not content.startswith("[🎤"):
                messages.append({"role": msg["role"], "content": content})
    # Manter últimas N
    return messages[-(MAX_HISTORY * 2):]
