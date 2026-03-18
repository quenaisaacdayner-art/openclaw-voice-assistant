"""
OpenClaw Voice Assistant — Web Interface (Gradio)
Talk to your OpenClaw agent via browser: type or record voice.

Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway (LLM) + Gradio (UI)
"""

import os
import json
import re
import asyncio
import tempfile
import wave
import threading
import queue
import numpy as np
import requests
import gradio as gr
from faster_whisper import WhisperModel
import edge_tts
import scipy.io.wavfile as wavfile

# Piper TTS (local, higher quality voice)
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

# RealtimeSTT (continuous listening with VAD)
try:
    from RealtimeSTT import AudioToTextRecorder
    REALTIME_STT_AVAILABLE = True
except ImportError:
    REALTIME_STT_AVAILABLE = False

# ─── Microphone Detection (PyAudio — used by RealtimeSTT) ─────────────────────

def find_mic_pyaudio():
    """Find best microphone index for PyAudio. Returns (index, name) or (None, 'default').
    
    Priority:
    1. Intel Smart Sound (built-in mic array — best quality)
    2. Realtek HD Audio Mic (built-in analog mic — good fallback)
    3. Any real mic that isn't a virtual camera
    4. System default (None = let PyAudio decide)
    """
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        realtek_mic = None
        any_real_mic = None

        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) <= 0:
                continue
            name = info.get("name", "")

            # Skip virtual cameras and mixers
            if any(skip in name for skip in ["Iriun", "Virtual", "Mezcla", "Stereo Mix"]):
                continue

            # Priority 1: Intel Smart Sound (name may be truncated)
            if "Intel" in name and ("Smart Sound" in name or "Sma" in name):
                pa.terminate()
                return i, name

            # Priority 2: Realtek analog mic
            if "Realtek" in name and "Mic" in name and realtek_mic is None:
                realtek_mic = (i, name)

            # Priority 3: Any real mic
            if any_real_mic is None and any(kw in name.lower() for kw in ["micrófono", "microphone", "microfone", "mic"]):
                any_real_mic = (i, name)

        pa.terminate()

        if realtek_mic:
            return realtek_mic
        if any_real_mic:
            return any_real_mic
        return None, "default (nenhum mic real encontrado)"
    except Exception as e:
        print(f"⚠️ Erro detectando mic: {e}")
        return None, "default"

MIC_INDEX, MIC_NAME = find_mic_pyaudio()
print(f"🎤 Microfone selecionado: [{MIC_INDEX}] {MIC_NAME}")

# ─── Configuration ────────────────────────────────────────────────────────────

GATEWAY_URL = os.environ.get(
    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions"
)
MODEL = os.environ.get("OPENCLAW_MODEL", "openclaw:main")
TTS_VOICE = os.environ.get("TTS_VOICE", "pt-BR-AntonioNeural")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper")  # "piper" (local) or "edge" (Microsoft)
PIPER_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "pt_BR-faber-medium.onnx")

# ─── Load Token ───────────────────────────────────────────────────────────────

def load_token():
    config_path = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        token = config["gateway"]["auth"]["token"]
        if token:
            return token
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if token:
        return token
    raise RuntimeError("Token não encontrado. Configure em ~/.openclaw/openclaw.json ou OPENCLAW_GATEWAY_TOKEN")

# ─── Globals (loaded once at startup) ────────────────────────────────────────

# Whisper loaded lazily on first manual transcription to avoid
# duplicating the ~460MB model when RealtimeSTT is used instead.
whisper_model = None
_whisper_lock = threading.Lock()

def _get_whisper():
    global whisper_model
    if whisper_model is None:
        with _whisper_lock:
            if whisper_model is None:
                print(f"⏳ Carregando Whisper ({WHISPER_MODEL_SIZE})...")
                whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
                print("✅ Whisper pronto")
    return whisper_model

TOKEN = load_token()
print("✅ Token carregado")

# Load Piper voice model
piper_voice = None
if TTS_ENGINE == "piper" and PIPER_AVAILABLE and os.path.exists(PIPER_MODEL):
    print(f"⏳ Carregando Piper TTS ({os.path.basename(PIPER_MODEL)})...")
    piper_voice = PiperVoice.load(PIPER_MODEL)
    print("✅ Piper TTS pronto")
elif TTS_ENGINE == "piper":
    print("⚠️ Piper indisponível — usando Edge TTS como fallback")
    TTS_ENGINE = "edge"

# ─── Transcription ────────────────────────────────────────────────────────────

