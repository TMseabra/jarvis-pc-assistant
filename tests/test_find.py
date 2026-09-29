import pytest

from jarvis.actions import find
from jarvis.actions.find import parse_image_request, parse_links_request, parse_results

DDG_PAGE = """
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.olx.pt%2Fcarros%2Fq-alpina%2F&amp;rut=x">
<b>Alpina</b> - OLX</a>
<a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Anúncio</a>
<a class="result__a" href="https://encontracarros.pt/marca/alpina">Carros Alpina &amp; Preços</a>
"""


def test_parse_ddg_results():
    assert parse_results(DDG_PAGE) == [("Alpina - OLX", "https://www.olx.pt/carros/q-alpina/"),
                                       ("Carros Alpina & Preços", "https://encontracarros.pt/marca/alpina")]


def test_web_links_text():
    out = find.web_links("carros alpina à venda", post=lambda data: DDG_PAGE)
    assert "1. Alpina - OLX\nhttps://www.olx.pt/carros/q-alpina/" in out


@pytest.mark.parametrize("text,expected", [
    ("mostra me uma foto de um audi", "um audi"),
    ("manda-me imagens do Ferrari F40", "Ferrari F40"),
    ("quero ver uma foto de um gato", "um gato"),
    ("mostra-me o ecrã", None),
    ("abre o spotify", None),
])
def test_parse_image_request(text, expected):
    assert parse_image_request(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("podes me mostrar carros da alpina para venda", "carros da alpina para venda"),
    ("dá-me links sobre receitas de bacalhau", "receitas de bacalhau"),
    ("pesquisa no google melhores portáteis 2026", "melhores portáteis 2026"),
    ("pesquisa no standvirtual audi", None),
    ("quem ganhou o jogo do benfica", None),
])
def test_parse_links_request(text, expected):
    assert parse_links_request(text) == expected


class _Resp:
    def __init__(self, json=None, content=b"", kind="image/jpeg", status=200):
        self._json, self.content, self.status_code = json, content, status
        self.headers = {"content-type": kind}

    def json(self):
        return self._json


def test_find_image_downloads_first_good_photo(tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(find, "_show", shown.append)
    api = {"results": [{"url": "https://x/small.jpg", "title": "mini"}, {"url": "https://x/audi.jpg", "title": "Audi RS6"}]}

    def get(url, params=None):
        if "openverse" in url:
            assert params["q"] == "audi"
            return _Resp(json=api)
        return _Resp(content=b"x" * (100 if "small" in url else 20000))

    out = find.find_image("um audi", get=get, folder=tmp_path)
    path = next(tmp_path.glob("*.jpg"))
    assert f"📎 {path}" in out and "Audi RS6" in out and shown == [path]


def test_brain_image_and_screenshot_shortcuts(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    calls = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": calls.append((name, args)) or "ok")
    brain = Brain(llm=FakeLLM([]), executor=executor)
    brain.handle("mostra me uma foto de um audi")
    brain.handle("manda-me uma foto do ecrã")
    brain.handle("podes me mostrar carros da alpina para venda")
    assert calls == [("show_image", {"query": "um audi"}), ("screenshot", {}),
                     ("web_links", {"query": "carros da alpina para venda"})]
