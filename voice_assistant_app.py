"""
OpenClaw Voice Assistant — Unified Gradio Interface
Auto-detects LOCAL mode (RealtimeSTT/PyAudio) or BROWSER mode (streaming VAD).

Stack: faster-whisper (STT) + Piper/Edge TTS + OpenClaw Gateway (LLM) + Gradio (UI)
"""

import os
import threading
import queue
import concurrent.futures

import numpy as np
import gradio as gr

from core.config import load_token
from core.history import build_api_history
from core.llm import ask_openclaw, ask_openclaw_stream, _find_sentence_end
from core.stt import transcribe_audio
from core.tts import init_piper, generate_tts

# ─── Mode Detection ──────────────────────────────────────────────────────────

def _detect_mode():
    """Try importing RealtimeSTT + PyAudio in a thread with timeout.
    RealtimeSTT import can hang if audio subsystem is unavailable.
    """
    result = {"mode": "BROWSER"}

    def _try_import():
        try:
            from RealtimeSTT import AudioToTextRecorder  # noqa: F401
            import pyaudio
            pa = pyaudio.PyAudio()
            pa.terminate()
            result["mode"] = "LOCAL"
        except Exception:
            pass

    t = threading.Thread(target=_try_import, daemon=True)
    t.start()
    t.join(timeout=5)
    return result["mode"]


MODE = _detect_mode()

print(f"🔧 Modo detectado: {MODE}")

# ─── Token & TTS init ────────────────────────────────────────────────────────

TOKEN = load_token()
print("✅ Token carregado")
init_piper()

# ─── TTS Thread Pool (buffer duplo: gera TTS em background enquanto LLM streama) ──
_tts_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

# ─── Server config ────────────────────────────────────────────────────────────

SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("PORT", 7860))

# ─── Status Indicators ───────────────────────────────────────────────────────

def _status_html(emoji, label, color):
    return (
        f'<div style="text-align:center;padding:10px 16px;border-radius:10px;'
        f'font-size:1.15em;font-weight:600;color:{color};'
        f'background:color-mix(in srgb, {color} 12%, transparent);'
        f'border:1px solid color-mix(in srgb, {color} 25%, transparent)">'
        f'{emoji} {label}</div>'
    )

STATUS_IDLE = _status_html("⏸️", "Pronto", "#6b7280")
STATUS_LISTENING = _status_html("🔴", "Escutando...", "#e53e3e")
STATUS_THINKING = _status_html("🧠", "Pensando...", "#d69e2e")
STATUS_SPEAKING = _status_html("🔊", "Falando...", "#38a169")

# ─── Microphone Detection (LOCAL mode only) ───────────────────────────────────

MIC_INDEX = None
MIC_NAME = "default"

if MODE == "LOCAL":
    def find_mic_pyaudio():
        """Find best microphone index for PyAudio. Returns (index, name) or (None, 'default')."""
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

                if any(skip in name for skip in ["Iriun", "Virtual", "Mezcla", "Stereo Mix"]):
                    continue

                if "Intel" in name and ("Smart Sound" in name or "Sma" in name):
                    pa.terminate()
                    return i, name

                if "Realtek" in name and "Mic" in name and realtek_mic is None:
                    realtek_mic = (i, name)

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


# ─── Continuous Listening: LOCAL (RealtimeSTT) ────────────────────────────────

