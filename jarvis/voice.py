"""Voz: microfone -> Whisper (local) para entrada; voz neural portuguesa para saída."""

import asyncio
import difflib
import glob
import logging
import os
import re
import sys
import tempfile
import threading
import time
import uuid
import warnings
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# Microfones virtuais/de sistema que alteram ou não captam a voz.
_VIRTUAL_MICS = ("voicemod", "mapeador", "mapper", "stereo mix", "mistura estéreo", "cable output", "virtual")

# Frases que o Whisper "ouve" no silêncio ou ruído.
_HALLUCINATIONS = {
    "obrigado", "obrigada", "obrigado por assistir", "legendas pela comunidade amaraorg",
    "legendado por", "e aí",
}

# Ajuda o Whisper a acertar em nomes que ele não conhece bem.
_WHISPER_PROMPT = (
    "Jarvis, abre o Spotify, o WhatsApp, o Telegram, o Discord e o YouTube. Pesquisa na Internet. "
    "Diz ao Claudinho para continuar."
)


def whisper_prompt() -> str:
    """Texto de contexto do Whisper + os nomes do contactos.txt, para os acertar quando falas."""
    try:
        from jarvis.contacts import known_names

        names = known_names()[:40]
    except Exception:
        names = []
    return _WHISPER_PROMPT + (" Contactos: " + ", ".join(names) + "." if names else "")


def pick_microphone(devices: list[tuple[int, str]], preferred: str | None = None) -> int | None:
    """Escolhe o microfone: o que contém `preferred` no nome, senão o primeiro que não seja virtual.

    `devices` é uma lista de (índice, nome) só com dispositivos de entrada.
    Devolve None para usar o predefinido do sistema.
    """
    if preferred:
        for index, name in devices:
            if preferred.lower() in name.lower():
                return index
    for index, name in devices:
        if not any(v in name.lower() for v in _VIRTUAL_MICS):
            return index
    return None


def is_hallucination(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if not cleaned or cleaned in _HALLUCINATIONS:
        return True
    # Com pouco som, o Whisper às vezes "lê" o initial_prompt ("abre o Spotify, o WhatsApp...").
    prompt = re.sub(r"[^\w\s]", "", _WHISPER_PROMPT.lower())
    return difflib.SequenceMatcher(None, cleaned, prompt).ratio() > 0.6


# "Jarvis, abre o Spotify" / "Ok Jarvis ..." — o Whisper às vezes escreve "Jervis", "Djarvis"...
_WAKE_WORD = re.compile(
    r"^\W*(?:(?:ok|okay|olá|ola|ei|hey|hei|ó|oh)\W+)?(?:jarvis|jervis|djarvis|jarvi|javis|jarbas|jarves)\b\W*",
    re.IGNORECASE,
)


def strip_wake_word(text: str) -> str | None:
    """Se a frase começa por "Jarvis", devolve o resto (pode ser ""); senão None."""
    match = _WAKE_WORD.match(text)
    return text[match.end():].strip() if match else None


def speakable(text: str) -> str:
    """Texto limpo para ler em voz alta (sem markdown, emojis, URLs longos)."""
    text = re.sub(r"https?://\S+", "o link", text)
    text = re.sub(r"[*_`#>|]", "", text)
    text = "".join(ch for ch in text if ch.isalnum() or ch.isspace() or ch in ".,;:!?'\"()-%€ºª/")
    return " ".join(text.split())


def _add_nvidia_dll_dirs():
    """No Windows, as DLLs CUDA instaladas por pip (nvidia-cublas-cu12, ...) não estão no PATH."""
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return
    for base in nvidia.__path__:
        for bin_dir in glob.glob(os.path.join(base, "*", "bin")):
            os.add_dll_directory(bin_dir)
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]


