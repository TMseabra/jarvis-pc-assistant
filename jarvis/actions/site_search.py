"""Pesquisar dentro de um site: "no Standvirtual pesquisa Audi A3" abre logo os resultados do site.

1. Sites conhecidos: link de pesquisa do próprio site.
2. Outros sites: o link de pesquisa que o site anuncia (OpenSearch, o mesmo que o browser usa
   para "pesquisar neste site"), guardado em .jarvis/pesquisa_sites.json.
3. Se nada disso der: Google só com resultados desse site (site:dominio).
"""

import json
import re
import unicodedata
import urllib.parse

from jarvis.actions import system
from jarvis.config import PROJECT_ROOT

CACHE = PROJECT_ROOT / ".jarvis" / "pesquisa_sites.json"

# {q} = texto codificado para URL; {slug} = "audi-a3"
KNOWN = {
    "standvirtual": ("Standvirtual", "https://www.standvirtual.com/carros/q-{slug}"),
    "olx": ("OLX", "https://www.olx.pt/ads/q-{slug}/"),
    "custojusto": ("CustoJusto", "https://www.custojusto.pt/portugal/q/{q}"),
    "worten": ("Worten", "https://www.worten.pt/search?query={q}"),
    "fnac": ("Fnac", "https://www.fnac.pt/SearchResult/ResultList.aspx?Search={q}"),
    "kuantokusta": ("KuantoKusta", "https://www.kuantokusta.pt/search?q={q}"),
    "amazon": ("Amazon", "https://www.amazon.es/s?k={q}"),
    "aliexpress": ("AliExpress", "https://www.aliexpress.com/w/wholesale-{slug}.html"),
    "ebay": ("eBay", "https://www.ebay.com/sch/i.html?_nkw={q}"),
    "idealista": ("Idealista", "https://www.idealista.pt/pesquisar/?q={q}"),
    "imovirtual": ("Imovirtual", "https://www.imovirtual.com/pt/resultados/comprar/q-{slug}"),
    "wikipedia": ("Wikipédia", "https://pt.wikipedia.org/w/index.php?search={q}"),
    "github": ("GitHub", "https://github.com/search?q={q}"),
    "reddit": ("Reddit", "https://www.reddit.com/search/?q={q}"),
    "twitch": ("Twitch", "https://www.twitch.tv/search?term={q}"),
    "steam": ("Steam", "https://store.steampowered.com/search/?term={q}"),
    "instagram": ("Instagram", "https://www.instagram.com/explore/search/keyword/?q={q}"),
    "linkedin": ("LinkedIn", "https://www.linkedin.com/search/results/all/?keywords={q}"),
    "pinterest": ("Pinterest", "https://www.pinterest.com/search/pins/?q={q}"),
    "x": ("X", "https://x.com/search?q={q}"),
    "twitter": ("X", "https://x.com/search?q={q}"),
    "googlemaps": ("Google Maps", "https://www.google.com/maps/search/{q}"),
    "maps": ("Google Maps", "https://www.google.com/maps/search/{q}"),
    "imdb": ("IMDb", "https://www.imdb.com/find/?q={q}"),
    "netflix": ("Netflix", "https://www.netflix.com/search?q={q}"),
    "continente": ("Continente", "https://www.continente.pt/pesquisa/?q={q}"),
    "pingodoce": ("Pingo Doce", "https://www.pingodoce.pt/pesquisa/?q={q}"),
    "ikea": ("IKEA", "https://www.ikea.com/pt/pt/search/?q={q}"),
    "decathlon": ("Decathlon", "https://www.decathlon.pt/search?Ntt={q}"),
    "zara": ("Zara", "https://www.zara.com/pt/pt/search?searchTerm={q}"),
    "shein": ("SHEIN", "https://pt.shein.com/pdsearch/{q}/"),
    "vinted": ("Vinted", "https://www.vinted.pt/catalog?search_text={q}"),
}
# Estes têm ferramentas próprias (vídeos, música...): não são tratados aqui.
OTHER_TOOLS = {"youtube", "tiktok", "spotify", "roblox", "whatsapp", "discord", "telegram", "claude",
               "claudinho", "chatgpt", "google", "net", "internet", "web", "pc", "computador"}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9.]", "", text)


def site_key(site: str) -> str:
    """'Standvirtual', 'standvirtual.com', 'o site do OLX' -> 'standvirtual' / 'olx'."""
    site = re.sub(r"^(?:o|a)\s+|^site\s+(?:do|da|de)?\s*", "", site.strip(), flags=re.IGNORECASE)
    key = _fold(site)
    key = re.sub(r"^(?:https?)?(?:www\.)?", "", key)
    base = key.split(".")[0]
    return base if base in KNOWN else key


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode().lower()).strip("-")


