"""Música (Spotify) e vídeos (YouTube).

Spotify sem configuração: teclas multimédia (▶⏸⏭⏮) e confirmação pelo título da janela
("Spotify Premium" = em pausa; "Artista - Música" = a tocar). Assim nunca dizemos que
está a tocar sem estar. Para tocar uma música/artista/playlist pelo nome é preciso a
API do Spotify (ver spotify_api.py).
"""

import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

from jarvis.actions import spotify_api
from jarvis.actions.system import open_url

_PAUSED_TITLES = {"spotify", "spotify premium", "spotify free"}
_VK = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1}
_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0 Safari/537.36",
    "Accept-Language": "pt-PT,pt;q=0.9",
}


def _http_get(url: str) -> str:
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = None
    request = urllib.request.Request(url, headers=_UA)
    return urllib.request.urlopen(request, timeout=10, context=context).read().decode("utf-8", "replace")


# --- YouTube -----------------------------------------------------------------

def first_youtube_video(html: str) -> tuple[str, str] | None:
    """(id, título) do primeiro vídeo da página de resultados do YouTube (ignora anúncios)."""
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}', html)
    if not m:
        return None
    try:
        title = json.loads(f'"{m.group(2)}"')  # desfaz &, \" ...
    except ValueError:
        title = m.group(2)
    return m.group(1), title


def play_youtube(query: str) -> str:
    """Pesquisa no YouTube e abre logo o primeiro vídeo (a tocar)."""
    results = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    try:
        video = first_youtube_video(_http_get(results))
    except OSError:
        video = None
    if not video:
        open_url(results)
        return f"Abri os resultados do YouTube para '{query}' (não consegui escolher um vídeo sozinho)."
    video_id, title = video
    open_url(f"https://www.youtube.com/watch?v={video_id}")
    return f"Pus a tocar no YouTube: \"{title}\"."


def search_tiktok(query: str) -> str:
    """Abre a pesquisa do TikTok (a página precisa de JavaScript, por isso não escolhemos o vídeo)."""
    open_url("https://www.tiktok.com/search?q=" + urllib.parse.quote(query))
    return f"Abri o TikTok com a pesquisa '{query}'."


# --- Spotify -----------------------------------------------------------------

def spotify_title() -> str | None:
    """Título da janela principal do Spotify, ou None se não estiver aberto."""
    import win32gui
    import win32process

    titles = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) and not win32gui.GetWindowText(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or win32gui.GetClassName(hwnd) != "Chrome_WidgetWin_1":
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if _process_name(pid).lower() == "spotify.exe":
            titles.append(title)

    win32gui.EnumWindows(visit, None)
    return titles[0] if titles else None


def _process_name(pid: int) -> str:
    import win32api
    import win32con
    import win32process

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            return os.path.basename(win32process.GetModuleFileNameEx(handle, 0))
        finally:
            win32api.CloseHandle(handle)
    except Exception:
        return ""


def is_playing(title: str | None) -> bool:
    return bool(title) and title.strip().lower() not in _PAUSED_TITLES


def _media_key(name: str):
    import ctypes

    vk = _VK[name]
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP


def _wait_title(condition, timeout: float = 6.0) -> str | None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        title = spotify_title()
        if condition(title):
            return title
        time.sleep(0.3)
    return None


def _ensure_spotify() -> str:
    title = spotify_title()
    if title is None:
        os.startfile("spotify:")  # type: ignore[attr-defined]
        title = _wait_title(lambda t: t is not None, timeout=20)
        if title is None:
            raise OSError("Não consegui abrir o Spotify.")
        time.sleep(2)  # dá tempo à app para carregar antes de receber teclas
        title = spotify_title()
    return title or ""


def music(action: str, query: str = "") -> str:
    """action: play | pause | next | previous. `query` (opcional, com play): o que tocar."""
    action = (action or "play").lower()
    title = _ensure_spotify()

    if action == "play" and query.strip():
        if spotify_api.configured():
            return spotify_api.play(query.strip())
        os.startfile("spotify:search:" + urllib.parse.quote(query.strip()))  # type: ignore[attr-defined]
        return (
            f"Abri a pesquisa de '{query}' no Spotify, mas não consigo pôr a tocar sozinho sem a ligação "
            "à API do Spotify (vê a secção Spotify do README). Carrega no play do primeiro resultado."
        )

    if action == "play":
        if is_playing(title):
            return f"Já está a tocar: {title}."
        if spotify_api.configured():
            return spotify_api.play("")  # "a minha música": as tuas músicas guardadas
        _media_key("play_pause")
        playing = _wait_title(is_playing)
        return f"A tocar: {playing}." if playing else "Carreguei no play, mas o Spotify não começou a tocar."

    if action == "pause":
        if not is_playing(title):
            return "O Spotify já está em pausa."
        _media_key("play_pause")
        return "Pus o Spotify em pausa." if _wait_title(lambda t: not is_playing(t)) is not None else \
            "Carreguei na pausa, mas o Spotify continua a tocar."

    if action in ("next", "previous"):
        _media_key(action)
        changed = _wait_title(lambda t: is_playing(t) and t != title, timeout=4)
        return f"A tocar: {changed}." if changed else "Mudei de música."

    raise ValueError(f"Ação de música desconhecida: '{action}'. Usa play, pause, next ou previous.")