class Transcriber:
    """faster-whisper: tenta a GPU (float16) e cai para o CPU (int8) se não der."""

    def __init__(self, model: str = "large-v3-turbo", device: str = "auto", language: str = "pt"):
        from faster_whisper import WhisperModel

        _add_nvidia_dll_dirs()
        self.language = language
        attempts = [("cuda", "float16"), ("cpu", "int8")] if device == "auto" else [
            (device, "float16" if device == "cuda" else "int8")
        ]
        errors = []
        for dev, compute in attempts:
            # No CPU o large-v3-turbo é lento; o small chega.
            name = model if dev == "cuda" or model != "large-v3-turbo" else "small"
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        self.model = WhisperModel(name, device=dev, compute_type=compute, local_files_only=True)
                    except Exception:
                        self.model = WhisperModel(name, device=dev, compute_type=compute)  # 1.ª vez: download
                    self._warmup()
                self.device, self.model_name = dev, name
                return
            except Exception as exc:
                errors.append(f"{dev}: {exc}")
        raise RuntimeError("Não consegui carregar o Whisper. " + " | ".join(errors))

    def _warmup(self):
        import numpy as np

        # Obriga a carregar as bibliotecas CUDA já (falha aqui e não a meio de um comando).
        list(self.model.transcribe(np.zeros(16000, dtype=np.float32), language=self.language)[0])

    def transcribe(self, samples) -> str:
        segments, _ = self.model.transcribe(
            samples,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            initial_prompt=whisper_prompt(),
            condition_on_previous_text=False,
        )
        kept = [s.text for s in segments if s.no_speech_prob < 0.6]
        text = " ".join(kept).strip()
        return "" if is_hallucination(text) else text


class Speaker:
    """Voz neural (edge-tts, precisa de internet) com recurso ao pyttsx3 se falhar."""

    def __init__(self, voice: str = "pt-PT-DuarteNeural", engine: str = "edge", style: str = "normal"):
        self.voice = voice
        self.engine = engine
        self.style = style  # "normal" ou "jarvis"
        self._fallback = None

    def say(self, text: str):
        text = speakable(text)
        if not text:
            return
        from jarvis.ducking import ducked

        STOP_SPEAKING.clear()
        with ducked():  # baixa a música e os jogos enquanto falo
            self._say(text)

    def _say(self, text: str):
        if self.engine == "edge" and sys.platform == "win32":
            for attempt in range(2):  # uma falha de rede pontual não deve mudar a voz
                try:
                    self._say_edge(text)
                    return
                except Exception as exc:
                    logging.getLogger("jarvis").warning("voz neural falhou (tentativa %d): %s", attempt + 1, exc)
        self._say_pyttsx3(text)

    def _say_edge(self, text: str):
        import edge_tts

        path = Path(tempfile.gettempdir()) / f"jarvis_{uuid.uuid4().hex}.mp3"
        wav = path.with_suffix(".wav")
        try:
            if self.style == "jarvis":
                # Mais grave, um pouco mais rápida e com um efeito digital subtil.
                asyncio.run(edge_tts.Communicate(text, self.voice, rate="+6%", pitch="-7Hz").save(str(path)))
                _write_wav(wav, jarvis_effect(_decode(path)), JARVIS_RATE)
                _play_wav(wav)
            else:
                asyncio.run(edge_tts.Communicate(text, self.voice).save(str(path)))
                _play_mp3_windows(path)
        finally:
            path.unlink(missing_ok=True)
            wav.unlink(missing_ok=True)

    def _say_pyttsx3(self, text: str):
        if self._fallback is None:
            import pyttsx3

            self._fallback = pyttsx3.init()
            # Mesmo género da voz neural escolhida, para não mudar de voz a meio da conversa.
            female = any(n in self.voice for n in ("Raquel", "Francisca", "Female"))
            wanted = ("zira", "helia", "maria", "female") if female else ("david", "mark", "male")
            for v in self._fallback.getProperty("voices"):
                if any(w in (v.name + v.id).lower() for w in wanted):
                    self._fallback.setProperty("voice", v.id)
                    break
        self._fallback.say(text)
        self._fallback.runAndWait()


