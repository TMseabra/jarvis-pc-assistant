"""Ações no sistema operativo: abrir aplicações, sites e pesquisas."""

import json
import os
import shutil
import subprocess
import sys
import unicodedata
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from jarvis.config import config

if sys.platform == "win32":
    from jarvis.actions import games, windows
else:  # pragma: no cover - o Jarvis é feito para Windows
    games = None


def _normalize(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _start_menu_dirs() -> list[Path]:
    dirs = []
    for env in ("PROGRAMDATA", "APPDATA"):
        base = os.environ.get(env)
        if base:
            dirs.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return dirs


def find_windows_shortcut(name: str, search_dirs: list[Path] | None = None) -> Path | None:
    """Procura um atalho (.lnk) no Menu Iniciar cujo nome corresponda a `name`.

    Prefere correspondência exata; senão, o atalho mais curto que contém o nome.
    """
    target = _normalize(name)
    if not target:
        return None
    candidates: list[Path] = []
    for directory in search_dirs if search_dirs is not None else _start_menu_dirs():
        if not directory.is_dir():
            continue
        for lnk in directory.rglob("*.lnk"):
            stem = _normalize(lnk.stem)
            if stem == target:
                return lnk
            if target in stem and "uninstall" not in stem and "desinstalar" not in stem:
                candidates.append(lnk)
    if not candidates:
        return None
    return min(candidates, key=lambda p: len(p.stem))


def _fold(text: str) -> str:
    """Minúsculas, sem acentos nem pontuação: 'Bloco de Notas' -> 'blocodenotas'."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if ch.isalnum())


_start_apps_cache: list[tuple[str, str]] | None = None


def list_start_apps() -> list[tuple[str, str]]:
    """(nome, AppID) de todas as apps do Menu Iniciar, incluindo as da Microsoft Store e com os
    nomes na língua do Windows ('Calculadora', 'Bloco de notas'). Em cache depois da 1.ª vez."""
    global _start_apps_cache
    if _start_apps_cache is None:
        _start_apps_cache = []
        if sys.platform == "win32":
            script = (
                "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
            )
            try:
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", script],
                    capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                ).stdout.decode("utf-8", errors="replace")
                data = json.loads(out) if out.strip() else []
                data = [data] if isinstance(data, dict) else data
                _start_apps_cache = [(d["Name"], d["AppID"]) for d in data if d.get("Name") and d.get("AppID")]
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
    return _start_apps_cache


# Como as pessoas dizem -> nome no Menu Iniciar.
_APP_ALIASES = {
    "vscode": "Visual Studio Code",
    "vs": "Visual Studio Code",
    "code": "Visual Studio Code",
    "visualstudio": "Visual Studio Code",
    "explorador": "Explorador de Ficheiros",
    "ficheiros": "Explorador de Ficheiros",
    "cmd": "Linha de Comandos",
    "loja": "Microsoft Store",
    "definicoes": "Definições",
    "whatsappweb": "WhatsApp",
    "wpp": "WhatsApp",
    "roblox": "Roblox Player",
    "claudeapp": "Claude",
    "claudeinstalado": "Claude",
    "appdoclaude": "Claude",
    "zap": "WhatsApp",
    "configuracoes": "Definições",
}


def find_start_app(name: str, apps: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Exato > começa por > contém (o mais curto). Ignora desinstaladores."""
    alias = _APP_ALIASES.get(_fold(name))
    if alias and any(_fold(n) == _fold(alias) for n, _ in apps):
        name = alias
    target = _fold(name)
    if not target:
        return None
    usable = [(n, a) for n, a in apps if "uninstall" not in _fold(n) and "desinstal" not in _fold(n)]
    ranks = [lambda f: f == target]
    if len(target) >= 3:  # "a" ou "tv" apanhariam quase tudo
        ranks += [lambda f: f.startswith(target), lambda f: target in f]
    for rank in ranks:
        matches = [(n, a) for n, a in usable if rank(_fold(n))]
        if matches:
            return min(matches, key=lambda m: len(m[0]))
    return None


def validate_app_name(name: str) -> str:
    """Só aceita nomes de aplicações, não caminhos nem comandos."""
    name = name.strip()
    if not name or any(ch in name for ch in '/\\&|;<>"`$%^'):
        raise ValueError(f"Nome de aplicação inválido: '{name}'.")
    return name


# "Apps" que são sites: abrem no browser escolhido.
_WEB_APPS = {
    "claudinho": ("Claude", "https://claude.ai/new"),
    "claudeweb": ("Claude", "https://claude.ai/new"),
    "claudenoopera": ("Claude", "https://claude.ai/new"),
    "claudenobrowser": ("Claude", "https://claude.ai/new"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/"),
}


def open_app(name: str) -> str:
    """Abre uma aplicação do PC pelo nome."""
    name = validate_app_name(name)
    web = _WEB_APPS.get(_fold(name))
    if web:
        open_url(web[1])
        return f"Abri o {web[0]} no browser."
    if sys.platform == "win32":
        # Jogos primeiro: "abre o Valorant" deve abrir o jogo e não só o launcher.
        game = games.find_game(name)
        if game:
            try:
                games.launch(game)
            except OSError as exc:
                return f"Não consegui abrir {game.name}: {exc}"
            if game.source == "Riot":
                # O Riot Client abre na página do jogo mas nem sempre carrega no Play sozinho.
                from jarvis.actions import riot

                product = next((a.split("=", 1)[1] for a in game.command if a.startswith("--launch-product=")), "")
                played = riot.press_play(product)
                windows.focus_later(game.name, game=True)
                return f"Abri {game.name}. {played}"
            windows.focus_later(game.name, game=True)
            return f"Abri {game.name} ({game.source})."

        # Depois: atalho .lnk com o nome exato (mantém argumentos que o Menu Iniciar às vezes
        # perde), apps do Menu Iniciar (inclui Store), outros atalhos, executáveis no PATH
        # ("calc", "notepad") e URIs ("ms-settings:"). Nunca passa pela shell.
        shortcut = find_windows_shortcut(name)
        if shortcut and _normalize(shortcut.stem) != _normalize(name):
            shortcut = None
        app = None if shortcut else find_start_app(name, list_start_apps())
        shortcut = shortcut or (None if app else find_windows_shortcut(name))
        if app:
            target, label = f"shell:AppsFolder\\{app[1]}", app[0]
        elif shortcut:
            target, label = str(shortcut), shortcut.stem
        elif shutil.which(name) or name.endswith(":"):
            target, label = name, name
        else:
            # Não chamamos o os.startfile às cegas: mostraria uma janela de erro do Windows.
            return f"Não encontrei nenhuma aplicação chamada '{name}'."
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except OSError:
            return f"Não consegui abrir '{label}'."
        windows.focus_later(label)
        return f"Abri {label}."

    if sys.platform == "darwin":
        result = subprocess.run(["open", "-a", name], capture_output=True)
        if result.returncode == 0:
            return f"Abri {name}."
        return f"Não encontrei nenhuma aplicação chamada '{name}'."

    exe = shutil.which(name) or shutil.which(name.lower())
    if exe:
        subprocess.Popen([exe], start_new_session=True)
        return f"Abri {name}."
    return f"Não encontrei nenhuma aplicação chamada '{name}'."


def normalize_url(url: str) -> str:
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Só posso abrir sites http/https: '{url}'.")
    return url


def _browser_paths() -> dict[str, list[Path]]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    pf86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    return {
        "opera": [local / "Programs" / "Opera" / "opera.exe"],
        "opera gx": [local / "Programs" / "Opera GX" / "opera.exe"],
        "chrome": [pf / "Google/Chrome/Application/chrome.exe", pf86 / "Google/Chrome/Application/chrome.exe",
                   local / "Google/Chrome/Application/chrome.exe"],
        "brave": [pf / "BraveSoftware/Brave-Browser/Application/brave.exe",
                  local / "BraveSoftware/Brave-Browser/Application/brave.exe"],
        "firefox": [pf / "Mozilla Firefox/firefox.exe", pf86 / "Mozilla Firefox/firefox.exe"],
        "edge": [pf86 / "Microsoft/Edge/Application/msedge.exe", pf / "Microsoft/Edge/Application/msedge.exe"],
    }


def browser_executable(choice: str) -> Path | None:
    """JARVIS_BROWSER: "opera", "chrome", ... ou um caminho. Vazio/"default" = browser do Windows."""
    choice = (choice or "").strip()
    if not choice or choice.lower() == "default":
        return None
    as_path = Path(choice)
    if as_path.suffix.lower() == ".exe" and as_path.exists():
        return as_path
    return next((p for p in _browser_paths().get(choice.lower(), []) if p.exists()), None)


def open_url(url: str):
    exe = browser_executable(config.browser)
    if exe:
        subprocess.Popen([str(exe), url])
    else:
        webbrowser.open(url)


def open_website(url: str) -> str:
    """Abre um site no browser escolhido (JARVIS_BROWSER) ou no predefinido."""
    url = normalize_url(url)
    open_url(url)
    return f"Abri {url}."


def search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def web_search(query: str) -> str:
    """Pesquisa na web no browser escolhido."""
    open_url(search_url(query))
    return f"Pesquisei por '{query}'."


def close_app(name: str) -> str:
    """Fecha as janelas de uma aplicação (como carregar no X), pelo nome da janela ou do programa."""
    import win32con
    import win32gui
    import win32process

    target = _fold(_APP_ALIASES.get(_fold(name), name))
    if len(target) < 3:
        return f"Não percebi que aplicação fechar: '{name}'."
    closed = set()

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = _process_exe(pid)
        if title and (target in _fold(title) or target in _fold(exe)) and "jarvis" not in _fold(title):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed.add(title)

    win32gui.EnumWindows(visit, None)
    if not closed:
        return f"Não encontrei nenhuma janela aberta de '{name}'."
    return f"Fechei {', '.join(sorted(closed))[:120]}."


def lock_pc() -> str:
    """Bloqueia o PC (como Win+L)."""
    import ctypes

    if not ctypes.windll.user32.LockWorkStation():
        return "Não consegui bloquear o PC."
    return "Bloqueei o PC."


_POWER = {
    "shutdown": (["shutdown", "/s", "/t", "15"], "O PC vai desligar-se daqui a 15 segundos."),
    "restart": (["shutdown", "/r", "/t", "15"], "O PC vai reiniciar daqui a 15 segundos."),
    "cancel": (["shutdown", "/a"], "Cancelei: o PC já não se vai desligar."),
}


def power(action: str) -> str:
    """Desligar / reiniciar (com 15 s para cancelar), suspender, ou cancelar."""
    if action == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "A pôr o PC em suspensão."
    if action not in _POWER:
        raise ValueError(f"Ação desconhecida: {action}")
    command, message = _POWER[action]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        if action == "cancel":
            return "Não havia nenhum desligar marcado."
        return f"Não consegui: {(result.stderr or result.stdout).strip()}"
    return message + (" Diz \"cancela o desligar\" se mudares de ideias." if action != "cancel" else "")


def _process_exe(pid: int) -> str:
    import win32api
    import win32con
    import win32process

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            return Path(win32process.GetModuleFileNameEx(handle, 0)).stem
        finally:
            win32api.CloseHandle(handle)
    except Exception:
        return ""
