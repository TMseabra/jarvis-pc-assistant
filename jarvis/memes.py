r"""Memes no ecrã do PC: "mete um meme na tela do PC" -> os teus memes (Ambiente de Trabalho\Jarvis\
Meus memes) ou 5 da net para escolher -> o escolhido aparece em grande no ecrã. Fotos, GIFs e links
do Tenor/Giphy que mandes ao bot do Telegram ficam guardados como teus memes. Também "dá um jumpscare na tela do PC" (cara assustadora + grito).

Os memes vêm do Reddit através de meme-api.com (sem chave); os NSFW e com spoiler são ignorados.
No Telegram recebes as imagens para escolher; no PC, a lista com os títulos.
"""

import re
import time
import urllib.parse

from jarvis import outputs, overlay

API = "https://meme-api.com/gimme/{count}"


def fetch(count: int = 5, get=None, folder=None) -> list[tuple[str, object]]:
    """[(título, caminho)] de `count` memes descarregados para Ambiente de Trabalho\\Jarvis\\Memes."""
    import httpx

    headers = {"User-Agent": "JarvisPC/1.0 (assistente pessoal)"}
    get = get or (lambda url: httpx.get(url, headers=headers, timeout=15, follow_redirects=True))
    items = get(API.format(count=count * 2)).json().get("memes", [])
    folder = outputs.prepare(folder or outputs.folder("Memes"))
    out = []
    for item in items:
        if item.get("nsfw") or item.get("spoiler"):
            continue
        url = item.get("url", "")
        ext = url.rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
            continue
        try:
            image = get(url)
        except Exception:
            continue
        if image.status_code != 200 or len(image.content) < 3000:
            continue
        name = re.sub(r"[^\w-]+", "_", item.get("title", "meme"))[:40].strip("_") or "meme"
        path = folder / f"{time.strftime('%H-%M-%S')}_{len(out) + 1}_{name}.{ext}"
        path.write_bytes(image.content)
        out.append((item.get("title", "meme").strip(), path))
        if len(out) >= count:
            break
    return out


class MemeFlow:
    """Guarda os memes mostrados (os teus primeiro, depois os da net) à espera da escolha."""

    def __init__(self, fetcher=fetch, show=overlay.show_image, mine=None):
        self.fetcher = fetcher
        self.show = show
        self.mine = mine or my_memes
        self.options: list[tuple[str, object]] = []

    @property
    def waiting(self) -> bool:
        return bool(self.options)

    def cancel(self):
        self.options = []

    def _put(self, title, path) -> str:
        self.cancel()
        self.show(path)
        return f"Pus o meme \"{str(title)[:60]}\" no ecrã do PC."

    def start(self, request: str = "") -> str:
        mine = self.mine()
        named = find_mine(request, mine) if request else None
        if named:  # "mete o meme do macaco"
            return self._put(*named)
        if not mine or re.search(r"\b(?:net|internet|reddit|novos?)\b", request.lower()):
            return self._from_net()
        self.options = mine[:15]
        lines = ["Os teus memes:"] + [f"{i}. {name}" for i, (name, _) in enumerate(self.options, 1)]
        lines.append("Diz o número (ou \"da net\" para memes novos da internet).")
        return "\n".join(lines)

    def _from_net(self) -> str:
        try:
            self.options = self.fetcher()
        except Exception as exc:
            return f"Não consegui ir buscar memes ({type(exc).__name__})."
        if not self.options:
            return "Não encontrei memes agora. Tenta daqui a bocado."
        lines = ["Memes da net para pôr no ecrã do PC:"]
        lines += [f"{i}. {title[:80]}" for i, (title, _) in enumerate(self.options, 1)]
        lines.append("Diz o número (ou \"outros\" para ver mais).")
        lines += [f"📎 {path}" for _, path in self.options]
        return "\n".join(lines)

    def choose(self, text: str) -> str:
        words = text.strip().lower()
        if re.search(r"\b(?:outros?|outras?|mais|novos?|net|internet)\b", words):
            return self._from_net()
        m = re.search(r"\d+", words)
        ordinals = {"primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5}
        index = int(m.group()) if m else next((n for w, n in ordinals.items() if w in words), None)
        if index and 1 <= index <= len(self.options):
            return self._put(*self.options[index - 1])
        named = find_mine(text, self.options)
        if named:
            return self._put(*named)
        return f"Diz um número de 1 a {len(self.options)} (ou \"cancela\")."


# --- os teus memes (Ambiente de Trabalho\Jarvis\Meus memes) ---------------------------

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def my_folder():
    path = outputs.folder("Meus memes")  # nunca é limpa: são os teus
    path.mkdir(parents=True, exist_ok=True)
    return path


def my_memes(folder=None) -> list[tuple[str, object]]:
    """[(nome, caminho)] dos teus memes, os mais recentes primeiro."""
    folder = folder or my_folder()
    files = [f for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXTS] if folder.exists() else []
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return [(f.stem, f) for f in files]


def _safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\n]+', " ", name).strip()[:60] or f"meme {time.strftime('%d-%m %H-%M-%S')}"


