"""`Jarvis.bat --testar-jarvis`: mostra ao vivo a pontuação do "Hey Jarvis" no teu microfone.

Serve para veres como dizer a palavra para ativar sempre (o modelo prefere a pronúncia
inglesa, "Djárvis") e, se preciso, ajustar JARVIS_WAKE_THRESHOLD no .env.
"""

import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

from jarvis.config import config
from jarvis.voice import Voice, WakeWord, enter_pressed


def bar(score: float, threshold: float, width: int = 40) -> Text:
    filled = int(min(score, 1.0) * width)
    mark = int(threshold * width)
    text = Text("  ")
    for i in range(width):
        if i == mark:
            text.append("│", style="bold yellow")
        elif i < filled:
            text.append("█", style="bold green" if score >= threshold else "cyan")
        else:
            text.append("·", style="grey35")
    text.append(f"  {score:.2f}", style="bold")
    return text


def run(seconds: float = 60) -> int:
    import numpy as np
    import pyaudio

    console = Console(highlight=False)
    threshold = config.wake_threshold or 0.3
    mic_index, mic_name = Voice._find_microphone(config.mic)
    wake = WakeWord(threshold)
    console.print(f"\n[bold cyan]Teste do “Hey Jarvis”[/]  ·  microfone: {mic_name}  ·  limiar: {threshold}")
    console.print("[#7a8ba8]Diz “Hey Jarvis” de várias formas. A barra fica verde quando ativava. "
                  "Enter para sair.[/]\n")
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                     input_device_index=mic_index, frames_per_buffer=WakeWord.FRAME)
    activations, best, recent = 0, 0.0, 0.0
    end = time.monotonic() + seconds
    try:
        with Live(console=console, refresh_per_second=15) as live:
            while time.monotonic() < end and not enter_pressed():
                frame = np.frombuffer(stream.read(WakeWord.FRAME, exception_on_overflow=False), dtype=np.int16)
                score = wake.score(frame)
                recent = max(score, recent * 0.85)  # a barra desce devagar para se conseguir ler
                if score >= threshold and best < threshold:
                    activations += 1
                best = score if score >= threshold else max(best * 0.9, score)
                line = bar(recent, threshold)
                line.append(f"   ativações: {activations}", style="green" if activations else "grey50")
                live.update(line)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
    console.print(f"\n{activations} ativação(ões). Se o teu “Hey Jarvis” fica perto da linha amarela sem a passar, "
                  "baixa JARVIS_WAKE_THRESHOLD no .env (ex.: 0.2).")
    return 0
