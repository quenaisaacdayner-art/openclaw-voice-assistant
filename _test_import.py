import traceback
try:
    from RealtimeSTT import AudioToTextRecorder
    print("OK")
except Exception as e:
    traceback.print_exc()
