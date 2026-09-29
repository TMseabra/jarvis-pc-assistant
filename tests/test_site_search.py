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


from jarvis.actions.site_search import parse_price, parse_refine  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("mercedes de 100k para cima", ("mercedes", 100000, None)),
    ("mercedes 100k", ("mercedes 100k", None, None)),
    ("bmw até 20 mil euros", ("bmw", None, 20000)),
    ("audi entre 10k e 15k", ("audi", 10000, 15000)),
    ("porsche acima de 150.000€", ("porsche", 150000, None)),
    ("carros até 2020", ("carros até 2020", None, None)),
    ("iphone menos de 500 euros", ("iphone", None, 500)),
    ("golf até 100 mercedes", ("golf mercedes", None, 100)),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_standvirtual_price_filter(monkeypatch):
    opened = []
    monkeypatch.setattr(site_search.system, "open_url", opened.append)
    out = site_search.site_search("standvirtual", "mercedes de 100k para cima")
    assert opened == ["https://www.standvirtual.com/carros/q-mercedes?search%5Bfilter_float_price%3Afrom%5D=100000"]
    assert "a partir de 100 000 €" in out


def test_refine_last_search_with_price(monkeypatch):
    opened = []
    monkeypatch.setattr(site_search.system, "open_url", opened.append)
    assert parse_refine("e agora mostra me os mercedes so de 100k para cima") is None  # ainda sem pesquisa
    site_search.site_search("standvirtual", "mercedes")
    site, query = parse_refine("e agora mostra me os mercedes so de 100k para cima")
    assert site == "standvirtual"
    site_search.site_search(site, query)
    assert opened[-1].endswith("q-mercedes?search%5Bfilter_float_price%3Afrom%5D=100000")
    assert parse_refine("só até 20k")[1].startswith("mercedes")
    assert parse_refine("abre o spotify") is None


def test_site_without_price_filter_says_so(monkeypatch):
    monkeypatch.setattr(site_search.system, "open_url", lambda url: None)
    assert "põe-no tu" in site_search.site_search("worten", "portátil até 800 euros")