JARVIS_RATE = 24000


def _decode(path: Path):
    from faster_whisper import decode_audio

    return decode_audio(str(path), sampling_rate=JARVIS_RATE)


def jarvis_effect(audio, rate: int = JARVIS_RATE):
    """Efeito "assistente de IA": tira os graves de fundo, junta um eco metálico muito curto
    (dá o timbre digital) e um pouco de sala, e normaliza. Subtil: a voz continua clara."""
    import numpy as np

    audio = np.asarray(audio, dtype=np.float32)
    # Passa-altos (~150 Hz): tira a média móvel, o que deixa a voz mais "limpa", como num altifalante.
    width = max(1, rate // 150)
    filtered = audio - np.convolve(audio, np.ones(width, dtype=np.float32) / width, mode="same")
    out = filtered.copy()
    for delay_ms, gain in ((9, 0.28), (17, 0.14), (48, 0.10), (95, 0.06)):
        d = int(rate * delay_ms / 1000)
        out[d:] += gain * filtered[:-d]
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.9).astype(np.float32)


def _write_wav(path: Path, audio, rate: int):
    import wave

    import numpy as np

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


# Carregar em "Parar" (ou /parar) corta a voz a meio.
STOP_SPEAKING = threading.Event()


def stop_speaking():
    STOP_SPEAKING.set()


def _play_wav(path: Path):
    import wave
    import winsound

    with wave.open(str(path)) as w:
        duration = w.getnframes() / w.getframerate()
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)  # não usa COM
    end = time.monotonic() + duration + 0.2
    while time.monotonic() < end:
        if STOP_SPEAKING.wait(0.05):
            winsound.PlaySound(None, 0)  # para o som a meio
            return


