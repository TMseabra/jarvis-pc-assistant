"""Riot Client: depois de o abrir, carregar no botão vermelho "Play" (o launcher não expõe os
botões ao Windows, por isso procuramos o botão na imagem da janela e clicamos nele)."""

import time
from collections import deque

import numpy as np

GAME_PROCESSES = {"valorant": "valorant-win64-shipping.exe", "league_of_legends": "league of legends.exe"}


def find_play_button(rgb: np.ndarray, block: int = 8) -> tuple[int, int] | None:
    """Centro (x, y) do botão "Play" vermelho numa imagem da janela do Riot Client, ou None.

    Procura a maior mancha vermelha (o botão, #FF4655) no quarto inferior esquerdo da janela;
    o ícone vermelho do jogo na barra lateral é pequeno demais para ganhar.
    """
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    red = (r > 200) & (r - g > 100) & (r - b > 90)
    h, w = red.shape
    zone_top, zone_right = int(h * 0.55), int(w * 0.5)
    zone = red[zone_top:, :zone_right]
    zh, zw = zone.shape[0] // block * block, zone.shape[1] // block * block
    if not zh or not zw:
        return None
    blocks = zone[:zh, :zw].reshape(zh // block, block, zw // block, block).mean(axis=(1, 3)) > 0.5
    seen = np.zeros_like(blocks)
    best: list[tuple[int, int]] = []
    for y in range(blocks.shape[0]):
        for x in range(blocks.shape[1]):
            if not blocks[y, x] or seen[y, x]:
                continue
            component, queue = [], deque([(y, x)])
            seen[y, x] = True
            while queue:
                cy, cx = queue.popleft()
                component.append((cy, cx))
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < blocks.shape[0] and 0 <= nx < blocks.shape[1] and blocks[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            if len(component) > len(best):
                best = component
    if len(best) < 40:  # pequeno demais para ser o botão
        return None
    ys = [c[0] for c in best]
    xs = [c[1] for c in best]
    width, height = (max(xs) - min(xs) + 1) * block, (max(ys) - min(ys) + 1) * block
    if width < height * 1.5:  # o botão é largo
        return None
    cx = (min(xs) + max(xs) + 1) * block // 2
    cy = (min(ys) + max(ys) + 1) * block // 2 + zone_top
    return cx, cy


def _riot_window():
    from pywinauto import Desktop

    from jarvis.actions.media import _process_name

    for w in Desktop(backend="uia").windows():
        if _process_name(w.element_info.process_id).lower() == "riot client.exe":
            return w
    return None


def _process_running(name: str) -> bool:
    import subprocess

    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"], capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return name.lower() in out.lower()


def press_play(product: str, timeout: float = 40) -> str:
    """Depois de lançar um jogo da Riot: se o jogo não arrancar sozinho, põe o Riot Client à frente,
    encontra o "Play" e clica. Confirma pelo processo do jogo."""
    import mss

    game_exe = GAME_PROCESSES.get(product)
    if game_exe and _process_running(game_exe):
        return "O jogo já está aberto."
    end = time.monotonic() + timeout
    clicked = False
    while time.monotonic() < end:
        if game_exe and _process_running(game_exe):
            return "Carreguei no Play e o jogo arrancou." if clicked else "O jogo arrancou."
        window = _riot_window()
        if window is not None and not clicked:
            try:
                if window.is_minimized():
                    window.restore()
                window.set_focus()
                time.sleep(1.5)  # a página do jogo acaba de carregar
                rect = window.rectangle()
                with mss.MSS() if hasattr(mss, "MSS") else mss.mss() as sct:
                    shot = sct.grab({"left": rect.left, "top": rect.top,
                                     "width": rect.width(), "height": rect.height()})
                rgb = np.array(shot)[:, :, :3][:, :, ::-1]
                spot = find_play_button(rgb)
                if spot:
                    window.click_input(coords=spot)
                    clicked = True
            except Exception:
                pass
        time.sleep(2)
    if not clicked:
        return "Abri o Riot Client, mas não encontrei o botão Play para carregar."
    return "Carreguei no Play, mas o jogo ainda não arrancou (pode estar a atualizar)."
