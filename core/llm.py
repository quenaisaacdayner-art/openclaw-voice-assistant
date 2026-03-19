"""Comunicação com OpenClaw Gateway API."""

import json
import re

import requests

from core.config import GATEWAY_URL, MODEL


def ask_openclaw(text, token, history_messages):
    """Envia texto pro gateway OpenClaw. Retorna resposta ou string de erro."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    messages = list(history_messages) + [{"role": "user", "content": text}]
    body = {"model": MODEL, "messages": messages}

    try:
        resp = requests.post(GATEWAY_URL, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.ConnectionError:
        return "❌ OpenClaw não respondeu. Gateway tá rodando?"
    except requests.Timeout:
        return "❌ Timeout — OpenClaw demorou demais."
    except (requests.RequestException, KeyError, IndexError) as e:
        return f"❌ Erro: {e}"


def ask_openclaw_stream(text, token, history_messages):
    """Envia texto com streaming SSE. Gera texto acumulado a cada chunk."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    messages = list(history_messages) + [{"role": "user", "content": text}]
    body = {"model": MODEL, "messages": messages, "stream": True}

    resp = requests.post(
        GATEWAY_URL, headers=headers, json=body, timeout=120, stream=True
    )
    resp.raise_for_status()

    full_text = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data_str = line[len("data: "):]
        if data_str.strip() == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
            content = chunk["choices"][0].get("delta", {}).get("content", "")
            if content:
                full_text += content
                yield full_text
        except (json.JSONDecodeError, KeyError, IndexError):
            continue


def _find_sentence_end(text):
    """Posição após primeira pontuação de fim de frase seguida de espaço."""
    m = re.search(r'[.!?…]\s', text)
    return m.end() if m else 0
