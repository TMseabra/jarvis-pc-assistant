import pytest

from jarvis.music_intents import parse_music, parse_suggestions


@pytest.mark.parametrize("text,expected", [
    ("mete uma musica do bad bunny", ("play", "bad bunny")),
    ("toca uma musica do badbunny", ("play", "badbunny")),
    ("põe uma música da Rosalía", ("play", "Rosalía")),
    ("coloca músicas dos Arctic Monkeys", ("play", "Arctic Monkeys")),
    ("mete Blinding Lights no spotify", ("play", "Blinding Lights")),
    ("mete outra musica", ("next", "")),
    ("podes trocar de musica", ("next", "")),
    ("salta esta", ("next", "")),
    ("passa à próxima", ("next", "")),
    ("mete outra musica do mesmo genero", ("similar", "play")),
    ("mete uma música parecida", ("similar", "play")),
    ("podes me dizer que musica tem vibes igual", ("similar", "suggest")),
    ("abre o spotify", None),
    ("mete o valorant", None),
])
def test_parse_music(text, expected):
    assert parse_music(text) == expected


def test_parse_suggestions():
    text = "1. After the Rain - Zedd\n\"Stay\" - The Kid LAROI\nFree - Florence\nOlá"
    assert parse_suggestions(text, "Florence + The Machine - Free") == [("After the Rain", "Zedd"),
                                                                        ("Stay", "The Kid LAROI")]


def _brain(monkeypatch, answer="After the Rain - Zedd\nStay - The Kid LAROI\nLevitating - Dua Lipa"):
    from jarvis.actions import media
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    calls = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": calls.append((name, args)) or "a tocar")
    monkeypatch.setattr(media, "spotify_title", lambda: "Florence - Free")
    llm = FakeLLM([])
    monkeypatch.setattr(llm, "complete", lambda system, prompt: answer, raising=False)
    return Brain(llm=llm, executor=executor), calls


def test_similar_plays_first_and_offers_the_rest(monkeypatch):
    brain, calls = _brain(monkeypatch)
    out = brain.handle("mete outra musica do mesmo genero")
    assert calls == [("music", {"action": "play", "query": "After the Rain Zedd"})]
    assert "Estava a tocar Florence - Free" in out and "1. Stay - The Kid LAROI" in out
    brain.handle("mete a 1")
    assert calls[-1] == ("music", {"action": "play", "query": "Stay The Kid LAROI"})


def test_similar_suggest_then_mete_uma_dessas(monkeypatch):
    brain, calls = _brain(monkeypatch)
    out = brain.handle("podes me dizer que musica tem vibes igual")
    assert calls == [] and "1. After the Rain - Zedd" in out
    brain.handle("mete uma dessas ent")
    assert calls == [("music", {"action": "play", "query": "After the Rain Zedd"})]


def test_skip_and_play_artist(monkeypatch):
    brain, calls = _brain(monkeypatch)
    brain.handle("mete outra musica")
    brain.handle("mete uma musica do bad bunny")
    assert calls == [("music", {"action": "next"}), ("music", {"action": "play", "query": "bad bunny"})]
