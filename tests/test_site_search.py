import pytest

from jarvis.actions import site_search
from jarvis.actions.site_search import discover, parse_site_search, search_url


@pytest.mark.parametrize("text,expected", [
    ("No standvirtual pesquisa sobre audia", ("standvirtual", "audia")),
    ("no Standvirtual pesquisa Audi A3", ("Standvirtual", "Audi A3")),
    ("pesquisa uma bicicleta no OLX", ("OLX", "bicicleta")),
    ("procura no olx por uma bicicleta", ("olx", "bicicleta")),
    ("jarvis pesquisa iphone 15 na worten", ("worten", "iphone 15")),
    ("abre o standvirtual e pesquisa bmw m3", ("standvirtual", "bmw m3")),
    ("pesquisa gatos no youtube", None),
    ("pesquisa quem ganhou o jogo na net", None),
    ("abre o spotify", None),
])
def test_parse_site_search(text, expected):
    assert parse_site_search(text) == expected


def test_known_sites_urls():
    assert search_url("Standvirtual", "Audi A3") == ("Standvirtual", "https://www.standvirtual.com/carros/q-audi-a3")
    assert search_url("worten.pt", "iphone 15")[1] == "https://www.worten.pt/search?query=iphone%2015"


def test_opensearch_discovery_and_google_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(site_search, "CACHE", tmp_path / "cache.json")
    pages = {
        "https://loja.pt/": '<link rel="search" type="application/opensearchdescription+xml" href="/os.xml">',
        "https://loja.pt/os.xml": '<Url type="text/html" template="https://loja.pt/procura?t={searchTerms}"/>',
    }
    get = lambda url: pages.get(url, "")  # noqa: E731
    assert discover("loja.pt", get) == "https://loja.pt/procura?t={searchTerms}"
    assert search_url("loja.pt", "mesa azul", get)[1] == "https://loja.pt/procura?t=mesa%20azul"
    assert "loja.pt" in (tmp_path / "cache.json").read_text()
    name, url = search_url("outra.pt", "x", lambda url: "")
    assert url.startswith("https://www.google.com/search?q=") and "site%3Aoutra.pt" in url


def test_brain_site_search_shortcut(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    opened = []
    monkeypatch.setattr(site_search.system, "open_url", opened.append)
    brain = Brain(llm=FakeLLM([]), executor=ToolExecutor(messenger=FakeMessenger()))
    assert "Pesquisei \"audia\" no Standvirtual" in brain.handle("No standvirtual pesquisa sobre audia")
    assert opened == ["https://www.standvirtual.com/carros/q-audia"]
