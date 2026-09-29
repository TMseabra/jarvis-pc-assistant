import pytest

from jarvis import contacts
from jarvis.actions import media, spotify_api, system
from jarvis.actions.messaging import pick_result
from jarvis.commands import split_commands

CONTACTS = [("Rafosto", ["rafa", "rafael"]), ("Rafael Pedro", ["pedro"])]


@pytest.mark.parametrize("spoken, expected", [
    ("rafa", "Rafosto"),
    ("Rafael", "Rafosto"),
    ("pedro", "Rafael Pedro"),
    ("Rafosta", "Rafosto"),       # o Whisper ouviu mal: o mais parecido
    ("Ana", "Ana"),                # desconhecido: fica como foi dito
])
def test_contacts_resolve(spoken, expected):
    assert contacts.resolve(spoken, CONTACTS) == expected


def test_contacts_file(tmp_path):
    f = tmp_path / "contactos.txt"
    assert contacts.load(f) == [] and f.exists()  # cria o modelo
    f.write_text("# comentário\nRafosto = rafa, rafostinho\n\nAna Silva\n", encoding="utf-8")
    assert contacts.load(f) == [("Rafosto", ["rafa", "rafostinho"]), ("Ana Silva", [])]


def test_pick_result_fuzzy_only_when_asked():
    titles = ["Amigos", "Rafosto", "ander"]
    assert pick_result(titles, "Rafosta") is None
    assert pick_result(titles, "Rafosta", fuzzy=True) == 1
    assert pick_result(titles, "Zé", fuzzy=True) is None


def test_first_youtube_video_skips_to_video_renderer():
    html = ('{"adSlotRenderer":{}},{"videoRenderer":{"videoId":"a0TRyQM8bmg","thumbnail":{},'
            '"title":{"runs":[{"text":"V\\u00eddeo de Roblox \\u0026 amigos"}]}}}')
    assert media.first_youtube_video(html) == ("a0TRyQM8bmg", "Vídeo de Roblox & amigos")
    assert media.first_youtube_video("<html>nada</html>") is None


@pytest.mark.parametrize("title, playing", [
    ("Spotify Premium", False), ("Spotify", False), ("Spotify Free", False),
    ("Queen - Bohemian Rhapsody", True), (None, False),
])
def test_spotify_is_playing(title, playing):
    assert media.is_playing(title) is playing


@pytest.mark.parametrize("query, expected", [
    ("Bohemian Rhapsody", ("track", "Bohemian Rhapsody")),
    ("playlist de treino", ("playlist", "treino")),
    ("músicas do Plutónio", ("artist", "Plutónio")),
    ("o álbum da Adele 25", ("album", "Adele 25")),
])
def test_spotify_search_type(query, expected):
    assert spotify_api.choose_search_type(query) == expected


def test_app_aliases_and_claudinho(monkeypatch):
    apps = [("Visual Studio Code", "Microsoft.VisualStudioCode"), ("Spotify", "x")]
    assert system.find_start_app("VS Code", apps)[0] == "Visual Studio Code"
    opened = []
    monkeypatch.setattr(system, "open_url", opened.append)
    assert system.open_app("Claudinho") == "Abri o Claude no browser."
    assert opened == ["https://claude.ai/new"]


@pytest.mark.parametrize("text, expected", [
    ("abre o Spotify e põe a minha música", ["abre o Spotify", "põe a minha música"]),
    ("abre o youtube e mete um vídeo de Roblox", ["abre o youtube", "mete um vídeo de Roblox"]),
    (
        "abre o TaskFlow no VS Code e diz ao Claudinho para continuar",
        ["abre o TaskFlow no VS Code e diz ao Claudinho para continuar"],
    ),
])
def test_split_music_and_claudinho(text, expected):
    assert split_commands(text) == expected


# --- ficheiros, definições, IA na web ------------------------------------------

from jarvis.actions import ai_web, files  # noqa: E402


def test_find_path(tmp_path):
    (tmp_path / "Trabalhos" / "Escola").mkdir(parents=True)
    (tmp_path / "Trabalhos" / "Escola" / "CV.pdf").touch()
    (tmp_path / "Trabalhos" / "cv antigo.docx").touch()
    (tmp_path / "Fotos da Praia 2025").mkdir()
    assert files.find_path("cv", [tmp_path]).name == "CV.pdf"          # 2 letras: só exato
    assert files.find_path("fotos da praia", [tmp_path]).name == "Fotos da Praia 2025"
    assert files.find_path("escola", [tmp_path]).name == "Escola"
    assert files.find_path("xyz", [tmp_path]) is None