def transcribe_audio(audio_input):
    """Transcribe audio from Gradio's gr.Audio component."""
    if audio_input is None:
        return ""

    # Gradio returns (sample_rate, numpy_array) for microphone input
    sr, audio_data = audio_input

    # Convert to mono if stereo
    if len(audio_data.shape) > 1:
        audio_data = audio_data.mean(axis=1)

    # Normalize to int16 if float
    if audio_data.dtype in (np.float32, np.float64):
        audio_data = (audio_data * 32767).astype(np.int16)

    # Save to temp WAV
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    wavfile.write(tmp.name, sr, audio_data)

    try:
        segments, _ = _get_whisper().transcribe(
            tmp.name,
            language="pt",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text
    except Exception as e:
        return f"[Erro na transcrição: {e}]"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

# ─── OpenClaw API ─────────────────────────────────────────────────────────────

def ask_openclaw(text, history_messages):
    """Send text to OpenClaw gateway."""
    headers = {
        "Authorization": f"Bearer {TOKEN}",
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


def ask_openclaw_stream(text, history_messages):
    """Send text to OpenClaw gateway with streaming (SSE). Yields accumulated text."""
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    messages = list(history_messages) + [{"role": "user", "content": text}]
    body = {"model": MODEL, "messages": messages, "stream": True}

    with requests.post(GATEWAY_URL, headers=headers, json=body, timeout=120, stream=True) as resp:
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
    """Position after the first sentence-ending punctuation followed by whitespace."""
    m = re.search(r'[.!?…]\s', text)
    return m.end() if m else 0


# ─── TTS ──────────────────────────────────────────────────────────────────────

def generate_tts_piper(text):
    """Generate TTS with Piper (local, higher quality). Returns path to WAV."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    try:
        audio_bytes = b""
        last_chunk = None
        for chunk in piper_voice.synthesize(text):
            audio_bytes += chunk.audio_int16_bytes
            last_chunk = chunk

        if not audio_bytes or last_chunk is None:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            return None

        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(last_chunk.sample_channels)
            wf.setsampwidth(last_chunk.sample_width)
            wf.setframerate(last_chunk.sample_rate)
            wf.writeframes(audio_bytes)

        if os.path.getsize(tmp.name) > 100:
            return tmp.name
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    except Exception as e:
        print(f"⚠️ Piper TTS error: {e}")
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return None


def generate_tts_edge(text):
    """Generate TTS with Edge TTS (Microsoft, online). Returns path to MP3."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()

    try:
        async def _gen():
            communicate = edge_tts.Communicate(text, TTS_VOICE)
            await communicate.save(tmp.name)

        # Gradio 6.x runs its own event loop — asyncio.run() would crash.
        # Run in a fresh thread with its own loop to be safe everywhere.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _gen()).result(timeout=30)

        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 100:
            return tmp.name
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    except Exception as e:
        print(f"⚠️ Edge TTS error: {e}")
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return None


_previous_tts_file = None
_tts_file_lock = threading.Lock()

def generate_tts(text):
    """Generate TTS audio. Uses Piper (local) or Edge (online) based on config."""
    global _previous_tts_file

    if not text or text.startswith("❌"):
        return None

    # Clean up previous TTS file (Gradio already served it by now)
    with _tts_file_lock:
        old_file = _previous_tts_file
        _previous_tts_file = None
    if old_file:
        try:
            os.unlink(old_file)
        except OSError:
            pass

    # Truncate for TTS
    tts_text = text[:1500] + "..." if len(text) > 1500 else text

    result = None
    if TTS_ENGINE == "piper" and piper_voice is not None:
        result = generate_tts_piper(tts_text)
        if not result:
            # Fallback to Edge if Piper fails
            result = generate_tts_edge(tts_text)
    else:
        result = generate_tts_edge(tts_text)

    with _tts_file_lock:
        _previous_tts_file = result
    return result

# ─── Chat Logic ───────────────────────────────────────────────────────────────

MAX_HISTORY = 10  # exchanges (20 messages)

def build_api_history(chat_history):
    """Convert Gradio chat history to OpenClaw API messages."""
    messages = []
    for msg in chat_history:
        if msg["role"] in ("user", "assistant"):
            content = msg.get("content", "")
            if content and not content.startswith("[🎤"):
                messages.append({"role": msg["role"], "content": content})
    # Keep last N
    return messages[-(MAX_HISTORY * 2):]

def _process_streaming_response(text, chat_history, api_history):
    """Stream LLM response with sentence-based TTS. Yields (chat_history, audio).

    Shared logic for text input, audio input, and continuous listening.
    """
    full_response = ""
    first_tts_done = False
    first_tts_end = 0
    audio = None

    try:
        for partial in ask_openclaw_stream(text, api_history):
            full_response = partial
            updated = chat_history + [{"role": "assistant", "content": partial}]

            # Generate TTS for first complete sentence (early voice)
            if not first_tts_done:
                end = _find_sentence_end(partial)
                if end > 0:
                    audio = generate_tts(partial[:end].strip())
                    if audio:
                        first_tts_done = True
                        first_tts_end = end
                        yield updated, audio
                        continue

            yield updated, audio

        # Streaming done
        if full_response:
            final = chat_history + [{"role": "assistant", "content": full_response}]
            # TTS for remaining unspoken text
            remaining = full_response[first_tts_end:].strip() if first_tts_done else full_response
            if remaining:
                final_audio = generate_tts(remaining)
                if final_audio:
                    audio = final_audio
            yield final, audio
        else:
            # Streaming yielded nothing — fallback to non-streaming
            response = ask_openclaw(text, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield final, audio

    except Exception as e:
        print(f"⚠️ Streaming failed, falling back to non-streaming: {e}")
        response = ask_openclaw(text, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield final, audio


def respond_text(user_message, chat_history):
    """Handle text input with streaming response and sentence-based TTS."""
    if not user_message or not user_message.strip():
        yield "", chat_history, None
        return

    text = user_message.strip()
    chat_history = chat_history + [{"role": "user", "content": text}]
    api_history = build_api_history(chat_history[:-1])

    for updated, audio in _process_streaming_response(text, chat_history, api_history):
        yield "", updated, audio


def respond_audio(audio_input, chat_history):
    """Handle audio input with streaming response and sentence-based TTS."""
    if audio_input is None:
        yield chat_history, None
        return

    # Transcribe
    text = transcribe_audio(audio_input)
    if not text:
        yield chat_history + [
            {"role": "assistant", "content": "⚠️ Não captei áudio — tenta de novo"}
        ], None
        return

    # Show what was transcribed
    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
    api_history = build_api_history(chat_history[:-1])

    for updated, audio in _process_streaming_response(text, chat_history, api_history):
        yield updated, audio

# ─── Continuous Listening (RealtimeSTT) ───────────────────────────────────────

class ContinuousListener:
    """Manages RealtimeSTT in a background thread for hands-free voice input."""

    def __init__(self):
        self.recorder = None
        self.running = False
        self.thread = None
        self.text_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()  # signals that recorder initialized OK
        self._init_error = None  # stores init error message
        self._processing = False  # guard against overlapping poll_continuous calls
        self._processing_lock = threading.Lock()

    def try_start_processing(self):
        """Atomically check-and-set processing flag. Returns True if acquired."""
        with self._processing_lock:
            if self._processing:
                return False
            self._processing = True
            return True

    def finish_processing(self):
        """Release processing flag."""
        with self._processing_lock:
            self._processing = False

    def start(self):
        if not REALTIME_STT_AVAILABLE:
            print("⚠️ RealtimeSTT não disponível")
            return False
        if self.running:
            return True

        self._stop_event.clear()
        self._ready_event.clear()
        self._init_error = None

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        # Wait up to 30s for recorder to initialize (it downloads models on first run)
        ok = self._ready_event.wait(timeout=30)
        if not ok or self._init_error:
            print(f"❌ RealtimeSTT falhou ao iniciar: {self._init_error or 'timeout'}")
            self.stop()
            return False
        return True

    def stop(self):
        self._stop_event.set()
        if self.recorder:
            try:
                self.recorder.stop()
            except Exception:
                pass
            try:
                self.recorder.shutdown()
            except Exception:
                pass
        self.running = False
        self.recorder = None

    def _on_text(self, text):
        """Called by RealtimeSTT when a complete utterance is detected."""
        text = text.strip()
        if text:
            print(f"📝 RealtimeSTT transcreveu: '{text}'")
            self.text_queue.put(text)

    def _run(self):
        try:
            mic_idx = MIC_INDEX
            mic_name = MIC_NAME
            print(f"🎤 RealtimeSTT iniciando com mic [{mic_idx}] {mic_name}...")

            self.recorder = AudioToTextRecorder(
                model="small",
                language="pt",
                input_device_index=mic_idx,
                spinner=False,
                silero_sensitivity=0.4,
                post_speech_silence_duration=0.8,
                min_length_of_recording=0.5,
                on_recording_start=lambda: print("🔴 Gravando..."),
                on_recording_stop=lambda: print("⏹️ Processando fala..."),
            )

            self.running = True
            self._ready_event.set()  # signal success to start()
            print("✅ RealtimeSTT pronto — escutando")

            while not self._stop_event.is_set():
                self.recorder.text(self._on_text)

        except Exception as e:
            import traceback
            self._init_error = str(e)
            print(f"⚠️ RealtimeSTT error: {e}")
            traceback.print_exc()
            self._ready_event.set()  # unblock start() even on failure
        finally:
            self.running = False
            print("🔇 RealtimeSTT parou")

    def get_text(self):
        """Non-blocking: returns transcribed text or None."""
        try:
            return self.text_queue.get_nowait()
        except queue.Empty:
            return None


continuous_listener = ContinuousListener()


# ─── Gradio Interface ────────────────────────────────────────────────────────

CUSTOM_CSS = """
#chatbot { min-height: 500px; }
.contain { max-width: 900px; margin: auto; }
footer { display: none !important; }
"""

with gr.Blocks(
    title="OpenClaw Voice Assistant",
) as app:

    gr.Markdown(
        """
        # 🎤 OpenClaw Voice Assistant
        **Fale ou digite** — conectado ao seu agente OpenClaw com memória e skills.

        *Stack: faster-whisper (STT) + edge-tts (TTS) + OpenClaw Gateway (LLM) + Gradio (UI) — 100% grátis*
        """
    )

    chatbot = gr.Chatbot(
        elem_id="chatbot",
        label="Conversa",
        height=500,
    )

    with gr.Row():
        with gr.Column(scale=4):
            text_input = gr.Textbox(
                placeholder="Digite sua mensagem...",
                show_label=False,
                container=False,
                scale=4,
            )
        with gr.Column(scale=1, min_width=100):
            send_btn = gr.Button("Enviar", variant="primary")

    with gr.Row():
        audio_input = gr.Audio(
            sources=["microphone"],
            type="numpy",
            label="🎤 Gravar voz (clique no microfone)",
        )

    # Continuous listening toggle (only if RealtimeSTT is available)
    if REALTIME_STT_AVAILABLE:
        with gr.Row():
            listen_btn = gr.Button(
                "🎤 Ativar Escuta Contínua",
                variant="secondary",
                size="sm",
            )
            listen_status = gr.Textbox(
                value="Escuta contínua: DESLIGADA",
                label="Status",
                interactive=False,
                max_lines=1,
            )

    audio_output = gr.Audio(
        label="🔊 Resposta em voz",
        type="filepath",
        autoplay=True,
        visible=True,
    )

    with gr.Row():
        clear_btn = gr.Button("🗑️ Limpar conversa", size="sm")

    # Events
    text_input.submit(
        respond_text,
        inputs=[text_input, chatbot],
        outputs=[text_input, chatbot, audio_output],
    )
    send_btn.click(
        respond_text,
        inputs=[text_input, chatbot],
        outputs=[text_input, chatbot, audio_output],
    )
    audio_input.stop_recording(
        respond_audio,
        inputs=[audio_input, chatbot],
        outputs=[chatbot, audio_output],
    )
    clear_btn.click(lambda: ([], None), outputs=[chatbot, audio_output])

    # ── Continuous Listening events ──
    if REALTIME_STT_AVAILABLE:
        listening_state = gr.State(value=False)

        def toggle_listening(is_on):
            if is_on:
                continuous_listener.stop()
                return (
                    False,
                    "🎤 Ativar Escuta Contínua",
                    "Escuta contínua: DESLIGADA",
                    gr.update(interactive=True, visible=True),
                )
            else:
                ok = continuous_listener.start()
                if ok:
                    return (
                        True,
                        "⏹️ Parar Escuta Contínua",
                        "Escuta contínua: LIGADA — fale normalmente",
                        gr.update(interactive=False, visible=False),
                    )
                return (
                    False,
                    "🎤 Ativar Escuta Contínua",
                    "⚠️ Falha ao iniciar escuta contínua",
                    gr.update(interactive=True, visible=True),
                )

        listen_btn.click(
            toggle_listening,
            inputs=[listening_state],
            outputs=[listening_state, listen_btn, listen_status, audio_input],
        )

        def poll_continuous(chat_history, is_on):
            """Check if RealtimeSTT has new text; if so, process it like a voice input."""
            if not is_on or not continuous_listener.try_start_processing():
                yield chat_history, None
                return

            try:
                text = continuous_listener.get_text()
                if not text:
                    yield chat_history, None
                    return

                # Process just like respond_audio but with already-transcribed text
                chat_history = chat_history + [
                    {"role": "user", "content": f"[🎤 Voz]: {text}"}
                ]
                api_history = build_api_history(chat_history[:-1])

                for updated, audio in _process_streaming_response(text, chat_history, api_history):
                    yield updated, audio
            finally:
                continuous_listener.finish_processing()

        # Poll every 1 second using a Timer
        poll_timer = gr.Timer(value=1)
        poll_timer.tick(
            poll_continuous,
            inputs=[chatbot, listening_state],
            outputs=[chatbot, audio_output],
        )

# ─── Launch ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🚀 Abrindo no browser...")
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css=CUSTOM_CSS,
    )
