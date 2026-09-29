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


def site_search(site: str, query: str) -> str:
    query = query.strip().strip("\"'")
    name, url = search_url(site, query)
    system.open_url(url)
    if "google.com/search" in url and "google" not in site.lower():
        return f"Não sei pesquisar diretamente no {name}: abri o Google com \"{query}\" nesse site."
    return f"Pesquisei \"{query}\" no {name}."


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
