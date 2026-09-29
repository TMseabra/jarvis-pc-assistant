import pytest

from jarvis import understand
from jarvis.voice import _echoes_hotwords, strip_wake_word


@pytest.mark.parametrize("text,expected", [
    # nomes mal ouvidos (frases reais do registo)
    ("Deixa eu ver se agora isto vai abrir o Lavaloranti.", "Deixa eu ver se agora isto vai abrir o Valorant."),
    ("Então agora quando eu quero falar sobre o Cláudio", "Então agora quando eu quero falar sobre o Claudinho"),
    ("abre o cloud", "abre o Claudinho"),
    ("diz ao cloud para continuar", "diz ao Claudinho para continuar"),
    ("abre o espotifai e o uatsapp", "abre o Spotify e o WhatsApp"),
    ("abre o Tik tok", "abre o TikTok"),
    ("no stand virtual pesquisa audi", "no Standvirtual pesquisa audi"),
    # gralhas
    ("abrre o spotify", "abre o spotify"),
    ("pesqisa gatos no youtube", "pesquisa gatos no youtube"),
    ("podes procurra uma música", "podes procura uma música"),
    ("abre o Steem", "abre o Steam"),
    ("abre o Discrod", "abre o Discord"),
    ("fecha o Robloxx", "fecha o Roblox"),
    # fala
    ("epá abre o Spotify, tipo, e toca Bad Bunny", "abre o Spotify, e toca Bad Bunny"),
    ("isto, isto, isto é bom", "isto é bom"),
    ("não, não quero", "não, não quero"),
    ("ha novas mensagens?", "ha novas mensagens?"),
    # não mexe no que está certo
    ("abre o Greenville no Roblox", "abre o Greenville no Roblox"),
    ("abre o meu CV", "abre o meu CV"),
    ("abre a calculadora", "abre a calculadora"),
    ("mete uma música do Bad Bunny", "mete uma música do Bad Bunny"),
    ("o cloud é uma nuvem", "o cloud é uma nuvem"),
])
def test_correct(text, expected):
    assert understand.correct(text) == expected
    assert understand.correct(understand.correct(text)) == understand.correct(text)  # idempotente


def test_contact_named_claudio_is_not_changed(monkeypatch):
    from jarvis import contacts

    monkeypatch.setattr(contacts, "known_names", lambda contacts_=None: ["Claudio"])
    assert understand.correct("manda msg ao Claudio no Discord") == "manda msg ao Claudio no Discord"


def test_fuzzy_match_against_contacts_and_apps():
    vocab = ["Rafosto", "Battlefield 2042", "Calculadora"]
    assert understand.fix_entities("abre o Battlefeld 2042", vocab) == "abre o Battlefield 2042"
    assert understand.fix_entities("abre a calculadra", vocab) == "abre a Calculadora"
    assert understand.fix_entities("abre o CV", vocab) == "abre o CV"


@pytest.mark.parametrize("text,expected", [
    ("Jarvis, abre o Spotify.", "abre o Spotify."),
    ("Ei, ei, ei Jarvis, abre o Greenville no Roblox.", "abre o Greenville no Roblox."),
    ("O André desapareceu. Ei, ei, ei Jarvis, abre o Greenville no Roblox, se vai achar.",
     "abre o Greenville no Roblox, se vai achar."),
    ("Ela às vezes não pega se eu falar. Ei Jarvis, abre o Visual Studio Code.", "abre o Visual Studio Code."),
    ("Ei, Travis, abre o Spotify", "abre o Spotify"),
    ("Ei Jarvis, abre o Spotify. Ei Jarvis, pausa.", "abre o Spotify. pausa."),
    ("o Jarvis é fixe", None),
    ("abre o Spotify", None),
    ("falámos do Travis ontem", None),
])
def test_wake_word_anywhere_with_ei(text, expected):
    assert strip_wake_word(text) == expected


def test_hotword_echo_is_hallucination():
    assert _echoes_hotwords("Jarvis Spotify Steam")
    assert not _echoes_hotwords("abre o Spotify")


def test_brain_corrects_typed_text(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    calls = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": calls.append((name, args)) or "feito")
    brain = Brain(llm=FakeLLM([]), executor=executor)
    brain.handle("no stand virtual pesquisa audi a3")
    assert calls[-1][0] == "site_search" and calls[-1][1]["site"] == "Standvirtual"
