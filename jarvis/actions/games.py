"""Jogos instalados (Steam, Epic, Riot, Battle.net) e como os lançar diretamente.

"Abre o Valorant" deve abrir o jogo, não só o launcher: cada loja tem a sua forma de
lançar um jogo (URI steam://, argumentos do Riot Client, --exec do Battle.net...).
"""

import json
import os
import re
import subprocess
import sys
import unicodedata
import winreg
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Game:
    name: str
    source: str  # "Steam", "Epic", "Riot", "Battle.net"
    uri: str | None = None  # aberto com os.startfile
    command: tuple[str, ...] = ()  # ou executado diretamente
    aliases: tuple[str, ...] = field(default=())


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if ch.isalnum())


# --- Steam -----------------------------------------------------------------

_STEAM_SKIP = re.compile(r"redistributable|steamworks|proton|soundtrack|dedicated server|\bsdk\b", re.I)


def _steam_root() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        default = Path(r"C:\Program Files (x86)\Steam")
        return default if default.exists() else None


def steam_games(root: Path | None = None) -> list[Game]:
    root = root or _steam_root()
    if not root:
        return []
    libraries = {root}
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        for path in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
            libraries.add(Path(path.replace("\\\\", "\\")))
    games = []
    for lib in libraries:
        for manifest in (lib / "steamapps").glob("appmanifest_*.acf"):
            text = manifest.read_text(encoding="utf-8", errors="replace")
            name = re.search(r'"name"\s+"([^"]+)"', text)
            appid = re.search(r'"appid"\s+"(\d+)"', text)
            if name and appid and not _STEAM_SKIP.search(name.group(1)):
                games.append(Game(name.group(1), "Steam", uri=f"steam://rungameid/{appid.group(1)}"))
    return games


# --- Epic ------------------------------------------------------------------

def epic_games(manifests: Path = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")) -> list[Game]:
    games = []
    for item in manifests.glob("*.item") if manifests.exists() else []:
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            continue
        name, app = data.get("DisplayName"), data.get("AppName")
        if not name or not app or "Conteúdo" in name or data.get("bIsIncompleteInstall"):
            continue
        games.append(Game(
            name, "Epic", uri=f"com.epicgames.launcher://apps/{app}?action=launch&silent=true"
        ))
    return games


# --- Riot ------------------------------------------------------------------

# pasta em ProgramData\Riot Games\Metadata -> (nome, produto para --launch-product, aliases)
_RIOT_PRODUCTS = {
    "valorant.live": ("VALORANT", "valorant", ("valo",)),
    "league_of_legends.live": ("League of Legends", "league_of_legends", ("lol", "league")),
    "bacon.live": ("Legends of Runeterra", "bacon", ("runeterra", "lor")),
    "lion.live": ("2XKO", "lion", ()),
}


def riot_games(programdata: Path = Path(r"C:\ProgramData\Riot Games")) -> list[Game]:
    installs = programdata / "RiotClientInstalls.json"
    try:
        client = json.loads(installs.read_text(encoding="utf-8"))["rc_default"]
    except (OSError, ValueError, KeyError):
        return []
    games = []
    for folder, (name, product, aliases) in _RIOT_PRODUCTS.items():
        if (programdata / "Metadata" / folder).exists():
            games.append(Game(
                name, "Riot",
                command=(client, f"--launch-product={product}", "--launch-patchline=live"),
                aliases=aliases,
            ))
    return games


# --- Battle.net ------------------------------------------------------------

# Nome no "Adicionar/remover programas" -> (código do produto para --exec="launch X", aliases)
_BATTLENET_PRODUCTS = {
    "Overwatch": ("Pro", ("ow", "overwatch 2")),
    "Diablo IV": ("Fen", ("diablo 4",)),
    "Diablo III": ("D3", ("diablo 3",)),
    "World of Warcraft": ("WoW", ("wow",)),
    "Hearthstone": ("WTCG", ()),
    "StarCraft II": ("S2", ("starcraft 2",)),
    "Heroes of the Storm": ("Hero", ()),
}


def _installed_programs() -> set[str]:
    names = set()
    for hive, path in (
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ):
        try:
            with winreg.OpenKey(hive, path) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, i)) as sub:
                            names.add(winreg.QueryValueEx(sub, "DisplayName")[0])
                    except OSError:
                        continue
        except OSError:
            continue
    return names


def battlenet_games(installed: set[str] | None = None) -> list[Game]:
    exe = next(
        (p for p in (Path(r"C:\Program Files (x86)\Battle.net\Battle.net.exe"),
                     Path(r"C:\Program Files\Battle.net\Battle.net.exe")) if p.exists()),
        None,
    )
    if not exe:
        return []
    installed = _installed_programs() if installed is None else installed
    return [
        Game(name, "Battle.net", command=(str(exe), f"--exec=launch {code}"), aliases=aliases)
        for name, (code, aliases) in _BATTLENET_PRODUCTS.items()
        if name in installed
    ]


# --- procura e lançamento --------------------------------------------------

_cache: list[Game] | None = None


def list_games() -> list[Game]:
    global _cache
    if _cache is None:
        _cache = []
        if sys.platform == "win32":
            # Riot e Battle.net primeiro: o VALORANT também aparece na Epic, mas o Riot é o direto.
            for source in (riot_games, battlenet_games, steam_games, epic_games):
                try:
                    _cache.extend(source())
                except OSError:
                    continue
    return _cache


def find_game(name: str, games: list[Game] | None = None) -> Game | None:
    """Exato (nome ou alias) > começa por > contém. Nomes com menos de 3 letras só por exato."""
    games = list_games() if games is None else games
    target = _fold(name)
    if not target:
        return None
    for game in games:
        if target == _fold(game.name) or target in {_fold(a) for a in game.aliases}:
            return game
    if len(target) < 3:
        return None
    for rank in (lambda f: f.startswith(target), lambda f: target in f):
        matches = [g for g in games if rank(_fold(g.name))]
        if matches:
            return min(matches, key=lambda g: len(g.name))
    return None


def launch(game: Game):
    if game.uri:
        os.startfile(game.uri)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(game.command, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
