"""Mensagens novas no Instagram, TikTok e LinkedIn (no browser, com a tua sessão).

Abre a caixa de mensagens de cada site num separador, lê o contador que o site põe no título
("(3) Instagram"), e fecha o separador outra vez (Ctrl+W, só se o separador à frente for o do site).
"""

import re
import time

from jarvis.actions import system

SITES = {
    "instagram": ("Instagram", "https://www.instagram.com/direct/inbox/"),
    "tiktok": ("TikTok", "https://www.tiktok.com/messages"),
    "linkedin": ("LinkedIn", "https://www.linkedin.com/messaging/"),
}
_COUNT = re.compile(r"^\s*\((\d+)\+?\)")
_LOGIN = re.compile(r"iniciar sess|log ?in|entrar|sign ?in|inscrever|sign ?up", re.IGNORECASE)


def _foreground_title() -> str:
    import win32gui

    return win32gui.GetWindowText(win32gui.GetForegroundWindow())


def read_title(title: str, name: str) -> str:
    """Título do separador -> resumo. '(3) Instagram' -> '3 novidades'."""
    m = _COUNT.match(title)
    if m:
        return f"{name}: tens {m.group(1)} mensagens/notificações por ver."
    if _LOGIN.search(title):
        return f"{name}: não tens sessão iniciada no browser."
    return f"{name}: nada de novo."


def check_site(key: str, wait_title=_foreground_title, settle: float = 5.0, timeout: float = 20.0) -> str:
    from pywinauto.keyboard import send_keys

    name, url = SITES[key]
    system.open_url(url)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if name.lower() in wait_title().lower():
            break
        time.sleep(0.4)
    else:
        return f"{name}: a página não abriu a tempo."
    time.sleep(settle)  # o contador de mensagens só aparece depois de a página carregar
    title = wait_title()
    summary = read_title(title, name)
    if name.lower() in title.lower():
        send_keys("^w")  # fecha só este separador
    return summary


def check_all(keys=("instagram", "tiktok", "linkedin")) -> list[str]:
    out = []
    for key in keys:
        try:
            out.append(check_site(key))
        except Exception as exc:
            out.append(f"{SITES[key][0]}: não consegui ver ({exc}).")
    return out
