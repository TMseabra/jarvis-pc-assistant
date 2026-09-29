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
    _launch(text)
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


def _launch(*args: str):
    from jarvis.config import PROJECT_ROOT

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([exe, "-m", "jarvis.overlay", *args], creationflags=flags, cwd=str(PROJECT_ROOT))


def show_image(path, seconds: float = 8.0):
    _launch("--image", str(path), "--seconds", str(seconds))


def jumpscare():
    _launch("--jumpscare")


# --- imagem (memes) ----------------------------------------------------------

def run_image(path: str, seconds: float = 8.0):
    """Mostra uma imagem (ou GIF animado) no meio do ecrã, a entrar com um "pop"."""
    import tkinter as tk

    from PIL import Image, ImageSequence, ImageTk

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

    source = Image.open(path)
    frames = [f.convert("RGBA") for f in ImageSequence.Iterator(source)][:120]
    durations = [max(source.info.get("duration", 80), 30) for _ in frames]
    scale = min(width * 0.8 / frames[0].width, height * 0.8 / frames[0].height)
    size = (max(1, int(frames[0].width * scale)), max(1, int(frames[0].height * scale)))
    frames = [f.resize(size) for f in frames]
    item = canvas.create_image(width / 2, height / 2)
    t0 = time.monotonic()
    state = {"frame": 0, "next": t0}
    cache = {}

    def frame():
        now = time.monotonic()
        t = now - t0
        if t > seconds:
            root.destroy()
            return
        if now >= state["next"] and len(frames) > 1:
            state["frame"] = (state["frame"] + 1) % len(frames)
            state["next"] = now + durations[state["frame"]] / 1000
        pop = min(t / 0.35, 1.0)
        zoom = 0.3 + 0.7 * (1 - (1 - pop) ** 3) + 0.08 * math.sin(pop * math.pi)
        zoom = round(zoom, 2)
        key = (state["frame"], zoom)
        if key not in cache:
            img = frames[state["frame"]]
            if zoom != 1.0:
                img = img.resize((max(1, int(size[0] * zoom)), max(1, int(size[1] * zoom))))
            cache[key] = ImageTk.PhotoImage(img)
        canvas.itemconfigure(item, image=cache[key])
        root.after(16, frame)

    frame()
    root.mainloop()


# --- jumpscare ---------------------------------------------------------------

def scary_face(size: int = 900):
    """Uma cara assustadora desenhada na hora (sem imagens da net)."""
    import random

    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new("RGB", (size, size), "black")
    d = ImageDraw.Draw(img)
    s = size / 900
    d.ellipse([150 * s, 60 * s, 750 * s, 880 * s], fill=(205, 200, 185))  # cara pálida
    for cx in (320, 580):  # olhos pretos fundos com pupila vermelha
        d.ellipse([(cx - 95) * s, 250 * s, (cx + 95) * s, 430 * s], fill=(10, 0, 0))
        d.ellipse([(cx - 22) * s, 318 * s, (cx + 22) * s, 362 * s], fill=(255, 20, 20))
    rnd = random.Random(7)
    for cx in (320, 580):  # sangue a escorrer dos olhos
        for _ in range(6):
            x = (cx + rnd.uniform(-70, 70)) * s
            d.line([(x, 400 * s), (x + rnd.uniform(-5, 5) * s, (400 + rnd.uniform(80, 220)) * s)],
                   fill=(150, 0, 0), width=int(rnd.uniform(5, 12) * s))
    d.polygon([(450 * s, 430 * s), (410 * s, 540 * s), (490 * s, 540 * s)], fill=(60, 20, 20))
    d.ellipse([270 * s, 580 * s, 630 * s, 860 * s], fill=(20, 0, 0))  # boca aberta a gritar
    for i in range(9):  # dentes
        x = 290 * s + i * 38 * s
        d.polygon([(x, 600 * s), (x + 34 * s, 600 * s), (x + 17 * s, 660 * s)], fill=(230, 225, 200))
        d.polygon([(x, 845 * s), (x + 34 * s, 845 * s), (x + 17 * s, 790 * s)], fill=(230, 225, 200))
    return img.filter(ImageFilter.GaussianBlur(1.2))


def scream_wav(path, seconds: float = 2.2, rate: int = 22050):
    """Grito: ruído distorcido com um tom agudo a descer, bem alto."""
    import wave

    import numpy as np

    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    rng = np.random.default_rng(3)
    freq = 1400 - 700 * t / seconds + 80 * np.sin(2 * np.pi * 9 * t)
    tone = np.sign(np.sin(2 * np.pi * np.cumsum(freq) / rate))
    noise = rng.uniform(-1, 1, t.size)
    envelope = np.minimum(t / 0.03, 1.0) * np.clip((seconds - t) / 0.4, 0, 1)
    signal = np.clip((0.55 * tone + 0.6 * noise) * envelope * 1.4, -1, 1)
    data = (signal * 32000).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())
    return path


def run_jumpscare(seconds: float = 2.4):
    import random
    import tempfile
    import tkinter as tk
    import winsound
    from pathlib import Path

    from PIL import ImageTk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{width}x{height}+0+0")
    canvas = tk.Canvas(root, width=width, height=height, bg="black", highlightthickness=0)
    canvas.pack()
    root.focus_force()

    face = scary_face()
    wav = scream_wav(Path(tempfile.gettempdir()) / "jarvis_grito.wav", seconds)
    winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
    sizes = [int(min(width, height) * z) for z in (0.5, 0.75, 1.0, 1.15)]
    images = {n: ImageTk.PhotoImage(face.resize((n, n))) for n in sizes}
    item = canvas.create_image(width / 2, height / 2, image=images[sizes[0]])
    t0 = time.monotonic()

    def frame():
        t = time.monotonic() - t0
        if t > seconds:
            root.destroy()
            return
        n = sizes[min(int(t / 0.08), len(sizes) - 1)]
        canvas.itemconfigure(item, image=images[n])
        canvas.coords(item, width / 2 + random.uniform(-40, 40), height / 2 + random.uniform(-40, 40))
        canvas.configure(bg="#8b0000" if int(t * 12) % 3 == 0 else "black")
        root.after(30, frame)

    frame()
    root.mainloop()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--jumpscare"]:
        run_jumpscare()
    elif args[:1] == ["--image"]:
        seconds = float(args[3]) if len(args) > 3 and args[2] == "--seconds" else 8.0
        run_image(args[1], seconds)
    else:
        run(" ".join(args) or "Olá")