def save_meme(data: bytes, name: str, ext: str, folder=None) -> object:
    folder = folder or my_folder()
    path = folder / f"{_safe_name(name)}{ext if ext.startswith('.') else '.' + ext}"
    n = 2
    while path.exists():
        path = folder / f"{_safe_name(name)} ({n}){path.suffix}"
        n += 1
    path.write_bytes(data)
    return path


def media_url_from_page(page: str) -> str | None:
    """Link de uma página do Tenor/Giphy/Imgur -> o GIF/imagem principal (og:image)."""
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', page) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', page)
    return m.group(1).replace("&amp;", "&") if m else None


def save_from_link(url: str, name: str = "", get=None, folder=None) -> object:
    """Guarda um meme a partir de um link (imagem direta ou página do Tenor/Giphy)."""
    import httpx

    get = get or (lambda u: httpx.get(u, headers={"User-Agent": _BROWSER_UA}, timeout=20, follow_redirects=True))
    response = get(url)
    kind = response.headers.get("content-type", "")
    if not kind.startswith("image/"):
        media = media_url_from_page(response.text)
        if not media:
            raise ValueError("Não encontrei nenhuma imagem nesse link.")
        response = get(media)
        kind = response.headers.get("content-type", "")
        url = media
    ext = "." + (kind.split("/")[-1].split(";")[0] if kind.startswith("image/") else url.rsplit(".", 1)[-1])
    ext = ".jpg" if ext == ".jpeg" else ext
    if not name:
        slug = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        name = slug.replace("-", " ") or "meme"
    return save_meme(response.content, name, ext, folder)


def find_mine(text: str, memes=None) -> tuple[str, object] | None:
    """'mete o meme do macaco' -> o teu meme cujo nome tem 'macaco'."""
    memes = my_memes() if memes is None else memes
    words = [w for w in re.findall(r"\w+", text.lower()) if len(w) > 2 and w not in _NOT_NAME]
    best, score = None, 0
    for name, path in memes:
        hits = sum(w in name.lower() for w in words)
        if hits > score:
            best, score = (name, path), hits
    return best


_NOT_NAME = {"mete", "meme", "memes", "tela", "ecra", "ecrã", "pc", "computador", "põe", "poe", "mostra", "manda",
             "adiciona", "the", "dos", "das", "com", "uma", "meu", "meus", "minha", "monitor", "para", "jarvis",
             "podes", "aquele", "aquela", "esse", "essa"}


def jumpscare() -> str:
    overlay.jumpscare()
    return "👻 Jumpscare no ecrã do PC (com grito)!"


_SCREEN = r"(?:n[oa]|para\s+[oa]|em)\s+(?:tela|ecr[aã]|monitor|pc|computador)"
MEME_REQUEST = re.compile(rf"\bmemes?\b.*{_SCREEN}|{_SCREEN}.*\bmemes?\b|^\W*(?:(?:jarvis|podes)\W+)*(?:mostra|mete|p[oõ]e|manda|adiciona)(?:-me)?\s+(?:(?:o|um|uns|aquele|a)\s+)?memes?\b",
                          re.IGNORECASE)
JUMPSCARE_REQUEST = re.compile(r"jump\s*-?\s*scare|jumsacre|jumscare|susto\s+" + _SCREEN + r"|assusta", re.IGNORECASE)