def test_open_path_known_folders_and_settings(monkeypatch):
    opened = []
    monkeypatch.setattr(files.os, "startfile", opened.append, raising=False)
    assert files.open_path("transferências") == "Abri a pasta Transferências."
    assert files.open_path("Bluetooth") == "Abri as Definições: Bluetooth."
    assert opened == ["shell:Downloads", "ms-settings:bluetooth"]


def test_ask_ai_sites(monkeypatch):
    opened = []
    monkeypatch.setattr(ai_web, "open_url", opened.append)
    monkeypatch.setattr(ai_web, "_submit_when_focused", lambda title: True)
    assert "ChatGPT" in ai_web.ask_ai("um gato astronauta", "image")
    assert opened[-1].startswith("https://chatgpt.com/?q=Gera%20uma%20imagem%3A%20um%20gato")
    ai_web.ask_ai("script que renomeia fotos", "code")
    assert opened[-1].startswith("https://claude.ai/new?q=script")
    ai_web.ask_ai("um poema", "text", site="Claudinho")
    assert opened[-1].startswith("https://claude.ai/new?q=")


def test_ask_ai_claude_without_focus_says_so(monkeypatch):
    monkeypatch.setattr(ai_web, "open_url", lambda url: None)
    monkeypatch.setattr(ai_web, "_submit_when_focused", lambda title: False)
    assert "carrega em Enter" in ai_web.ask_ai("x", "code")


@pytest.mark.parametrize("text, expected", [
    ("gera uma imagem de um robô a tocar guitarra", ["gera uma imagem de um robô a tocar guitarra"]),
    ("faz-me um logo e abre o Spotify", ["faz-me um logo", "abre o Spotify"]),
    ("abre o Spotify põe música", ["abre o Spotify", "põe música"]),
])
def test_split_does_not_cut_infinitives(text, expected):
    assert split_commands(text) == expected


# --- verificação final -------------------------------------------------------

from jarvis.llm import ToolCall, ToolResult  # noqa: E402
from jarvis.verify import verify  # noqa: E402


def _r(text, error=False):
    return ToolResult(ToolCall("x", {}), text, is_error=error)


def test_verify_all_ok():
    check = verify([_r("Abri Spotify."), _r("A tocar: Queen - Bohemian Rhapsody.")])
    assert check.ok and check.spoken() == "Terminei, correu tudo bem."
    assert check.ui_line() == "Verificado: 2/2 ações correram bem."


def test_verify_detects_failures_even_without_error_flag():
    check = verify([
        _r("Abri Spotify."),
        _r("Carreguei no play, mas o Spotify não começou a tocar."),
        _r("Não encontrei a conversa 'Zé' no Discord.", error=True),
    ])
    assert not check.ok and len(check.failures) == 2
    assert check.spoken() == "Terminei, mas nem tudo correu bem: Carreguei no play, mas o Spotify não começou a tocar e mais 1."
    assert verify([]) is None


# --- continuar o trabalho no GitHub ------------------------------------------

import subprocess  # noqa: E402
import time  # noqa: E402

from jarvis.actions import projects  # noqa: E402


def _repo(path, message):
    path.mkdir()
    run = lambda *a: subprocess.run(["git", *a], cwd=path, capture_output=True, check=True)  # noqa: E731
    run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
    (path / "a.txt").write_text("x"); run("add", "."); run("commit", "-qm", message)
    return path


def test_last_worked_project_and_context(tmp_path):
    old = _repo(tmp_path / "Antigo", "primeiro")
    time.sleep(1.1)
    new = _repo(tmp_path / "Novo", "adiciona login")
    (new / "login.py").write_text("# por acabar")
    assert projects.last_worked_project([old, new, tmp_path / "sem_git"]) == new
    context = projects.work_context(new)
    assert "adiciona login" in context and "login.py" in context


def test_continue_work_passes_context_to_claude(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "TaskFlow", "dashboard")
    calls = []
    monkeypatch.setattr(projects, "last_worked_project", lambda: repo)
    monkeypatch.setattr(projects, "open_project", lambda name, prompt, project=None: calls.append((name, prompt, project)) or "ok")
    projects.continue_work()
    name, prompt, project = calls[0]
    assert project == repo and "Continua o trabalho" in prompt and "dashboard" in prompt


# --- histórico do YouTube ---------------------------------------------------------