def _play_mp3_windows(path: Path):
    """Toca um mp3 com o MCI do Windows (sem dependências extra) e espera que acabe.

    Corre numa thread própria com COM em modo STA: o pywinauto (usado no Discord/WhatsApp)
    põe a thread principal em modo MTA, e aí o MCI falha ("erro 266") — era por isso que,
    depois da 1.ª resposta, a voz passava para a de recurso.
    """
    import ctypes
    import threading

    error: list[str] = []

    def play():
        import pythoncom

        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        mci = ctypes.windll.winmm.mciSendStringW
        alias = f"jarvis{uuid.uuid4().hex[:8]}"
        try:
            code = mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
            if code != 0:
                error.append(f"MCI {code}")
                return
            try:
                mci(f"play {alias}", None, 0, None)
                status = ctypes.create_unicode_buffer(32)
                while not STOP_SPEAKING.wait(0.05):
                    mci(f"status {alias} mode", status, 32, None)
                    if status.value != "playing":
                        break
                mci(f"stop {alias}", None, 0, None)
            finally:
                mci(f"close {alias}", None, 0, None)
        finally:
            pythoncom.CoUninitialize()

    thread = threading.Thread(target=play, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise RuntimeError(f"Não consegui tocar o áudio ({error[0]}).")


class Recorder:
    """Grava do microfone usando deteção de voz (Silero VAD), não o volume do som.

    Assim o ruído de fundo (ventoinhas, jogo) não conta como fala, e pausas curtas
    ("hum...") não terminam a gravação: só acaba com `end_silence` segundos sem voz,
    ou quando `should_stop()` devolve True (ex.: carregar em Enter).
    """

    RATE = 16000
    CHUNK = 512  # 32 ms
    START_CHUNKS = 3  # ~100 ms de voz seguida para começar
    PRE_ROLL = 0.5  # segundos guardados antes de detetar a voz (não corta a 1.ª sílaba)

    def __init__(self, mic_index: int | None):
        from faster_whisper.vad import get_vad_model

        self.mic_index = mic_index
        self.vad = get_vad_model()

    def speech_probability(self, previous, chunk) -> float:
        import numpy as np

        return float(self.vad(np.concatenate([previous, chunk]))[-1].squeeze())

    def record(
        self,
        *,
        wait_for_speech: float | None,
        end_silence: float,
        max_seconds: float = 120,
        should_stop=lambda: False,
        on_progress=None,
        wake=None,
    ):
        """Devolve o áudio (float32, 16 kHz) ou None se ninguém falou.

        Com `wake` (WakeWord), vai também medindo a pontuação do "Hey Jarvis": fica em
        self.wake_detected / self.wake_score depois da gravação.
        """
        import collections

        import numpy as np
        import pyaudio

        self.wake_detected, self.wake_score = False, 0.0
        self.wake_at_start = False  # o "Hey Jarvis" foi dito no início da frase (e não a meio)
        speech_t0 = 0.0
        wake_buffer = np.zeros(0, dtype=np.int16)
        if wake is not None:
            wake.reset()

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16, channels=1, rate=self.RATE, input=True,
            input_device_index=self.mic_index, frames_per_buffer=self.CHUNK,
        )
        chunk_s = self.CHUNK / self.RATE
        pre_roll = collections.deque(maxlen=int(self.PRE_ROLL / chunk_s))
        frames: list = []
        previous = np.zeros(self.CHUNK, dtype=np.float32)
        voiced_run, speaking = 0, False
        elapsed = silence = 0.0
        try:
            while True:
                raw = stream.read(self.CHUNK, exception_on_overflow=False)
                chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                prob = self.speech_probability(previous, chunk)
                previous = chunk
                elapsed += chunk_s
                if wake is not None and not self.wake_detected:
                    # O openWakeWord trabalha em blocos de 80 ms (1280 amostras).
                    wake_buffer = np.concatenate([wake_buffer, (chunk * 32767).astype(np.int16)])
                    while len(wake_buffer) >= WakeWord.FRAME:
                        score = wake.score(wake_buffer[:WakeWord.FRAME])
                        wake_buffer = wake_buffer[WakeWord.FRAME:]
                        self.wake_score = max(self.wake_score, score)
                        if score >= wake.threshold:
                            self.wake_detected = True
                            self.wake_at_start = not speaking or elapsed - speech_t0 <= WAKE_START_S
                            if not speaking:  # "Hey Jarvis" conta como início da fala
                                speaking, frames, silence = True, list(pre_roll), 0.0
                            break
                if not speaking:
                    pre_roll.append(chunk)
                    voiced_run = voiced_run + 1 if prob > 0.5 else 0
                    if voiced_run >= self.START_CHUNKS:
                        speaking, frames, silence = True, list(pre_roll), 0.0
                        speech_t0 = elapsed
                    elif should_stop() or (wait_for_speech is not None and elapsed > wait_for_speech):
                        return None
                else:
                    frames.append(chunk)
                    silence = 0.0 if prob > 0.35 else silence + chunk_s
                    duration = len(frames) * chunk_s
                    if silence >= end_silence or should_stop() or duration >= max_seconds:
                        break
                if on_progress and int(elapsed / chunk_s) % 8 == 0:  # ~4x por segundo
                    on_progress(speaking, len(frames) * chunk_s if speaking else 0.0, silence)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
        # Tira o silêncio do fim (fica 0.3 s).
        keep = len(frames) - max(0, int((silence - 0.3) / chunk_s))
        return np.concatenate(frames[:max(keep, 1)])


# "Hey Jarvis" só conta se vier nos primeiros segundos da frase ("…e o Jarvis disse…" não conta).
WAKE_START_S = 2.5


class WakeWord:
    """Deteção local de "Hey Jarvis" com o openWakeWord (funciona com música a tocar).

    O modelo foi treinado com pronúncia inglesa ("Djárvis"): com o "J" português a pontuação
    é baixa, por isso o Jarvis também aceita frases começadas por "Jarvis" via Whisper.
    """

    FRAME = 1280  # 80 ms a 16 kHz

    def __init__(self, threshold: float = 0.3):
        import warnings

        from openwakeword.model import Model
        from openwakeword.utils import download_models

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            except Exception:
                download_models(model_names=["hey_jarvis"])  # 1.ª vez (~5 MB)
                self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        self.threshold = threshold

    def score(self, frame) -> float:
        return float(self.model.predict(frame).get("hey_jarvis", 0.0))

    def reset(self):
        self.model.reset()


