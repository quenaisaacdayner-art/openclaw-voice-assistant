import pyaudio
pa = pyaudio.PyAudio()
print("=== DISPOSITIVOS DE ENTRADA ===")
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info.get("maxInputChannels", 0) > 0:
        name = info["name"]
        ch = info["maxInputChannels"]
        rate = int(info["defaultSampleRate"])
        print(f"  [{i}] {name} (channels={ch}, rate={rate})")

default = pa.get_default_input_device_info()
print(f"\nDefault: [{default['index']}] {default['name']}")
pa.terminate()

# Test our detection function
from voice_assistant_web import find_mic_pyaudio, MIC_INDEX, MIC_NAME
print(f"\nNossa detecção: [{MIC_INDEX}] {MIC_NAME}")
