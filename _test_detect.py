import time
import threading

def _detect_mode():
    result = {"mode": "BROWSER"}
    def _try_import():
        try:
            t0 = time.time()
            from RealtimeSTT import AudioToTextRecorder
            print(f"  RealtimeSTT importou em {time.time()-t0:.1f}s")
            import pyaudio
            pa = pyaudio.PyAudio()
            pa.terminate()
            result["mode"] = "LOCAL"
        except Exception as e:
            print(f"  Erro: {e}")
    t = threading.Thread(target=_try_import, daemon=True)
    t.start()
    t.join(timeout=5)
    if t.is_alive():
        print(f"  TIMEOUT! Thread ainda rodando após 5s")
    return result["mode"]

t0 = time.time()
mode = _detect_mode()
print(f"Modo detectado: {mode} ({time.time()-t0:.1f}s)")
