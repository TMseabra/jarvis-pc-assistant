"""Encontrar coisas na net sem chave de API: links (DuckDuckGo) e fotos (Openverse).

- links: "mostra-me carros da Alpina à venda" -> os 5 primeiros resultados, com o link.
- fotos: "mostra-me uma foto de um Audi" -> descarrega uma foto, abre-a no PC e, se o pedido
  vier do Telegram, é enviada no chat (linha "📎 caminho").
"""

import html
import re
import time
import urllib.parse

from jarvis.config import PROJECT_ROOT

IMAGES_DIR = PROJECT_ROOT / ".jarvis" / "imagens"
_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
_RESULT = re.compile(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _real_url(href: str) -> str:
    """Os links do DuckDuckGo às vezes vêm como //duckduckgo.com/l/?uddg=<link>."""
    href = html.unescape(href)
    if "uddg=" in href:
        return urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href).query)["uddg"][0])
    return href if href.startswith("http") else "https:" + href


def parse_results(page: str, limit: int = 5) -> list[tuple[str, str]]:
    out, seen = [], set()
    for href, title in _RESULT.findall(page):
        url = _real_url(href)
        if "duckduckgo.com/y.js" in url or url in seen:  # anúncios
            continue
        seen.add(url)
        out.append((html.unescape(re.sub(r"<[^>]+>", "", title)).strip(), url))
        if len(out) >= limit:
            break
    return out


def web_links(query: str, limit: int = 5, post=None) -> str:
    import httpx

    post = post or (lambda data: httpx.post("https://html.duckduckgo.com/html/", data=data, timeout=12,
                                            headers={"User-Agent": _BROWSER_UA}, follow_redirects=True).text)
    try:
        results = parse_results(post({"q": query, "kl": "pt-pt"}), limit)
    except Exception as exc:
        return f"Não consegui pesquisar \"{query}\" ({type(exc).__name__})."
    if not results:
        return f"Não encontrei resultados para \"{query}\"."
    lines = [f"Encontrei isto para \"{query}\":"]
    lines += [f"{i}. {title}\n{url}" for i, (title, url) in enumerate(results, 1)]
    return "\n".join(lines)


def _clean_image_query(query: str) -> str:
    query = re.sub(r"^(?:uma?\s+|umas?\s+|uns\s+|o\s+|a\s+|os\s+|as\s+)", "", query.strip(), flags=re.I)
    return query.strip(" .?!")


def find_image(query: str, get=None, folder=None) -> str:
    """Procura uma foto (Openverse: fotos livres do Flickr, Wikimedia...), guarda-a e devolve o caminho."""
    import httpx

    query = _clean_image_query(query)
    folder = folder or IMAGES_DIR
    headers = {"User-Agent": "JarvisPC/1.0 (assistente pessoal)"}
    get = get or (lambda url, params=None: httpx.get(url, params=params, headers=headers, timeout=15,
                                                     follow_redirects=True))
    try:
        found = get("https://api.openverse.org/v1/images/",
                    params={"q": query, "page_size": 8, "mature": "false"}).json().get("results", [])
    except Exception as exc:
        return f"Não consegui procurar fotos de \"{query}\" ({type(exc).__name__})."
    for item in found:
        try:
            image = get(item["url"])
        except Exception:
            continue
        kind = image.headers.get("content-type", "")
        if image.status_code != 200 or not kind.startswith("image/") or len(image.content) < 5000:
            continue
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(kind.split(";")[0], ".jpg")
        folder.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^\w-]+", "_", query)[:40] or "foto"
        path = folder / f"{name}_{time.strftime('%Y-%m-%d_%H-%M-%S')}{ext}"
        path.write_bytes(image.content)
        _show(path)
        title = item.get("title") or query
        return f"Aqui está uma foto de {query} (\"{title}\").\n📎 {path}"
    return f"Não encontrei nenhuma foto de \"{query}\"."


def _show(path):
    import os

    try:
        os.startfile(path)  # type: ignore[attr-defined]  # abre no visualizador de fotos do PC
    except OSError:
        pass


# "mostra-me uma foto de um audi", "manda-me imagens do Ferrari F40"
IMAGE_REQUEST = re.compile(
    r"^\W*(?:(?:jarvis|podes|consegues)\W+)*(?:me\s+)?(?:mostrar?|mandar?|enviar?|arranjar?|d[aá]|dar)(?:[- ]?me)?\s+(?:uma?s?\s+|umas\s+)?"
    r"(?:foto(?:grafia)?s?|imagens?|pics?)\s+(?:de|do|da|dos|das|dum|duma)\s+(?P<q>.+?)\W*$"
    r"|^\W*(?:(?:jarvis|podes|consegues)\W+)*(?:quero\s+ver|procura)\s+(?:uma?s?\s+)?(?:foto(?:grafia)?s?|imagens?)\s+"
    r"(?:de|do|da|dos|das|dum|duma)\s+(?P<q2>.+?)\W*$",
    re.IGNORECASE,
)
# "mostra-me carros da Alpina à venda", "dá-me links sobre X", "pesquisa no google X"
LINKS_REQUEST = re.compile(
    r"^\W*(?:(?:jarvis|podes|consegues)\W+)*(?:me\s+)?(?:mostrar?|arranjar?|d[aá]|dar|encontrar?|procurar?)(?:[- ]?me)?\s+"
    r"(?P<q>.+?\s+(?:[àa]|para|pra)\s+venda.*?)\W*$"
    r"|\b(?:links?|sites?)\s+(?:de|do|da|sobre|para|com|onde)\s+(?P<q2>.+?)\W*$"
    r"|^\W*(?:(?:jarvis|podes|consegues)\W+)*(?:pesquisa|procura)\s+(?:no\s+google|na\s+net|na\s+internet)\s+"
    r"(?:por\s+|sobre\s+)?(?P<q3>.+?)\W*$",
    re.IGNORECASE,
)


def parse_image_request(text: str) -> str | None:
    m = IMAGE_REQUEST.search(text)
    return (m.group("q") or m.group("q2")) if m else None


def parse_links_request(text: str) -> str | None:
    m = LINKS_REQUEST.search(text)
    if not m:
        return None
    query = m.group("q") or m.group("q2") or m.group("q3")
    return re.sub(r"^(?:uns|umas|os|as|o|a)\s+", "", query.strip(), flags=re.IGNORECASE)
