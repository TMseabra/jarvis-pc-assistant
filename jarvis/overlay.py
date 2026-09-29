"""Texto grande e animado por cima de tudo no ecrã ("diz olá no ecrã do PC").

Corre num processo à parte (`python -m jarvis.overlay "Olá"`), para não bloquear o Jarvis:
as letras entram a crescer, ondulam com cores do arco-íris e desaparecem ao fim de uns segundos.
Clicar ou carregar numa tecla fecha logo.
"""

import colorsys
import math
import re
import subprocess
import sys
import time

TRANSPARENT = "#010203"  # cor que o Windows torna transparente
DURATION = 5.0


def show(text: str) -> str:
    """Lança a animação e volta logo."""
    text = " ".join(text.split())[:40] or "Olá"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    from jarvis.config import PROJECT_ROOT

    subprocess.Popen([exe, "-m", "jarvis.overlay", text], creationflags=flags, cwd=str(PROJECT_ROOT))
    return f"Pus \"{text}\" em grande no ecrã do PC."


def _font_size(text: str, width: int) -> int:
    return max(60, min(260, int(width * 1.5 / max(len(text), 1))))


def run(text: str):
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", TRANSPARENT)
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{width}x{height}+0+0")
    canvas = tk.Canvas(root, width=width, height=height, bg=TRANSPARENT, highlightthickness=0)
    canvas.pack()
    root.bind("<Button>", lambda e: root.destroy())
    root.bind("<Key>", lambda e: root.destroy())
    root.focus_force()

    size = _font_size(text, width)
    spacing = size * 0.62
    start_x = width / 2 - spacing * (len(text) - 1) / 2
    letters = []
    for i, ch in enumerate(text):
        shadow = canvas.create_text(0, 0, text=ch, fill="#000000", font=("Segoe UI Black", size, "bold"))
        letter = canvas.create_text(0, 0, text=ch, fill="#ffffff", font=("Segoe UI Black", size, "bold"))
        letters.append((i, shadow, letter))
    t0 = time.monotonic()

    def frame():
        t = time.monotonic() - t0
        if t > DURATION:
            root.destroy()
            return
        # Entrada: cada letra cai de cima com um salto; saída: sobem e desvanecem.
        for i, shadow, letter in letters:
            delay = i * 0.08
            appear = min(max((t - delay) / 0.5, 0.0), 1.0)
            bounce = 1 - (1 - appear) ** 3 + 0.12 * math.sin(appear * math.pi) if appear < 1 else 1.0
            leave = max(t - (DURATION - 0.7), 0) / 0.7
            y = height / 2 - (1 - bounce) * height * 0.6 - leave * height * 0.3 + 25 * math.sin(t * 5 + i * 0.6)
            x = start_x + i * spacing
            hue = (t * 0.25 + i * 0.07) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
            color = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
            visible = appear > 0 and leave < 1
            canvas.coords(letter, x, y)
            canvas.coords(shadow, x + size * 0.05, y + size * 0.05)
            canvas.itemconfigure(letter, fill=color, state="normal" if visible else "hidden")
            canvas.itemconfigure(shadow, state="normal" if visible else "hidden")
        root.after(16, frame)

    frame()
    root.mainloop()


# "diz olá na tela do pc", "mostra 'bom dia' no ecrã", "escreve olá no ecrã em grande"
REQUEST = re.compile(
    r"^\W*(?:(?:jarvis|podes|consegues)\W+)*(?:diz(?:er)?|escreve(?:r)?|mostra(?:r)?|p[oõ]e|mete)\s+"
    r"(?P<text>.+?)\s+(?:n[oa]|em)\s+(?:tela|ecr[aã]|monitor)(?:\s+d[oa]\s+(?:pc|computador))?"
    r"(?:\s+(?:em\s+)?grande)?\W*$",
    re.IGNORECASE,
)


def parse_request(text: str) -> str | None:
    m = REQUEST.match(text)
    if not m:
        return None
    words = m.group("text").strip().strip("\"'“”")
    if re.fullmatch(r"(?:o|a|me|-me|o que est[aá])", words, re.IGNORECASE):
        return None  # "mostra-me o ecrã" é um print
    words = {"ola": "Olá", "ole": "Olé", "adeus": "Adeus"}.get(words.lower(), words)
    return words[:1].upper() + words[1:]


if __name__ == "__main__":
    run(" ".join(sys.argv[1:]) or "Olá")