def enter_pressed() -> bool:
    """True se carregaram em Enter desde a última vez (sem bloquear). Só no Windows."""
    if sys.platform != "win32":
        return False
    import msvcrt

    pressed = False
    while msvcrt.kbhit():
        if msvcrt.getwch() in ("\r", "\n"):
            pressed = True
    return pressed


class Voice:
    def __init__(
        self,
        language: str = "pt-PT",
        mic: str | None = None,
        whisper_model: str = "large-v3-turbo",
        whisper_device: str = "auto",
        tts_voice: str = "pt-PT-DuarteNeural",
        tts_engine: str = "edge",
        voice_style: str = "normal",
        end_silence: float = 3.0,
        manual_silence: float = 15.0,
        wake_threshold: float | None = 0.3,
    ):
        self.mic_index, self.mic_name = self._find_microphone(mic)
        self.recorder = Recorder(self.mic_index)
        # "Hey Jarvis" local (openWakeWord). None = desligado; se não estiver instalado, fica só o Whisper.
        self.wake = None
        if wake_threshold:
            try:
                self.wake = WakeWord(wake_threshold)
            except Exception as exc:
                logging.getLogger("jarvis").warning("openWakeWord indisponível: %s", exc)
        self.transcriber = Transcriber(whisper_model, whisper_device, language.split("-")[0])
        self.speaker = Speaker(tts_voice, tts_engine, voice_style)
        self.end_silence = end_silence
        self.manual_silence = manual_silence

    @staticmethod
    def _find_microphone(preferred: str | None) -> tuple[int | None, str]:
        import pyaudio

        pa = pyaudio.PyAudio()
        try:
            devices = []
            host_api = pa.get_default_host_api_info()["index"]  # evita duplicados de outras APIs
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info["maxInputChannels"] > 0 and info["hostApi"] == host_api:
                    devices.append((i, info["name"]))
            index = pick_microphone(devices, preferred)
            if index is None:
                return None, pa.get_default_input_device_info()["name"]
            return index, dict(devices)[index]
        finally:
            pa.terminate()

    def listen(self, manual: bool = False, on_progress=None, wait_for_speech: float | None = 30) -> str | None:
        """Grava e transcreve.

        manual=False (mãos-livres): acaba com `end_silence` s de silêncio.
        manual=True (modo Falar): acaba com Enter, ou com `manual_silence` s de silêncio.
        """
        audio = self.record(manual=manual, on_progress=on_progress, wait_for_speech=wait_for_speech)
        return None if audio is None else self.transcribe(audio)

    @property
    def wake_detected(self) -> bool:
        """True se a última gravação (em mãos-livres) ouviu o "Hey Jarvis" no início da frase."""
        return getattr(self.recorder, "wake_detected", False) and getattr(self.recorder, "wake_at_start", True)

    def record(self, manual: bool = False, on_progress=None, wait_for_speech: float | None = 30,
               hands_free: bool = False):
        enter_pressed()  # descarta teclas carregadas antes
        audio = self.recorder.record(
            wait_for_speech=wait_for_speech,
            end_silence=self.manual_silence if manual else self.end_silence,
            should_stop=enter_pressed,
            on_progress=on_progress,
            wake=self.wake if hands_free else None,
            # Com música a tocar o detetor de voz pode nunca ouvir silêncio: limite por pedido.
            max_seconds=20 if hands_free else 120,
        )
        if audio is None or len(audio) < Recorder.RATE * 0.3:
            return None
        return audio

    def transcribe(self, audio) -> str | None:
        return self.transcriber.transcribe(audio) or None

    def say(self, text: str):
        self.speaker.say(text)