class ContinuousListener:
    """Manages RealtimeSTT in a background thread for hands-free voice input."""

    def __init__(self):
        self.recorder = None
        self.running = False
        self.thread = None
        self.text_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._init_error = None
        self.processing = False
        self.partial_text = ""

    def start(self):
        if MODE != "LOCAL":
            print("⚠️ RealtimeSTT não disponível")
            return False
        if self.running:
            return True

        self._stop_event.clear()
        self._ready_event.clear()
        self._init_error = None

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

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
        self.partial_text = ""

    def _on_text(self, text):
        text = text.strip()
        if text:
            print(f"📝 RealtimeSTT transcreveu: '{text}'")
            self.partial_text = ""
            self.text_queue.put(text)

    def _on_partial_text(self, text):
        self.partial_text = text.strip() if text else ""

    def _run(self):
        try:
            print(f"🎤 RealtimeSTT iniciando com mic [{MIC_INDEX}] {MIC_NAME}...")

            self.recorder = AudioToTextRecorder(
                model="small",
                language="pt",
                input_device_index=MIC_INDEX,
                spinner=False,
                silero_sensitivity=0.4,
                post_speech_silence_duration=0.8,
                min_length_of_recording=0.5,
                on_recording_start=lambda: print("🔴 Gravando..."),
                on_recording_stop=lambda: print("⏹️ Processando fala..."),
                on_realtime_transcription_update=self._on_partial_text,
            )

            self.running = True
            self._ready_event.set()
            print("✅ RealtimeSTT pronto — escutando")

            while not self._stop_event.is_set():
                self.recorder.text(self._on_text)

        except Exception as e:
            import traceback
            self._init_error = str(e)
            print(f"⚠️ RealtimeSTT error: {e}")
            traceback.print_exc()
            self._ready_event.set()
        finally:
            self.running = False
            print("🔇 RealtimeSTT parou")

    def get_text(self):
        try:
            return self.text_queue.get_nowait()
        except queue.Empty:
            return None


# ─── Continuous Listening: BROWSER (RMS VAD) ──────────────────────────────────

class BrowserContinuousListener:
    """Accumulates streaming audio from browser mic, detects speech end, transcribes."""

    def __init__(self):
        self.active = False
        self.audio_buffer = []
        self.sample_rate = None
        self.silence_count = 0
        self.speech_detected = False
        self.speech_chunk_count = 0
        self.processing = False
        self.text_queue = queue.Queue()
        self.SILENCE_THRESHOLD = 0.01
        self.SILENCE_CHUNKS_NEEDED = 8
        self.MIN_SPEECH_CHUNKS = 3

    def reset(self):
        self.audio_buffer = []
        self.silence_count = 0
        self.speech_detected = False
        self.speech_chunk_count = 0
        self.sample_rate = None

    def feed_chunk(self, sr, audio_data):
        if not self.active or self.processing:
            return None

        self.sample_rate = sr

        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)
        if audio_data.dtype in (np.int16, np.int32):
            audio_data = audio_data.astype(np.float32) / 32768.0

        rms = np.sqrt(np.mean(audio_data ** 2))

        if rms > self.SILENCE_THRESHOLD:
            self.speech_detected = True
            self.silence_count = 0
            self.speech_chunk_count += 1
            self.audio_buffer.append(audio_data)
        else:
            if self.speech_detected:
                self.audio_buffer.append(audio_data)
                self.silence_count += 1

                if self.silence_count >= self.SILENCE_CHUNKS_NEEDED and self.speech_chunk_count >= self.MIN_SPEECH_CHUNKS:
                    return self._transcribe_buffer()

        return None

    def _transcribe_buffer(self):
        if not self.audio_buffer or self.sample_rate is None:
            self.reset()
            return None

        self.processing = True
        try:
            full_audio = np.concatenate(self.audio_buffer)
            audio_int16 = (full_audio * 32767).astype(np.int16)
            audio_tuple = (self.sample_rate, audio_int16)
            text = transcribe_audio(audio_tuple)
            return text if text else None
        except Exception as e:
            print(f"⚠️ Transcription error: {e}")
            return None
        finally:
            self.reset()
            self.processing = False


# ─── Instantiate the right listener ──────────────────────────────────────────

if MODE == "LOCAL":
    continuous_listener = ContinuousListener()
else:
    continuous_listener = BrowserContinuousListener()


# ─── Chat Logic (shared) ─────────────────────────────────────────────────────