def _history_db(path, visits):
    import sqlite3
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
    con.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER, visit_duration INTEGER)")
    for i, (vid, title, minutes_ago, seconds) in enumerate(visits, 1):
        con.execute("INSERT INTO urls VALUES (?, ?, ?)", (i, f"https://www.youtube.com/watch?v={vid}", f"{title} - YouTube"))
        when = int((media._CHROMIUM_EPOCH.__class__.now() - media._CHROMIUM_EPOCH).total_seconds() * 1e6) - minutes_ago * 60_000_000
        con.execute("INSERT INTO visits VALUES (?, ?, ?, ?)", (i, i, when, seconds * 1_000_000))
    con.commit(); con.close()


def test_watched_videos_order_and_filters(tmp_path, monkeypatch):
    db = tmp_path / "History"
    _history_db(db, [
        ("AAAAAAAAAAA", "Vídeo antigo", 120, 300),
        ("BBBBBBBBBBB", "O que eu vi", 10, 600),
        ("CCCCCCCCCCC", "Clique por engano", 5, 2),       # < 10 s: não conta
        ("DDDDDDDDDDD", "Aberto pelo Jarvis", 1, 400),    # aberto pelo Jarvis: não conta
    ])
    monkeypatch.setattr(media, "_opened_by_jarvis", lambda: {"DDDDDDDDDDD"})
    videos = media.watched_videos([db])
    assert [v[1] for v in videos] == ["O que eu vi", "Vídeo antigo"]


def test_open_watched_video(tmp_path, monkeypatch):
    db = tmp_path / "History"
    _history_db(db, [("AAAAAAAAAAA", "Antigo", 60, 100), ("BBBBBBBBBBB", "Recente", 5, 100)])
    monkeypatch.setattr(media, "history_files", lambda: [db])
    monkeypatch.setattr(media, "_opened_by_jarvis", lambda: set())
    monkeypatch.setattr(media, "open_from_history_page", lambda position: None)  # página não lida
    opened = []
    monkeypatch.setattr(media, "open_url", opened.append)
    assert "Recente" in media.open_watched_video(1)
    assert "Antigo" in media.open_watched_video(2)
    assert opened == ["https://www.youtube.com/watch?v=BBBBBBBBBBB", "https://www.youtube.com/watch?v=AAAAAAAAAAA"]


# --- responder à última mensagem -------------------------------------------------

from jarvis.tools import ToolExecutor  # noqa: E402


class FakeRouter:
    def __init__(self):
        self.calls = []

    def reply_latest(self, platform, message, compose=None, confirm=None):
        if not message:
            message = compose("Rafa", "[19:00] Rafa: bora jogar logo?")
        if confirm is not None:
            message = confirm("WhatsApp", "Rafa", message)
            if not message:
                return None
        self.calls.append((platform, message))
        return f"Respondi a Rafa. Texto enviado: \"{message}\""

    def close(self):
        pass


def test_reply_last_message_composes_and_confirms():
    router = FakeRouter()
    executor = ToolExecutor(messenger=router)
    executor.compose = lambda contact, messages: "bora, às 21h"
    shown = []
    executor.confirm_ai = lambda p, c, m: shown.append(m) or m
    executor.run("reply_last_message", {"platform": "whatsapp"}, "responde à última mensagem que recebi")
    assert shown == ["bora, às 21h"] and router.calls == [("whatsapp", "bora, às 21h")]


def test_reply_last_message_dictated_is_sent_without_ai_confirmation():
    router = FakeRouter()
    executor = ToolExecutor(messenger=router)
    executor.confirm_ai = lambda p, c, m: None  # se fosse chamado, cancelava
    executor.run("reply_last_message", {"platform": "whatsapp"}, "responde à última mensagem a dizer que já vou")
    assert router.calls == [("whatsapp", "Já vou")]


def test_reply_cancelled_is_reported():
    router = FakeRouter()
    executor = ToolExecutor(messenger=router)
    executor.compose = lambda contact, messages: "ok"
    executor.confirm_ai = lambda p, c, m: None
    out = executor.run("reply_last_message", {"platform": "whatsapp"}, "responde à última mensagem")
    assert "NÃO foi enviada" in out and router.calls == []


def test_compose_reply_uses_llm_and_strips_quotes():
    from jarvis.brain import COMPOSE_SYSTEM, compose_reply

    class LLM:
        def complete(self, system, prompt):
            assert system == COMPOSE_SYSTEM and "<conversa>" in prompt and "bora jogar" in prompt
            return '"bora, logo às 21h"'
    assert compose_reply(LLM(), "Rafa", "[19:00] Rafa: bora jogar?") == "bora, logo às 21h"


