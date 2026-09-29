import json
import sqlite3

from jarvis.actions import ai_web, steam

LOCALCONFIG = """
"UserLocalConfigStore"
{
    "Software" { "Valve" { "Steam" { "apps" {
        "284160" { "LastPlayed" "1700000000" "Playtime" "28440" }
        "960090" { "Playtime" "600" }
        "730"    { "LastPlayed" "1" }
        "1623730" { "Playtime" "90" }
    } } } }
}
"""


def _steam(tmp_path, favorites=("284160", "1623730")):
    user = tmp_path / "userdata" / "123" / "config"
    (user / "cloudstorage").mkdir(parents=True)
    (user / "localconfig.vdf").write_text(LOCALCONFIG, encoding="utf-8")
    fav = {"id": "favorite", "name": "", "added": [int(a) for a in favorites], "removed": []}
    (user / "cloudstorage" / "cloud-storage-namespace-1.json").write_text(
        json.dumps([["user-collections.favorite", {"key": "user-collections.favorite", "value": json.dumps(fav)}]]),
        encoding="utf-8")
    return tmp_path


def test_parse_vdf_and_playtimes(tmp_path):
    root = _steam(tmp_path)
    user = steam.user_dirs(root)[0]
    assert steam.playtimes(user) == {"284160": 28440, "960090": 600, "1623730": 90}
    assert steam.favorites(user) == {"284160", "1623730"}


def test_steam_stats(tmp_path, monkeypatch):
    root = _steam(tmp_path)
    monkeypatch.setattr(steam, "NAMES_CACHE", tmp_path / "nomes.json")
    names = {"284160": "BeamNG.drive", "960090": "Bloons TD 6", "1623730": "Palworld"}
    fetch = lambda ids: {i: names[i] for i in ids if i in names}  # noqa: E731
    all_games = steam.steam_stats("all", root=root, fetch=fetch)
    assert "BeamNG.drive, com 474 h" in all_games and "3 jogos" in all_games
    favs = steam.steam_stats("favorites", root=root, fetch=fetch)
    assert "favoritos (2 jogos)" in favs and "Bloons" not in favs and "476 h" in favs


def test_last_chat_url(tmp_path):
    db = tmp_path / "History"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, last_visit_time INTEGER)")
    con.executemany("INSERT INTO urls (url, last_visit_time) VALUES (?, ?)", [
        ("https://claude.ai/chat/antiga", 100), ("https://claude.ai/chat/recente?x=1", 300),
        ("https://claude.ai/new", 400), ("https://chatgpt.com/c/gpt1", 200),
    ])
    con.commit(); con.close()
    assert ai_web.last_chat_url("claude", [db]) == "https://claude.ai/chat/recente"
    assert ai_web.last_chat_url("chatgpt", [db]) == "https://chatgpt.com/c/gpt1"


def test_continue_last_chat(monkeypatch):
    opened, typed = [], []
    monkeypatch.setattr(ai_web, "last_chat_url", lambda site: "https://claude.ai/chat/x")
    monkeypatch.setattr(ai_web, "open_url", opened.append)
    monkeypatch.setattr(ai_web, "_type_when_focused", lambda title, text: typed.append(text) or True)
    assert "pedi" in ai_web.continue_last_chat("Claudinho")
    assert opened == ["https://claude.ai/chat/x"] and typed == ["Continua de onde ficámos."]
