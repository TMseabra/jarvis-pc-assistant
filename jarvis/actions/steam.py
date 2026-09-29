"""Estatísticas da Steam a partir dos ficheiros locais (sem login nem API key).

- Horas por jogo: userdata/<conta>/config/localconfig.vdf ("Playtime", em minutos).
- Favoritos: userdata/<conta>/config/cloudstorage/cloud-storage-namespace-1.json
  (coleção "user-collections.favorite").
- Nomes: jogos instalados (appmanifest) e, para os restantes, a loja da Steam (guardados em
  .jarvis/steam_nomes.json para não voltar a perguntar).
"""

import json
import re
from pathlib import Path

from jarvis.config import PROJECT_ROOT

NAMES_CACHE = PROJECT_ROOT / ".jarvis" / "steam_nomes.json"
# Apps sem página na loja.
KNOWN_NAMES = {"480": "Spacewar"}


def parse_vdf(text: str) -> dict:
    """Formato de texto KeyValues da Valve -> dict (chaves em minúsculas)."""
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    stack, current, key = [], {}, None
    for quoted, brace in tokens:
        if brace == "{":
            new = {}
            current[(key or "").lower()] = new
            stack.append(current)
            current, key = new, None
        elif brace == "}":
            current = stack.pop() if stack else current
        elif key is None:
            key = quoted
        else:
            current[key.lower()] = quoted
            key = None
    return current


def _root() -> Path | None:
    from jarvis.actions.games import _steam_root

    return _steam_root()


def user_dirs(root: Path | None = None) -> list[Path]:
    root = root or _root()
    base = root / "userdata" if root else None
    return [d for d in base.iterdir() if d.is_dir() and d.name.isdigit()] if base and base.exists() else []


def playtimes(user: Path) -> dict[str, int]:
    """appid -> minutos jogados."""
    config = user / "config" / "localconfig.vdf"
    if not config.exists():
        return {}
    data = parse_vdf(config.read_text(encoding="utf-8", errors="replace"))
    apps = (data.get("userlocalconfigstore", data).get("software", {}).get("valve", {})
            .get("steam", {}).get("apps", {}))
    out = {}
    for appid, info in apps.items():
        value = str(info.get("playtime", "")) if isinstance(info, dict) else ""
        if value.isdigit() and int(value) > 0:
            out[appid] = int(value)
    return out


def favorites(user: Path) -> set[str]:
    path = user / "config" / "cloudstorage" / "cloud-storage-namespace-1.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    for key, value in entries:
        if key == "user-collections.favorite" and value.get("value"):
            return {str(a) for a in json.loads(value["value"]).get("added", [])}
    return set()


def _installed_names(root: Path | None) -> dict[str, str]:
    from jarvis.actions.games import steam_games

    return {g.uri.rsplit("/", 1)[-1]: g.name for g in steam_games(root) if g.uri}


def game_names(appids: list[str], root: Path | None = None, fetch=None) -> dict[str, str]:
    """Nomes para os appids: instalados, cache e (só para os que faltam) a loja da Steam."""
    names = {**KNOWN_NAMES, **_installed_names(root)}
    try:
        names.update(json.loads(NAMES_CACHE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    missing = [a for a in appids if a not in names]
    if missing:
        fetch = fetch or _fetch_store_names
        fetched = fetch(missing)
        if fetched:
            names.update(fetched)
            try:
                NAMES_CACHE.parent.mkdir(parents=True, exist_ok=True)
                cached = json.loads(NAMES_CACHE.read_text(encoding="utf-8")) if NAMES_CACHE.exists() else {}
                cached.update(fetched)
                NAMES_CACHE.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
            except (OSError, ValueError):
                pass
    return names


def _fetch_store_names(appids: list[str]) -> dict[str, str]:
    import httpx

    out = {}
    with httpx.Client(timeout=8) as http:
        for appid in appids[:40]:
            try:
                data = http.get("https://store.steampowered.com/api/appdetails",
                                params={"appids": appid, "filters": "basic", "l": "portuguese"}).json()
                info = data.get(appid, {})
                if info.get("success"):
                    out[appid] = info["data"]["name"]
            except (httpx.HTTPError, ValueError, KeyError):
                continue
    return out


def _hours(minutes: int) -> str:
    hours = minutes / 60
    return f"{hours:.0f} h" if hours >= 10 else f"{hours:.1f} h".replace(".", ",")


def steam_stats(scope: str = "all", top: int = 5, root: Path | None = None, fetch=None) -> str:
    """Resumo das horas jogadas: o jogo com mais horas, o total e o top (todos ou só os favoritos)."""
    users = user_dirs(root)
    if not users:
        return "Não encontrei a pasta de utilizador da Steam neste PC."
    # Várias contas no PC: a que tem mais horas registadas.
    user = max(users, key=lambda u: sum(playtimes(u).values()))
    times = playtimes(user)
    label = "na tua biblioteca"
    if scope == "favorites":
        favs = favorites(user)
        if not favs:
            return "Não encontrei a tua coleção de favoritos na Steam."
        times = {a: m for a, m in times.items() if a in favs}
        label = f"nos teus favoritos ({len(favs)} jogos)"
    if not times:
        return f"Não encontrei horas jogadas {label}."
    ranking = sorted(times.items(), key=lambda kv: kv[1], reverse=True)
    names = game_names([a for a, _ in ranking[:max(top, 1)]], root, fetch)
    name = lambda appid: names.get(appid, f"jogo {appid}")  # noqa: E731
    best_id, best_min = ranking[0]
    total = sum(times.values())
    lines = [
        f"O jogo com mais horas {label} é {name(best_id)}, com {_hours(best_min)}.",
        f"No total são {_hours(total)} em {len(times)} jogos.",
        "Top: " + "; ".join(f"{name(a)} {_hours(m)}" for a, m in ranking[:top]) + ".",
    ]
    return " ".join(lines)


def top_games(scope: str = "all", top: int = 10, root: Path | None = None, fetch=None) -> list[tuple[str, float]]:
    """[(nome, horas)] dos jogos com mais horas (para gráficos)."""
    users = user_dirs(root)
    if not users:
        return []
    user = max(users, key=lambda u: sum(playtimes(u).values()))
    times = playtimes(user)
    if scope == "favorites":
        favs = favorites(user)
        times = {a: m for a, m in times.items() if a in favs}
    ranking = sorted(times.items(), key=lambda kv: kv[1], reverse=True)[:top]
    names = game_names([a for a, _ in ranking], root, fetch)
    return [(names.get(a, f"jogo {a}"), m / 60) for a, m in ranking]