def test_whatsapp_web_alias():
    apps = [("WhatsApp", "5319275A.WhatsAppDesktop!App")]
    assert system.find_start_app("WhatsApp Web", apps)[0] == "WhatsApp"
    assert system.find_start_app("wpp", apps)[0] == "WhatsApp"


# --- Spotify pela interface --------------------------------------------------------

def test_best_play_match():
    labels = ["Músicas apreciadas", "chill", "Mix de House", "Rádio de Drake", "Mix tranquila", "Tha Carter III de Lil Wayne"]
    assert labels[media.best_play_match(labels, "playlist chill")] == "chill"
    assert labels[media.best_play_match(labels, "mix de house")] == "Mix de House"
    assert labels[media.best_play_match(labels, "tha carter III")] == "Tha Carter III de Lil Wayne"
    assert media.best_play_match(labels, "Bohemian Rhapsody") is None


def test_liked_words():
    for q in ("favoritos", "uma música dos meus favoritos", "músicas apreciadas", "as minhas músicas", "músicas que gosto"):
        assert media._LIKED_WORDS.search(q), q
    assert not media._LIKED_WORDS.search("Bohemian Rhapsody")


@pytest.mark.parametrize("args, request_text, expected", [
    ({"play": "favoritos"}, "põe uma música dos meus favoritos", ("play", "favoritos")),
    ({"action": "pause"}, "skipa a música", ("next", "")),
    ({"action": "play"}, "passa à próxima", ("next", "")),
    ({"action": "skip"}, "", ("next", "")),
    ({"action": "play", "query": "chill"}, "põe a playlist chill", ("play", "chill")),
    ({"action": "previous"}, "volta à música anterior", ("previous", "")),
])
def test_music_args(args, request_text, expected):
    from jarvis.tools import music_args
    assert music_args(args, request_text) == expected


# --- mensagens (Discord separado, redes sociais) e janelas ------------------------------

from jarvis.actions import social, windows  # noqa: E402
from jarvis.actions.desktop_chat import discord_sections, format_discord_sections  # noqa: E402


def test_discord_sections_split_friends_groups_servers():
    home = ["Mensagens diretas", "2 menções, Rafosto", "1 menção, Broke bois"]
    servers = ["226 menções, Shadow Greenville Roleplay", "Mensagens não lidas, Roblox Car Scene",
               "No Hesi, FlaviBot.xyz, ..., pasta , 362 menções não lidas", "Greenville",
               "1.117 menções, Connecticut State Roleplay"]
    dms = ["Amigos4", "Solicitações de mensagens1", "RafostoTag do servidor: PAY", "Broke bois3 membros"]
    s = discord_sections(home, servers, dms)
    assert s["friends"] == [("Rafosto", 2)]
    assert s["groups"] == [("Broke bois", 1)]
    assert s["requests"] == 1
    assert ("Connecticut State Roleplay", 1117) in s["servers"] and len(s["servers"]) == 3
    text = format_discord_sections(s)
    assert "Amigos: Rafosto (2)" in text and "Grupos: Broke bois" in text
    assert "3 servidores" in text and text.index("Connecticut") < text.index("Shadow")


def test_social_title_reading():
    assert "3" in social.read_title("(3) Instagram", "Instagram")
    assert "sessão" in social.read_title("Iniciar sessão • Instagram", "Instagram")
    assert "nada de novo" in social.read_title("Mensagens | LinkedIn", "LinkedIn")


def test_social_check_closes_only_its_tab(monkeypatch):
    import pywinauto.keyboard

    keys = []
    monkeypatch.setattr(social.system, "open_url", lambda url: None)
    monkeypatch.setattr(pywinauto.keyboard, "send_keys", keys.append)
    out = social.check_site("instagram", wait_title=lambda: "(2) Instagram", settle=0)
    assert "2" in out and keys == ["^w"]


def test_window_matching():
    assert windows.matches("VALORANT", "VALORANT  ", r"C:\Riot\VALORANT-Win64-Shipping.exe")
    assert windows.matches("Spotify", "Spotify Premium", "Spotify.exe")
    assert not windows.matches("Spotify", "Jarvis — Spotify", "python.exe")
    assert not windows.matches("Discord", "Opera", "opera.exe")


