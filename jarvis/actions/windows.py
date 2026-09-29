"""Depois de abrir uma app/jogo: esperar pela janela, pô-la à frente e (nas apps) maximizá-la.

Corre numa thread à parte, para o Jarvis responder logo. Nos jogos, a janela pode demorar
(o Valorant abre primeiro o Riot Client), e o launcher às vezes rouba o foco: por isso
continuamos a vigiar durante uns segundos e voltamos a pôr o jogo à frente.
"""

import re
import threading
import time
import unicodedata

from jarvis.config import config


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def _keys(label: str) -> list[str]:
    """'Spotify Premium' -> ['spotify']; 'VALORANT' -> ['valorant']; 'Visual Studio Code' -> ['visualstudiocode', 'code']."""
    words = [_fold(w) for w in label.split()]
    keys = [_fold(label)] + [w for w in words[:1] + words[-1:] if len(w) >= 4]
    return list(dict.fromkeys(k for k in keys if len(k) >= 3))


def matches(label: str, title: str, exe: str) -> bool:
    if "jarvis" in _fold(title):
        return False
    haystack = _fold(title) + " " + _fold(exe.rsplit("\\", 1)[-1])
    return any(k in haystack for k in _keys(label))


def find_window(label: str):
    import win32gui
    import win32process

    from jarvis.actions.system import _process_exe

    found = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if matches(label, title, _process_exe(pid)):
            found.append(hwnd)

    win32gui.EnumWindows(visit, None)
    return found[0] if found else None


def bring_to_front(hwnd, maximize: bool) -> bool:
    import win32api
    import win32con
    import win32gui

    try:
        if maximize:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        elif win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        # O Windows só deixa mudar o foco a quem recebeu input: um Alt "falso" desbloqueia.
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(hwnd)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False


def _watch(label: str, maximize: bool, timeout: float, keep: float):
    import win32gui

    end = time.monotonic() + timeout
    hwnd = None
    while time.monotonic() < end and not hwnd:
        hwnd = find_window(label)
        if not hwnd:
            time.sleep(1.0)
    if not hwnd:
        return
    bring_to_front(hwnd, maximize)
    # Durante `keep` segundos, se outra janela (o launcher) lhe roubar o foco, volta a pô-la à frente.
    stop = time.monotonic() + keep
    while time.monotonic() < stop:
        time.sleep(2.0)
        if not win32gui.IsWindow(hwnd):
            hwnd = find_window(label)  # os jogos às vezes trocam de janela ao carregar
            if not hwnd:
                return
        if win32gui.GetForegroundWindow() != hwnd:
            bring_to_front(hwnd, False)


def focus_later(label: str, game: bool = False):
    """Põe a janela de `label` à frente assim que aparecer (maximizada, se for uma app)."""
    if not config.maximize_windows and not game:
        return
    timeout, keep = (240.0, 30.0) if game else (20.0, 0.0)
    threading.Thread(target=_watch, args=(label, not game and config.maximize_windows, timeout, keep),
                     daemon=True, name=f"focus-{label}").start()
