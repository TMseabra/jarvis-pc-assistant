"""Pedir coisas a IAs na web (com a tua sessão no browser): imagens no ChatGPT, código no Claude.

Os dois sites aceitam o pedido no link (?q=...), por isso o Jarvis abre a conversa já com o
texto escrito. Usa a conta em que tens sessão iniciada no browser escolhido (JARVIS_BROWSER).
"""

import urllib.parse

from jarvis.actions.system import open_url

SITES = {
    "chatgpt": ("ChatGPT", "https://chatgpt.com/?q="),
    "claude": ("Claude", "https://claude.ai/new?q="),
}

# Por omissão: imagens no ChatGPT (gera imagens), código no Claude.
DEFAULT_SITE = {"image": "chatgpt", "code": "claude", "text": "chatgpt"}
_PREFIX = {
    "image": "Gera uma imagem: ",
    "code": "",
    "text": "",
}


def ask_ai(task: str, kind: str = "text", site: str = "") -> str:
    kind = kind if kind in DEFAULT_SITE else "text"
    site = site.lower().replace("claudinho", "claude").replace("gpt", "chatgpt").replace("chatchatgpt", "chatgpt")
    site = site if site in SITES else DEFAULT_SITE[kind]
    name, base = SITES[site]
    prompt = _PREFIX[kind] + task.strip()
    open_url(base + urllib.parse.quote(prompt))
    what = {"image": "a imagem", "code": "o código"}.get(kind, "o pedido")
    if site == "claude" and not _submit_when_focused("Claude"):
        # O Claude só pré-preenche o pedido: se não confirmámos a janela, não carregamos em Enter às cegas.
        return f"Abri o Claude com o pedido para {what} escrito; carrega em Enter para enviar."
    return f"Pedi ao {name} {what}: \"{task.strip()}\"."


def _submit_when_focused(title_word: str, timeout: float = 12.0) -> bool:
    """Espera que a janela em primeiro plano seja a do site (título com `title_word`) e carrega Enter."""
    import time

    try:
        import win32gui
        from pywinauto.keyboard import send_keys
    except ImportError:
        return False
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if title_word.lower() in win32gui.GetWindowText(win32gui.GetForegroundWindow()).lower():
            time.sleep(2.5)  # deixa a página carregar e pôr o texto na caixa
            if title_word.lower() in win32gui.GetWindowText(win32gui.GetForegroundWindow()).lower():
                send_keys("{ENTER}")
                return True
        time.sleep(0.3)
    return False


# --- continuar a última conversa -------------------------------------------------------

CHAT_URLS = {
    "claude": ("Claude", "https://claude.ai/chat/%"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/c/%"),
}


def last_chat_url(site: str, files=None) -> str | None:
    """URL da última conversa aberta no browser (histórico), ex.: claude.ai/chat/<id>."""
    import shutil
    import sqlite3
    import tempfile
    import uuid
    from pathlib import Path

    from jarvis.actions.media import history_files

    pattern = CHAT_URLS[site][1]
    best = (0, None)
    for history in files if files is not None else history_files():
        copy = Path(tempfile.gettempdir()) / f"jarvis_history_{uuid.uuid4().hex}.sqlite"
        try:
            shutil.copy2(history, copy)
            con = sqlite3.connect(copy)
            row = con.execute("SELECT url, last_visit_time FROM urls WHERE url LIKE ? "
                              "ORDER BY last_visit_time DESC LIMIT 1", (pattern,)).fetchone()
            con.close()
        except (OSError, sqlite3.Error):
            row = None
        finally:
            copy.unlink(missing_ok=True)
        if row and row[1] > best[0]:
            best = (row[1], row[0].split("?")[0])
    return best[1]


def continue_last_chat(site: str = "claude", message: str = "") -> str:
    """Abre a última conversa do Claude/ChatGPT e escreve lá `message` (por omissão: continua)."""
    site = site.lower().replace("claudinho", "claude").replace("gpt", "chatgpt").replace("chatchatgpt", "chatgpt")
    site = site if site in CHAT_URLS else "claude"
    name = CHAT_URLS[site][0]
    url = last_chat_url(site)
    if not url:
        return f"Não encontrei nenhuma conversa do {name} no histórico do browser."
    open_url(url)
    text = message.strip() or "Continua de onde ficámos."
    if not _type_when_focused(name, text):
        return f"Abri a tua última conversa do {name}, mas não consegui escrever lá: escreve tu \"{text}\"."
    return f"Abri a tua última conversa do {name} e pedi: \"{text}\"."


def _type_when_focused(title_word: str, text: str, timeout: float = 15.0) -> bool:
    """Espera que a janela do site esteja à frente, cola `text` na caixa de escrever e envia."""
    import time

    try:
        import win32gui
        from pywinauto.keyboard import send_keys

        from jarvis.actions.desktop_chat import _paste
    except ImportError:
        return False
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if title_word.lower() in win32gui.GetWindowText(win32gui.GetForegroundWindow()).lower():
            time.sleep(3.0)  # a conversa carrega e a caixa de escrever fica com o cursor
            if title_word.lower() in win32gui.GetWindowText(win32gui.GetForegroundWindow()).lower():
                _paste(text)
                send_keys("{ENTER}")
                return True
        time.sleep(0.3)
    return False