def fill(template: str, query: str) -> str:
    return template.replace("{q}", urllib.parse.quote(query)).replace("{slug}", _slug(query)) \
        .replace("{searchTerms}", urllib.parse.quote(query))


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def discover(domain: str, get=None) -> str | None:
    """Link de pesquisa OpenSearch que o site anuncia na página inicial (com {searchTerms})."""
    import httpx

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36"}
    get = get or (lambda url: httpx.get(url, headers=headers, follow_redirects=True, timeout=6).text)
    try:
        html = get(f"https://{domain}/")
        link = re.search(r"<link[^>]+application/opensearchdescription\+xml[^>]*>", html, re.IGNORECASE)
        href = re.search(r'href="([^"]+)"', link.group(0)) if link else None
        if not href:
            return None
        xml = get(urllib.parse.urljoin(f"https://{domain}/", href.group(1).replace("&amp;", "&")))
        url = re.search(r'<Url[^>]+type="text/html"[^>]+template="([^"]+)"', xml) or \
            re.search(r'<Url[^>]+template="([^"]+)"[^>]+type="text/html"', xml)
        return url.group(1).replace("&amp;", "&") if url and "{searchTerms}" in url.group(1) else None
    except Exception:
        return None


def search_url(site: str, query: str, get=None) -> tuple[str, str]:
    """(nome do site, link dos resultados)."""
    key = site_key(site)
    if key in KNOWN:
        name, template = KNOWN[key]
        return name, fill(template, query)
    domains = [key] if "." in key else [f"www.{key}.pt", f"www.{key}.com"]
    cache = _load_cache()
    for domain in domains:
        template = cache.get(domain) or discover(domain, get)
        if template:
            if domain not in cache:
                cache[domain] = template
                try:
                    CACHE.parent.mkdir(parents=True, exist_ok=True)
                    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
                except OSError:
                    pass
            return domain.removeprefix("www."), template.replace("{searchTerms}", urllib.parse.quote(query))
    where = f"site:{key}" if "." in key else site.strip()
    return site.strip(), "https://www.google.com/search?q=" + urllib.parse.quote(f"{query} {where}")


# --- preços: "de 100k para cima", "até 20 mil euros", "entre 10k e 15k" --------------------

_AMOUNT = r"(\d+(?:[.,]\d+)*)\s*(k|mil|m|milh(?:ão|ao|ões|oes)|€|euros?)?(?![a-zà-ú])"
_PRICE_PATTERNS = [
    ("range", re.compile(rf"\b(?:entre|de)\s+{_AMOUNT}\s+(?:e|a|até)\s+{_AMOUNT}", re.IGNORECASE)),
    ("min", re.compile(rf"\b(?:de|com)\s+{_AMOUNT}\s+(?:para|pra|p)\s+cima\b", re.IGNORECASE)),
    ("max", re.compile(rf"\b(?:de|com)\s+{_AMOUNT}\s+(?:para|pra|p)\s+baixo\b", re.IGNORECASE)),
    ("min", re.compile(rf"\b(?:acima\s+d[eo]s?|mais\s+de|a\s+partir\s+de|desde|m[ií]nimo(?:\s+de)?|no\s+m[ií]nimo)\s+{_AMOUNT}",
                       re.IGNORECASE)),
    ("max", re.compile(rf"\b(?:at[ée]|abaixo\s+d[eo]s?|menos\s+de|m[aá]ximo(?:\s+de)?|no\s+m[aá]ximo)\s+{_AMOUNT}",
                       re.IGNORECASE)),
]
_PRICE_WORDS = re.compile(r"\b(?:euros?|€|de\s+pre[cç]o|pre[cç]o|a\s+custar|que\s+custem?)\b", re.IGNORECASE)


def _to_euros(number: str, unit: str | None) -> int | None:
    unit = (unit or "").lower()
    value = float(number.replace(".", "").replace(",", ".")) if not re.fullmatch(r"\d+[.,]\d{1,2}", number) \
        else float(number.replace(",", "."))
    if unit in ("k", "mil"):
        value *= 1000
    elif unit == "m" or unit.startswith("milh"):
        value *= 1_000_000
    elif not unit and 1900 <= value <= 2100:
        return None  # "até 2020" é um ano, não um preço
    return int(value)


def parse_price(text: str) -> tuple[str, int | None, int | None]:
    """'mercedes de 100k para cima' -> ('mercedes', 100000, None)."""
    low = high = None
    for kind, pattern in _PRICE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if kind == "range":
            low, high = _to_euros(m.group(1), m.group(2) or m.group(4)), _to_euros(m.group(3), m.group(4))
        elif kind == "min":
            low = _to_euros(m.group(1), m.group(2))
        else:
            high = _to_euros(m.group(1), m.group(2))
        if low is None and high is None:
            continue
        text = (text[:m.start()] + text[m.end():])
        break
    text = _PRICE_WORDS.sub("", text)
    return " ".join(text.split()), low, high


# Filtro de preço no link de cada site ({low}/{high} em euros).
PRICE_PARAMS = {
    "standvirtual": ("search[filter_float_price:from]={low}", "search[filter_float_price:to]={high}"),
    "olx": ("search[filter_float_price:from]={low}", "search[filter_float_price:to]={high}"),
    "imovirtual": ("priceMin={low}", "priceMax={high}"),
    "ebay": ("_udlo={low}", "_udhi={high}"),
    "custojusto": ("ps={low}", "pe={high}"),
    "vinted": ("price_from={low}", "price_to={high}"),
}