# --- responder a quem mandou mensagem ------------------------------------------------

from jarvis.actions.desktop_chat import whatsapp_chat_name, whatsapp_preview  # noqa: E402
from jarvis.tools import parse_reply_to, unread_contacts  # noqa: E402

SUMMARY = """WhatsApp (2 por ler):
- IP ECL (16:40): Rafael: vou chegar atrasado
- Rafael Pedro (16:50): a tua loja é má
Discord:
- 👤 Amigos: Rafosto (2)
- 👥 Grupos: Broke bois
- 🌐 Comunidades: 3 servidores com mensagens por ler."""


def test_whatsapp_names_without_unread_count():
    assert whatsapp_chat_name("1 mensagem não lida Rafael Pedro 16:50 olá") == "Rafael Pedro"
    assert whatsapp_preview("3 mensagens não lidas Rafa 11:24 bora")[0] == "Rafa"


def test_unread_contacts_from_summary():
    assert unread_contacts(SUMMARY) == [("whatsapp", "IP ECL"), ("whatsapp", "Rafael Pedro"),
                                        ("discord", "Rafosto"), ("discord", "Broke bois")]


def test_parse_reply_to():
    unread = unread_contacts(SUMMARY)
    assert parse_reply_to("sim responde a esta Rafael Pedro a criticar a sua loja e diz L bozo", unread) == \
        ("whatsapp", "Rafael Pedro", "L bozo")
    assert parse_reply_to("responde ao Rafael Pedro", unread) == ("whatsapp", "Rafael Pedro", None)
    assert parse_reply_to("responde ao rafosto", unread) == ("discord", "Rafosto", None)
    assert parse_reply_to("abre o spotify", unread) is None
    assert parse_reply_to("responde ao Rafael Pedro", []) is None


def test_brain_reply_flow_asks_then_sends():
    from jarvis.brain import Brain
    from tests.test_brain import FakeLLM, FakeMessenger

    messenger = FakeMessenger()
    brain = Brain(llm=FakeLLM([]), executor=ToolExecutor(messenger=messenger))
    brain.last_unread = unread_contacts(SUMMARY)
    assert "O que queres dizer ao Rafael Pedro no WhatsApp?" == brain.handle("responde ao Rafael Pedro")
    brain.handle("L bozo")
    assert messenger.sent == [("whatsapp", "Rafael Pedro", "L bozo")]
    brain.handle("responde ao rafosto e diz bora jogar")
    assert messenger.sent[-1] == ("discord", "Rafosto", "bora jogar")


def test_model_question_sets_pending_send():
    from jarvis.brain import Brain
    from jarvis.llm import StepResult
    from tests.test_brain import FakeLLM, FakeMessenger

    messenger = FakeMessenger()
    question = StepResult(text="Escreve o que queres dizer com o Rafael Pedro no WhatsApp. "
                               "![x](https://i.imgur.com/1.png)", tool_calls=[])
    llm = FakeLLM([question, question])
    brain = Brain(llm=llm, executor=ToolExecutor(messenger=messenger))
    reply = brain.handle("quero falar com alguém")
    assert "imgur" not in reply
    brain.handle("ganda L")
    assert messenger.sent == [("whatsapp", "Rafael Pedro", "ganda L")]


def test_history_page_links_order_and_titles():
    class Info:
        def __init__(self, name):
            self.name = name

    class Link:
        def __init__(self, url, name):
            self.element_info = Info(name)
            self.iface_value = type("V", (), {"CurrentValue": url})()

    class Doc:
        def descendants(self, control_type):
            return [Link("https://www.youtube.com/", "Início"),
                    Link("https://www.youtube.com/watch?v=PR-nxqmG3V8&t=5s", "Jarvis for Linux 3 minutes, 57 seconds"),
                    Link("https://www.youtube.com/watch?v=PR-nxqmG3V8", "Jarvis for Linux"),
                    Link("https://www.youtube.com/watch?v=p-oFxcgg1MY", "Drive Thru 16 minutes")]

    links = media.history_page_links(Doc())
    assert [(v, t) for v, t, _ in links] == [("PR-nxqmG3V8", "Jarvis for Linux"), ("p-oFxcgg1MY", "Drive Thru")]


def test_open_watched_video_prefers_youtube_history_page(monkeypatch):
    monkeypatch.setattr(media, "open_from_history_page", lambda position: "Drive Thru")
    assert "Drive Thru" in media.open_watched_video(1) and "histórico do YouTube" in media.open_watched_video(1)