def respond_text(user_message, chat_history):
    """Handle text input with streaming response and sentence-based TTS.

    Buffer duplo: gera TTS da frase N+1 em background enquanto frase N toca.
    """
    if not user_message or not user_message.strip():
        yield "", chat_history, None, STATUS_IDLE
        return

    text = user_message.strip()
    chat_history = chat_history + [{"role": "user", "content": text}]
    api_history = build_api_history(chat_history[:-1])

    full_response = ""
    last_tts_end = 0
    audio = None
    tts_future = None
    tts_end_pos = 0

    yield "", chat_history, None, STATUS_THINKING

    try:
        for partial in ask_openclaw_stream(text, TOKEN, api_history):
            full_response = partial
            updated = chat_history + [{"role": "assistant", "content": partial}]

            # Se TTS em background ficou pronto, emitir áudio
            if tts_future and tts_future.done():
                result = tts_future.result()
                if result:
                    audio = result
                    last_tts_end = tts_end_pos
                tts_future = None
                yield "", updated, audio, STATUS_SPEAKING
                continue

            # Procurar nova frase pra gerar TTS em background
            if not tts_future:
                remaining = partial[last_tts_end:]
                end = _find_sentence_end(remaining)
                if end > 0:
                    sentence = remaining[:end].strip()
                    if sentence:
                        tts_future = _tts_executor.submit(generate_tts, sentence)
                        tts_end_pos = last_tts_end + end

            yield "", updated, audio, STATUS_THINKING

        # Aguardar TTS pendente
        if tts_future:
            result = tts_future.result(timeout=30)
            if result:
                audio = result
                last_tts_end = tts_end_pos
            tts_future = None

        if full_response:
            final = chat_history + [{"role": "assistant", "content": full_response}]
            remaining = full_response[last_tts_end:].strip()
            if remaining:
                final_audio = generate_tts(remaining)
                if final_audio:
                    audio = final_audio
            yield "", final, audio, STATUS_IDLE
        else:
            response = ask_openclaw(text, TOKEN, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield "", final, audio, STATUS_IDLE

    except Exception:
        response = ask_openclaw(text, TOKEN, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield "", final, audio, STATUS_IDLE


def respond_audio(audio_input, chat_history):
    """Handle audio input with streaming response and sentence-based TTS.

    Buffer duplo: gera TTS da frase N+1 em background enquanto frase N toca.
    """
    if audio_input is None:
        yield chat_history, None, STATUS_IDLE
        return

    yield chat_history, None, STATUS_THINKING

    text = transcribe_audio(audio_input)
    if not text:
        yield chat_history + [
            {"role": "assistant", "content": "⚠️ Não captei áudio — tenta de novo"}
        ], None, STATUS_IDLE
        return

    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
    api_history = build_api_history(chat_history[:-1])

    full_response = ""
    last_tts_end = 0
    audio = None
    tts_future = None
    tts_end_pos = 0

    try:
        for partial in ask_openclaw_stream(text, TOKEN, api_history):
            full_response = partial
            updated = chat_history + [{"role": "assistant", "content": partial}]

            if tts_future and tts_future.done():
                result = tts_future.result()
                if result:
                    audio = result
                    last_tts_end = tts_end_pos
                tts_future = None
                yield updated, audio, STATUS_SPEAKING
                continue

            if not tts_future:
                remaining = partial[last_tts_end:]
                end = _find_sentence_end(remaining)
                if end > 0:
                    sentence = remaining[:end].strip()
                    if sentence:
                        tts_future = _tts_executor.submit(generate_tts, sentence)
                        tts_end_pos = last_tts_end + end

            yield updated, audio, STATUS_THINKING

        if tts_future:
            result = tts_future.result(timeout=30)
            if result:
                audio = result
                last_tts_end = tts_end_pos
            tts_future = None

        if full_response:
            final = chat_history + [{"role": "assistant", "content": full_response}]
            remaining = full_response[last_tts_end:].strip()
            if remaining:
                final_audio = generate_tts(remaining)
                if final_audio:
                    audio = final_audio
            yield final, audio, STATUS_IDLE
        else:
            response = ask_openclaw(text, TOKEN, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield final, audio, STATUS_IDLE

    except Exception:
        response = ask_openclaw(text, TOKEN, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield final, audio, STATUS_IDLE


def _process_voice_text(text, chat_history):
    """Process already-transcribed voice text through LLM + TTS. Yields (chat_history, audio, status).

    Buffer duplo: gera TTS da frase N+1 em background enquanto frase N toca.
    """
    chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
    api_history = build_api_history(chat_history[:-1])

    full_response = ""
    last_tts_end = 0
    audio = None
    tts_future = None
    tts_end_pos = 0

    try:
        for partial in ask_openclaw_stream(text, TOKEN, api_history):
            full_response = partial
            updated = chat_history + [{"role": "assistant", "content": partial}]

            if tts_future and tts_future.done():
                result = tts_future.result()
                if result:
                    audio = result
                    last_tts_end = tts_end_pos
                tts_future = None
                yield updated, audio, STATUS_SPEAKING
                continue

            if not tts_future:
                remaining = partial[last_tts_end:]
                end = _find_sentence_end(remaining)
                if end > 0:
                    sentence = remaining[:end].strip()
                    if sentence:
                        tts_future = _tts_executor.submit(generate_tts, sentence)
                        tts_end_pos = last_tts_end + end

            yield updated, audio, STATUS_THINKING

        if tts_future:
            result = tts_future.result(timeout=30)
            if result:
                audio = result
                last_tts_end = tts_end_pos
            tts_future = None

        if full_response:
            final = chat_history + [{"role": "assistant", "content": full_response}]
            remaining = full_response[last_tts_end:].strip()
            if remaining:
                final_audio = generate_tts(remaining)
                if final_audio:
                    audio = final_audio
            yield final, audio, STATUS_IDLE
        else:
            response = ask_openclaw(text, TOKEN, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            yield final, audio, STATUS_IDLE

    except Exception:
        response = ask_openclaw(text, TOKEN, api_history)
        final = chat_history + [{"role": "assistant", "content": response}]
        audio = generate_tts(response)
        yield final, audio, STATUS_IDLE


# ─── Gradio Interface ────────────────────────────────────────────────────────

CUSTOM_CSS = """
#chatbot { min-height: 500px; }
.contain { max-width: 900px; margin: auto; }
footer { display: none !important; }

/* Mobile-friendly */
@media (max-width: 768px) {
    #chatbot { min-height: 300px; }
    .contain { padding: 8px !important; }
    .gr-button { min-height: 44px !important; font-size: 16px !important; }
    .gr-textbox textarea { font-size: 16px !important; }
    #send-btn { min-width: 80px !important; }
}
"""

# Force dark mode on load
DARK_JS = """
() => {
    if (!document.body.classList.contains('dark')) {
        document.body.classList.add('dark');
    }
}
"""

with gr.Blocks(
    title="OpenClaw Voice Assistant",
) as app:

    gr.Markdown(
        """
        # 🎤 OpenClaw Voice Assistant
        **Fale ou digite** — conectado ao seu agente OpenClaw com memória e skills.
        """
    )

    status_indicator = gr.HTML(value=STATUS_IDLE)

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
            send_btn = gr.Button("Enviar", variant="primary", elem_id="send-btn")

    with gr.Row():
        audio_input = gr.Audio(
            sources=["microphone"],
            type="numpy",
            label="🎤 Gravar voz (clique no microfone)",
            streaming=True if MODE == "BROWSER" else False,
        )

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

    partial_text_display = gr.Textbox(
        value="",
        label="🗣️ Transcrição parcial",
        interactive=False,
        visible=(MODE == "LOCAL"),
        max_lines=2,
    )

    audio_output = gr.Audio(
        label="🔊 Resposta em voz",
        type="filepath",
        autoplay=True,
        visible=True,
    )

    with gr.Row():
        clear_btn = gr.Button("🗑️ Limpar conversa", size="sm")

    # ── State ──
    listening_state = gr.State(value=False)

    # ── Events: text ──
    text_input.submit(
        respond_text,
        inputs=[text_input, chatbot],
        outputs=[text_input, chatbot, audio_output, status_indicator],
    )
    send_btn.click(
        respond_text,
        inputs=[text_input, chatbot],
        outputs=[text_input, chatbot, audio_output, status_indicator],
    )
    clear_btn.click(
        lambda: ([], None, STATUS_IDLE),
        outputs=[chatbot, audio_output, status_indicator],
    )

    # ── Mode-specific events ──

    if MODE == "LOCAL":
        # Manual audio: stop_recording triggers transcription
        audio_input.stop_recording(
            respond_audio,
            inputs=[audio_input, chatbot],
            outputs=[chatbot, audio_output, status_indicator],
        )

        def toggle_listening(is_on):
            if is_on:
                continuous_listener.stop()
                return (
                    False,
                    "🎤 Ativar Escuta Contínua",
                    "Escuta contínua: DESLIGADA",
                    gr.update(interactive=True, visible=True),
                    STATUS_IDLE,
                    gr.update(visible=False),
                )
            else:
                ok = continuous_listener.start()
                if ok:
                    return (
                        True,
                        "⏹️ Parar Escuta Contínua",
                        "Escuta contínua: LIGADA — fale normalmente",
                        gr.update(interactive=False, visible=False),
                        STATUS_LISTENING,
                        gr.update(visible=True),
                    )
                return (
                    False,
                    "🎤 Ativar Escuta Contínua",
                    "⚠️ Falha ao iniciar escuta contínua",
                    gr.update(interactive=True, visible=True),
                    STATUS_IDLE,
                    gr.update(visible=False),
                )

        listen_btn.click(
            toggle_listening,
            inputs=[listening_state],
            outputs=[listening_state, listen_btn, listen_status, audio_input,
                     status_indicator, partial_text_display],
        )

        def poll_continuous(chat_history, is_on):
            """Check if RealtimeSTT has new text; if so, process it."""
            partial = continuous_listener.partial_text if is_on else ""

            if not is_on or continuous_listener.processing:
                status = STATUS_LISTENING if is_on else STATUS_IDLE
                yield chat_history, None, status, partial
                return

            text = continuous_listener.get_text()
            if not text:
                yield chat_history, None, STATUS_LISTENING, partial
                return

            continuous_listener.processing = True
            try:
                for hist, audio, status in _process_voice_text(text, chat_history):
                    yield hist, audio, status, ""
            finally:
                continuous_listener.processing = False

        poll_timer = gr.Timer(value=1)
        poll_timer.tick(
            poll_continuous,
            inputs=[chatbot, listening_state],
            outputs=[chatbot, audio_output, status_indicator, partial_text_display],
        )

    else:
        # BROWSER mode: streaming audio + VAD

        def toggle_listening(is_on):
            if is_on:
                continuous_listener.active = False
                continuous_listener.reset()
                return (
                    False,
                    "🎤 Ativar Escuta Contínua",
                    "Modo manual — grave e solte para transcrever",
                    STATUS_IDLE,
                )
            else:
                continuous_listener.active = True
                continuous_listener.reset()
                return (
                    True,
                    "⏹️ Parar Escuta Contínua",
                    "Escuta contínua LIGADA — clique no mic acima e fale normalmente",
                    STATUS_LISTENING,
                )

        listen_btn.click(
            toggle_listening,
            inputs=[listening_state],
            outputs=[listening_state, listen_btn, listen_status, status_indicator],
        )

        def handle_stream_chunk(audio_chunk, chat_history):
            """In continuous mode: feed chunks to VAD. In manual mode: accumulate."""
            if audio_chunk is None:
                return chat_history, None, gr.skip()

            sr, data = audio_chunk

            if not continuous_listener.active:
                # Manual mode: accumulate chunks for stop_recording handler
                continuous_listener.sample_rate = sr
                audio_data = data.copy()
                if len(audio_data.shape) > 1:
                    audio_data = audio_data.mean(axis=1)
                if audio_data.dtype in (np.int16, np.int32):
                    audio_data = audio_data.astype(np.float32) / 32768.0
                continuous_listener.audio_buffer.append(audio_data)
                return chat_history, None, gr.skip()

            # Continuous mode: VAD-based auto-segmentation
            text = continuous_listener.feed_chunk(sr, data)

            if not text:
                return chat_history, None, gr.skip()

            print(f"📝 Escuta contínua transcreveu: '{text}'")
            chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
            api_history = build_api_history(chat_history[:-1])

            response = ask_openclaw(text, TOKEN, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            return final, audio, STATUS_IDLE

        audio_input.stream(
            handle_stream_chunk,
            inputs=[audio_input, chatbot],
            outputs=[chatbot, audio_output, status_indicator],
        )

        def handle_stop_recording(chat_history):
            """When user stops recording in manual mode, transcribe the full buffer."""
            if continuous_listener.active:
                if continuous_listener.speech_detected and continuous_listener.audio_buffer:
                    text = continuous_listener._transcribe_buffer()
                    if text:
                        print(f"📝 Escuta contínua (stop) transcreveu: '{text}'")
                        chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
                        api_history = build_api_history(chat_history[:-1])
                        response = ask_openclaw(text, TOKEN, api_history)
                        final = chat_history + [{"role": "assistant", "content": response}]
                        audio = generate_tts(response)
                        return final, audio, STATUS_IDLE
                continuous_listener.reset()
                return chat_history, None, STATUS_LISTENING

            # Manual mode: transcribe full accumulated buffer
            buf = continuous_listener.audio_buffer
            sr = continuous_listener.sample_rate
            continuous_listener.audio_buffer = []
            continuous_listener.sample_rate = None

            if not buf or sr is None:
                return chat_history, None, STATUS_IDLE

            full_audio = np.concatenate(buf)
            audio_int16 = (full_audio * 32767).astype(np.int16)
            audio_tuple = (sr, audio_int16)
            text = transcribe_audio(audio_tuple)

            if not text:
                return chat_history + [
                    {"role": "assistant", "content": "⚠️ Não captei áudio — tenta de novo"}
                ], None, STATUS_IDLE

            chat_history = chat_history + [{"role": "user", "content": f"[🎤 Voz]: {text}"}]
            api_history = build_api_history(chat_history[:-1])

            full_response = ""
            audio = None
            try:
                for partial in ask_openclaw_stream(text, TOKEN, api_history):
                    full_response = partial
                if full_response:
                    final = chat_history + [{"role": "assistant", "content": full_response}]
                    audio = generate_tts(full_response)
                    return final, audio, STATUS_IDLE
            except Exception:
                pass

            response = ask_openclaw(text, TOKEN, api_history)
            final = chat_history + [{"role": "assistant", "content": response}]
            audio = generate_tts(response)
            return final, audio, STATUS_IDLE

        audio_input.stop_recording(
            handle_stop_recording,
            inputs=[chatbot],
            outputs=[chatbot, audio_output, status_indicator],
        )


# ─── Launch ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if MODE == "BROWSER":
        print(f"\n🚀 Servidor iniciando na porta {SERVER_PORT}...")
        print(f"   Modo: BROWSER (mic via streaming do navegador)")
        print(f"\n📡 Acesse via SSH tunnel: ssh -N -L {SERVER_PORT}:127.0.0.1:{SERVER_PORT} root@<VPS_IP>")
        print(f"   Depois abra: http://127.0.0.1:{SERVER_PORT}\n")
    else:
        print(f"\n🚀 Abrindo no browser...")
        print(f"   Modo: LOCAL (RealtimeSTT + PyAudio)")

    app.launch(
        server_name=SERVER_HOST,
        server_port=SERVER_PORT,
        share=False,
        inbrowser=(MODE == "LOCAL"),
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css=CUSTOM_CSS,
        js=DARK_JS,
    )