def add_price(url: str, key: str, low: int | None, high: int | None) -> str | None:
    if low is None and high is None:
        return url
    params = PRICE_PARAMS.get(key)
    if key == "amazon":  # em cêntimos: rh=p_36:MIN-MAX
        return url + f"&rh=p_36:{(low or 0) * 100}-{(high * 100) if high else ''}"
    if not params:
        return None
    parts = []
    if low is not None:
        parts.append(params[0].format(low=low))
    if high is not None:
        parts.append(params[1].format(high=high))
    query = "&".join(urllib.parse.quote(p, safe="=") for p in parts)
    return url + ("&" if "?" in url else "?") + query


def _euros(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " €"


LAST: dict = {}  # última pesquisa: {"site": ..., "query": ...} (para "e agora só de 100k para cima")


def site_search(site: str, query: str, request: str = "") -> str:
    query, low, high = parse_price(query.strip().strip("\"'"))
    if low is None and high is None and request:
        _, low, high = parse_price(request)
    name, url = search_url(site, query)
    LAST.update(site=site, query=query)
    priced = add_price(url, site_key(site), low, high)
    system.open_url(priced or url)
    if "google.com/search" in url and "google" not in site.lower():
        return f"Não sei pesquisar diretamente no {name}: abri o Google com \"{query}\" nesse site."
    price = ""
    if low is not None or high is not None:
        span = (f"entre {_euros(low)} e {_euros(high)}" if low is not None and high is not None
                else f"a partir de {_euros(low)}" if low is not None else f"até {_euros(high)}")
        price = f", {span}" if priced else f" (não sei pôr o filtro de preço {span} neste site: põe-no tu)"
    return f"Pesquisei \"{query}\" no {name}{price}."


# "e agora mostra-me só os de 100k para cima", "agora até 20 mil"
_REFINE_FILLER = {"e", "agora", "mostra", "me", "mostrame", "so", "só", "os", "as", "o", "a", "de", "com", "que",
                  "custem", "custam", "filtra", "filtrar", "pesquisa", "procura", "jarvis", "apenas", "mas", "ai", "aí",
                  "carros", "anuncios", "anúncios", "resultados", "então", "entao", "pff", "por", "favor"}


def parse_refine(request: str) -> tuple[str, str] | None:
    """Depois de uma pesquisa num site, um pedido só com preço refaz a pesquisa com o filtro."""
    if not LAST:
        return None
    rest, low, high = parse_price(request)
    if low is None and high is None:
        return None
    words = [w for w in re.findall(r"[\wÀ-ú]+", rest.lower()) if w not in _REFINE_FILLER]
    if len(words) > 3:
        return None
    query = " ".join(words) or LAST["query"]
    return LAST["site"], f"{query} {request_price_text(low, high)}"


def request_price_text(low: int | None, high: int | None) -> str:
    if low is not None and high is not None:
        return f"entre {low} e {high} euros"
    return f"de {low} para cima" if low is not None else f"até {high} euros"


# "no standvirtual pesquisa audi a3", "pesquisa audi a3 no standvirtual", "procura no olx por uma bicicleta"
_VERB = r"(?:pesquisa|pesquisar|procura|procurar|busca|buscar|pesquisa-me|procura-me|mostra-me)"
_SITE = r"(?:o\s+site\s+(?:do|da|de)\s+|site\s+(?:do|da|de)\s+)?(?P<site>[\w.-]+(?:\s+maps)?)"
_ABOUT = r"(?:(?:por|sobre|o|a|os|as|um|uma)\s+)*"
_PATTERNS = [
    re.compile(rf"^\W*(?:jarvis\W+)?(?:no|na|em)\s+{_SITE}\s*,?\s+{_VERB}\s+{_ABOUT}(?P<q>.+?)\W*$", re.IGNORECASE),
    re.compile(rf"^\W*(?:jarvis\W+)?(?:podes\s+)?{_VERB}\s+(?:no|na|em)\s+{_SITE}\s+{_ABOUT}(?P<q>.+?)\W*$", re.IGNORECASE),
    re.compile(rf"^\W*(?:jarvis\W+)?(?:podes\s+)?{_VERB}\s+{_ABOUT}(?P<q>.+?)\s+(?:no|na|em)\s+{_SITE}\W*$", re.IGNORECASE),
    re.compile(rf"^\W*(?:jarvis\W+)?abre\s+o\s+{_SITE}\s+e\s+{_VERB}\s+{_ABOUT}(?P<q>.+?)\W*$", re.IGNORECASE),
]


def parse_site_search(request: str) -> tuple[str, str] | None:
    """Pedido -> (site, pesquisa), só para sites (não para YouTube, Spotify, a net em geral...)."""
    for pattern in _PATTERNS:
        m = pattern.match(request.strip())
        if not m:
            continue
        site, query = m.group("site"), m.group("q")
        key = site_key(site)
        if key in OTHER_TOOLS or key.split(".")[0] in OTHER_TOOLS or not query.strip():
            return None
        if key in KNOWN or "." in key:
            return site, query
    return None
