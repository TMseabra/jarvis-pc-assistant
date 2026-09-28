"""O gravador com deteção de voz, alimentado por um microfone falso (ficheiro .wav)."""

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("faster_whisper")
from jarvis.voice import Recorder  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "duas_frases.wav"
# duas_frases.wav (medido com o VAD): fala de ~1.25 s a ~3.9 s, pausa de ~2.4 s,
# fala de ~6.3 s a ~8.3 s, depois ruído leve até aos 13.2 s.
SPEECH_START, SPEECH_END, PAUSE = 1.25, 8.3, 2.4


class FakeStream:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def read(self, n, exception_on_overflow=True):
        chunk = self.data[self.pos:self.pos + n * 2]
        self.pos += n * 2
        return chunk.ljust(n * 2, b"\0")  # depois do fim: silêncio

    def stop_stream(self):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_mic(monkeypatch):
    with wave.open(str(FIXTURE)) as w:
        data = w.readframes(w.getnframes())
    stream = FakeStream(data)

    class FakePyAudio:
        def open(self, **kwargs):
            return stream

        def terminate(self):
            pass

    fake = type(sys)("pyaudio")
    fake.PyAudio, fake.paInt16 = FakePyAudio, 8
    monkeypatch.setitem(sys.modules, "pyaudio", fake)
    return stream


def seconds(audio) -> float:
    return len(audio) / Recorder.RATE


def test_records_both_sentences_across_the_pause(fake_mic):
    audio = Recorder(None).record(wait_for_speech=5, end_silence=3.0)
    # Não cortou na pausa de 2.4 s: tem as duas frases (+ 0.5 s de pré-gravação).
    assert seconds(audio) == pytest.approx(SPEECH_END - SPEECH_START + 0.5, abs=0.7)
    # Parou ~3 s depois do fim da fala, não no fim do ficheiro.
    assert fake_mic.pos / 2 / Recorder.RATE == pytest.approx(SPEECH_END + 3.0, abs=0.6)


def test_short_end_silence_stops_at_the_pause(fake_mic):
    audio = Recorder(None).record(wait_for_speech=5, end_silence=PAUSE - 1)
    assert seconds(audio) < 4  # só a primeira frase


def test_stop_key_ends_recording(fake_mic):
    reads = {"n": 0}

    def stop_after_3s():
        reads["n"] += 1
        return reads["n"] * Recorder.CHUNK / Recorder.RATE > 3.0

    audio = Recorder(None).record(wait_for_speech=5, end_silence=15, should_stop=stop_after_3s)
    assert seconds(audio) < 3


def test_no_speech_returns_none(monkeypatch, fake_mic):
    fake_mic.data = (np.zeros(16000 * 3, dtype=np.int16)).tobytes()
    assert Recorder(None).record(wait_for_speech=2, end_silence=2) is None
