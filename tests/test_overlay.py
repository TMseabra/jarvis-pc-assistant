import pytest

from jarvis import overlay


@pytest.mark.parametrize("text,expected", [
    ("diz ola na tela do pc", "Olá"),
    ("escreve 'bom dia' no ecrã em grande", "Bom dia"),
    ("jarvis mostra Benfica campeão no ecrã do computador", "Benfica campeão"),
    ("mostra-me o ecrã", None),
    ("manda-me um print do ecrã", None),
])
def test_parse_overlay_request(text, expected):
    assert overlay.parse_request(text) == expected


def test_brain_overlay_shortcut(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    calls = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": calls.append((name, args)) or "ok")
    brain = Brain(llm=FakeLLM([]), executor=executor)
    brain.handle("diz ola na tela do pc")
    brain.handle("manda-me um print do ecrã")
    assert calls == [("show_on_screen", {"text": "Olá"}), ("screenshot", {})]


def test_memes_flow_and_requests(tmp_path):
    from jarvis import memes

    shown = []
    options = [("Drake meme", tmp_path / "a.jpg"), ("Cat meme", tmp_path / "b.jpg")]
    flow = memes.MemeFlow(fetcher=lambda: options, show=shown.append)
    out = flow.start()
    assert "1. Drake meme" in out and f"📎 {tmp_path / 'a.jpg'}" in out and flow.waiting
    assert "de 1 a 2" in flow.choose("9")
    assert "Cat meme" in flow.choose("o 2") and shown == [tmp_path / "b.jpg"] and not flow.waiting
    assert memes.MEME_REQUEST.search("adiciona um meme na tela do pc")
    assert memes.JUMPSCARE_REQUEST.search("da um jumsacre na tela do pc")
    assert memes.JUMPSCARE_REQUEST.search("dá um jumpscare no pc")
    assert not memes.MEME_REQUEST.search("abre o spotify")


def test_memes_fetch_skips_nsfw(tmp_path):
    from jarvis import memes

    class R:
        def __init__(self, json=None, content=b"", status=200):
            self._j, self.content, self.status_code = json, content, status

        def json(self):
            return self._j

    api = {"memes": [{"title": "bad", "url": "https://i/x.jpg", "nsfw": True},
                     {"title": "Good one", "url": "https://i/y.png", "nsfw": False, "spoiler": False},
                     {"title": "video", "url": "https://v/z.mp4"}]}
    got = memes.fetch(5, get=lambda url: R(json=api) if "meme-api" in url else R(content=b"x" * 5000), folder=tmp_path)
    assert [t for t, _ in got] == ["Good one"] and got[0][1].exists()


def test_brain_meme_and_jumpscare(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    executor = ToolExecutor(messenger=FakeMessenger())
    shown, scares = [], []
    executor.memes.fetcher = lambda: [("A", "a.jpg"), ("B", "b.jpg")]
    executor.memes.show = shown.append
    from jarvis import memes

    monkeypatch.setattr(memes.overlay, "jumpscare", lambda: scares.append(1))
    brain = Brain(llm=FakeLLM([]), executor=executor)
    assert "1. A" in brain.handle("adiciona um meme na tela do pc")
    assert "B" in brain.handle("2") and shown == ["b.jpg"]
    assert "Jumpscare" in brain.handle("da um jumsacre na tela do pc") and scares == [1]


def test_scary_face_and_scream(tmp_path):
    img = overlay.scary_face(300)
    assert img.size == (300, 300)
    wav = overlay.scream_wav(tmp_path / "g.wav", seconds=0.3)
    assert wav.stat().st_size > 10000
