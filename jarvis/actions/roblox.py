"""Entrar num jogo do Roblox pelo nome: pesquisa na Roblox e abre o jogo com o link roblox://."""

import os
import time
import uuid

import httpx

SEARCH = "https://apis.roblox.com/search-api/omni-search"


def search_games(query: str, http=None) -> list[dict]:
    """[{name, place_id, players}] pela ordem de relevância da Roblox."""
    http = http or httpx.Client(timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    data = http.get(SEARCH, params={"searchQuery": query, "sessionId": str(uuid.uuid4()), "pageType": "all"}).json()
    games = []
    for group in data.get("searchResults", []):
        for item in group.get("contents", []):
            if item.get("rootPlaceId"):
                games.append({
                    "name": item.get("name", "?"),
                    "place_id": item["rootPlaceId"],
                    "players": item.get("playerCount") or 0,
                })
    return games


def _roblox_running() -> bool:
    import win32gui
    import win32process

    from jarvis.actions.media import _process_name

    found = []

    def visit(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if _process_name(pid).lower().startswith("robloxplayer"):
                found.append(hwnd)

    win32gui.EnumWindows(visit, None)
    return bool(found)


def play(game: str, search=search_games, launch=None, wait_seconds: float = 25) -> str:
    """Procura o jogo e entra nele. Confirma que a janela do Roblox abriu."""
    try:
        results = search(game)
    except (httpx.HTTPError, ValueError) as exc:
        return f"Não consegui pesquisar no Roblox: {exc}"
    if not results:
        return f"Não encontrei nenhum jogo do Roblox chamado '{game}'."
    best = results[0]
    link = f"roblox://experiences/start?placeId={best['place_id']}"
    (launch or os.startfile)(link)  # type: ignore[attr-defined]
    players = f", {best['players']} a jogar" if best["players"] else ""
    if launch is None:  # verificação real: a janela do Roblox apareceu?
        end = time.monotonic() + wait_seconds
        while time.monotonic() < end:
            if _roblox_running():
                return f"Entrei no jogo {best['name']} no Roblox{players}."
            time.sleep(1)
        return f"Mandei o Roblox abrir {best['name']}, mas a janela do jogo não apareceu (o Roblox está instalado?)."
    return f"Entrei no jogo {best['name']} no Roblox{players}."
