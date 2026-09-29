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
