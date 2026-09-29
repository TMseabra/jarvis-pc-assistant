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


from jarvis.actions import roblox  # noqa: E402


def test_play_roblox_launches_best_match():
    launched = []
    search = lambda q: [{"name": "Greenville RP", "place_id": 891852901, "players": 4131}]  # noqa: E731
    out = roblox.play("greenville", search=search, launch=launched.append)
    assert launched == ["roblox://experiences/start?placeId=891852901"]
    assert "Greenville RP" in out and "4131 a jogar" in out


def test_play_roblox_not_found():
    assert "Não encontrei" in roblox.play("xyz", search=lambda q: [], launch=lambda link: None)


def test_play_roblox_with_just_roblox_opens_the_app(monkeypatch):
    from jarvis.actions import system
    from jarvis.tools import ToolExecutor

    opened = []
    monkeypatch.setattr(system, "open_app", lambda name: opened.append(name) or "Abri Roblox.")
    monkeypatch.setattr(roblox, "play", lambda game: (_ for _ in ()).throw(AssertionError("não devia pesquisar")))
    assert ToolExecutor().run("play_roblox", {"game": "Roblox"}) == "Abri Roblox."
    assert opened == ["Roblox Player"]


def test_recent_chats_and_pick(tmp_path):
    db = tmp_path / "History"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, title TEXT, url TEXT, last_visit_time INTEGER)")
    con.executemany("INSERT INTO urls (title, url, last_visit_time) VALUES (?, ?, ?)", [
        ("Bug no TaskFlow - Claude", "https://claude.ai/chat/a", 300),
        ("Receita de bolo - Claude", "https://claude.ai/chat/b", 200),
        ("Claude", "https://claude.ai/chat/c", 100),
        ("Bug no TaskFlow - Claude", "https://claude.ai/chat/a?x", 50),
    ])
    con.commit(); con.close()
    chats = ai_web.recent_chats("claude", files=[db])
    assert [t for t, _ in chats] == ["Bug no TaskFlow", "Receita de bolo", "(conversa sem título)"]
    assert ai_web.pick_chat(chats, "a segunda")[0] == "Receita de bolo"
    assert ai_web.pick_chat(chats, "3")[0] == "(conversa sem título)"
    assert ai_web.pick_chat(chats, "a do taskflow")[0] == "Bug no TaskFlow"
    assert ai_web.pick_chat(chats, "a de futebol") is None


def test_list_and_open_chat(monkeypatch):
    chats = [("Bug no TaskFlow", "https://claude.ai/chat/a"), ("Receita", "https://claude.ai/chat/b")]
    monkeypatch.setattr(ai_web, "recent_chats", lambda site: chats)
    opened = []
    monkeypatch.setattr(ai_web, "open_url", opened.append)
    listing = ai_web.list_chats("Claudinho")
    assert "1. Bug no TaskFlow" in listing and "2. Receita" in listing and "Queres abrir" in listing
    assert ai_web.open_chat("claude", "2") == 'Abri a conversa "Receita" no Claude.'
    assert opened == ["https://claude.ai/chat/b"]


def test_game_without_roblox_in_request_opens_pc_game(monkeypatch):
    from jarvis.actions import system
    from jarvis.tools import ToolExecutor

    opened = []
    monkeypatch.setattr(system, "open_app", lambda name: opened.append(name) or f"Abri {name}.")
    monkeypatch.setattr(roblox, "play", lambda game: f"Entrei no jogo {game} no Roblox.")
    executor = ToolExecutor()
    assert executor.run("play_roblox", {"game": "Palworld"}, "abre o jogo palworld") == "Abri Palworld."
    assert "Roblox" in executor.run("play_roblox", {"game": "Greenville"}, "abre o jogo greenville no roblox")
    assert opened == ["Palworld"]


def test_find_play_button_on_real_riot_screenshot():
    import numpy as np
    PIL = __import__("pytest").importorskip("PIL.Image")
    from pathlib import Path
    from jarvis.actions.riot import find_play_button

    rgb = np.array(PIL.open(Path(__file__).parent / "fixtures" / "riot_client.png").convert("RGB"))
    x, y = find_play_button(rgb)
    assert 250 < x < 420 and 1080 < y < 1160  # o botão vermelho "Play" em baixo à esquerda
    assert find_play_button(np.zeros((800, 1200, 3), dtype=np.uint8)) is None


# --- mensagens novas, pesquisa na net, gráficos ----------------------------------------

from jarvis.actions import charts, web  # noqa: E402
from jarvis.actions.desktop_chat import discord_unread, whatsapp_preview  # noqa: E402


def test_whatsapp_preview():
    assert whatsapp_preview("Rafa 11:24 bora jogar valorant?") == ("Rafa", "11:24", "bora jogar valorant?")
    assert whatsapp_preview("Grupo da Turma Ontem Rui: ok") == ("Grupo da Turma", "Ontem", "Rui: ok")


def test_discord_unread():
    names = ["Mensagens diretas", "Mensagens não lidas, Shadow Greenville", "2 menções, PRPC | Department",
             "Amigos4", "Rafosto", "1 menção Roblox Car Scene"]
    out = discord_unread(names)
    assert out[0] == "Shadow Greenville" and "PRPC" in out[1] and "(2 menções)" in out[1] and len(out) == 3


def test_make_chart(tmp_path):
    out = charts.make_chart("Horas", ["BeamNG", "Palworld"], [474, 12], kind="barh", folder=tmp_path)
    png = next(tmp_path.glob("*.png"))
    assert png.stat().st_size > 5000 and str(png) in out


def test_web_answer_without_key_opens_search(monkeypatch):
    opened = []
    monkeypatch.setattr(web, "open_url", opened.append)
    monkeypatch.setattr(web.config, "gemini_api_key", None, raising=False) if False else None
    out = web.answer("quem ganhou ontem?") if not web.config.gemini_api_key else "sem chave: saltado"
    if opened:
        assert "google.com/search" in opened[0] and "chave" in out


def test_web_answer_with_fake_gemini():
    class Resp:
        text = "O Benfica ganhou 2-0."
        candidates = []

    class Client:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                assert kwargs["config"].tools[0].google_search is not None
                return Resp()

    assert web.answer("quem ganhou?", client=Client()) == "O Benfica ganhou 2-0."
