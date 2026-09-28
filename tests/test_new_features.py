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
