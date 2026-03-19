"""Teste isolado do TTS — descobre onde tá o problema."""
import asyncio
import os
import subprocess
import edge_tts

VOICE = "pt-BR-AntonioNeural"
TEXT = "Olá Dayner, este é um teste de áudio do OpenClaw. Se você está ouvindo isso, o TTS funciona."
OUT_FILE = os.path.join(os.path.dirname(__file__), "teste_tts.mp3")

async def gerar():
    print(f"🔊 Gerando áudio com edge-tts...")
    print(f"   Voz: {VOICE}")
    print(f"   Texto: {TEXT}")
    comm = edge_tts.Communicate(TEXT, VOICE)
    await comm.save(OUT_FILE)

asyncio.run(gerar())

# Verificar arquivo
if os.path.exists(OUT_FILE):
    size = os.path.getsize(OUT_FILE)
    print(f"\n✅ Arquivo gerado: {OUT_FILE}")
    print(f"   Tamanho: {size} bytes")
    
    if size < 100:
        print("   ⚠️ ARQUIVO MUITO PEQUENO — provavelmente corrompido")
    else:
        print("   📊 Tamanho parece OK")
    
    # Ler primeiros bytes pra verificar se é MP3 válido
    with open(OUT_FILE, "rb") as f:
        header = f.read(4)
    
    if header[:3] == b'ID3' or header[:2] == b'\xff\xfb' or header[:2] == b'\xff\xf3':
        print("   ✅ Header MP3 válido")
    else:
        print(f"   ⚠️ Header não parece MP3: {header.hex()}")
    
    # Tentar abrir com start
    print(f"\n🎵 Abrindo com 'start' (player padrão do Windows)...")
    result = subprocess.run(["start", "", OUT_FILE], shell=True, capture_output=True, text=True)
    print(f"   Return code: {result.returncode}")
    if result.stderr:
        print(f"   ❌ Stderr: {result.stderr}")
    
    print(f"\n💡 Se NÃO abriu, tenta manualmente:")
    print(f"   1. Abre o Explorer em: {os.path.dirname(OUT_FILE)}")
    print(f"   2. Dá duplo-clique em 'teste_tts.mp3'")
    print(f"   3. Se abrir = problema é no script. Se não = problema é player/codec.")
else:
    print("❌ Arquivo NÃO foi gerado — edge-tts falhou")
