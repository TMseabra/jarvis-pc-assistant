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
