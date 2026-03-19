"""Medir latência de cada etapa do pipeline."""
import time
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from core.config import load_token, WHISPER_MODEL_SIZE
from core.stt import transcribe_audio
from core.tts import init_tts, generate_tts
from core.llm import ask_openclaw, ask_openclaw_stream

TOKEN = load_token()
init_tts()

# 1. Whisper carregamento (já feito no import, mas vamos forçar)
print("\n=== LATÊNCIA POR ETAPA ===\n")

# 2. LLM - primeira resposta
t0 = time.time()
resp = ask_openclaw("oi", TOKEN, [])
t_llm = time.time() - t0
print(f"LLM (completo): {t_llm:.1f}s — resposta: {resp[:80]}...")

# 3. LLM streaming - tempo até primeiro token
t0 = time.time()
first_token_time = None
full = ""
for partial in ask_openclaw_stream("diz oi", TOKEN, []):
    if first_token_time is None:
        first_token_time = time.time() - t0
    full = partial
t_stream_total = time.time() - t0
print(f"LLM stream TTFT: {first_token_time:.1f}s | total: {t_stream_total:.1f}s")

# 4. TTS
t0 = time.time()
audio = generate_tts("Olá, como você está?")
t_tts = time.time() - t0
print(f"TTS: {t_tts:.1f}s — arquivo: {audio}")

# 5. TTS frase longa
t0 = time.time()
audio2 = generate_tts("Esta é uma frase mais longa para testar o tempo de geração do TTS com Edge, que precisa ir até os servidores da Microsoft e voltar.")
t_tts2 = time.time() - t0
print(f"TTS (longa): {t_tts2:.1f}s")

print(f"\n=== TOTAL ESTIMADO (voz→resposta→voz) ===")
print(f"Whisper: ~3-5s (small) / ~1-2s (tiny)")
print(f"LLM TTFT: {first_token_time:.1f}s")
print(f"TTS 1ª frase: {t_tts:.1f}s")
print(f"TOTAL MÍNIMO: {first_token_time + t_tts:.1f}s (sem transcrição)")
