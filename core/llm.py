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
    """Encontra ponto de split pra TTS em texto parcial do LLM.

    Prioridade:
    1. Pontuação forte (.!?…) seguida de espaço ou fim
    2. Ponto-e-vírgula ou dois-pontos seguidos de espaço
    3. Vírgula seguida de espaço (só se texto > 80 chars — evita splits muito curtos)

    Retorna posição APÓS o separador (incluindo o espaço). 0 se não encontrou.
    """
    # Prioridade 1: pontuação forte
    m = re.search(r'[.!?…](\s|$)', text)
    if m:
        return m.end()

    # Prioridade 2: ponto-e-vírgula, dois-pontos
    m = re.search(r'[;:](\s|$)', text)
    if m:
        return m.end()

    # Prioridade 3: vírgula (só se texto longo o suficiente)
    if len(text) > 80:
        m = re.search(r',\s', text)
        if m:
            return m.end()

    return 0
