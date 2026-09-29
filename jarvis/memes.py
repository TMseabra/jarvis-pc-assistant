"""Memes no ecrã do PC: "mete um meme na tela do PC" -> 5 memes para escolher -> o escolhido
aparece em grande no ecrã. Também "dá um jumpscare na tela do PC" (cara assustadora + grito).

Os memes vêm do Reddit através de meme-api.com (sem chave); os NSFW e com spoiler são ignorados.
No Telegram recebes as imagens para escolher; no PC, a lista com os títulos.
"""

import re
import time

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
    """Guarda os memes mostrados, à espera que o utilizador escolha um."""

    def __init__(self, fetcher=fetch, show=overlay.show_image):
        self.fetcher = fetcher
        self.show = show
        self.options: list[tuple[str, object]] = []

    @property
    def waiting(self) -> bool:
        return bool(self.options)

    def cancel(self):
        self.options = []

    def start(self) -> str:
        try:
            self.options = self.fetcher()
        except Exception as exc:
            return f"Não consegui ir buscar memes ({type(exc).__name__})."
        if not self.options:
            return "Não encontrei memes agora. Tenta daqui a bocado."
        lines = ["Escolhe um meme para pôr no ecrã do PC:"]
        for i, (title, path) in enumerate(self.options, 1):
            lines.append(f"{i}. {title[:80]}")
        lines.append("Diz o número (ou \"outros\" para ver mais).")
        lines += [f"📎 {path}" for _, path in self.options]
        return "\n".join(lines)

    def choose(self, text: str) -> str:
        words = text.strip().lower()
        if re.search(r"\b(?:outros?|outras?|mais|novos?)\b", words):
            return self.start()
        m = re.search(r"\d+", words)
        ordinals = {"primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5}
        index = int(m.group()) if m else next((n for w, n in ordinals.items() if w in words), None)
        if not index or not 1 <= index <= len(self.options):
            return f"Diz um número de 1 a {len(self.options)} (ou \"cancela\")."
        title, path = self.options[index - 1]
        self.cancel()
        self.show(path)
        return f"Pus o meme \"{title[:60]}\" no ecrã do PC."


def jumpscare() -> str:
    overlay.jumpscare()
    return "👻 Jumpscare no ecrã do PC (com grito)!"


_SCREEN = r"(?:n[oa]|para\s+[oa]|em)\s+(?:tela|ecr[aã]|monitor|pc|computador)"
MEME_REQUEST = re.compile(rf"\bmemes?\b.*{_SCREEN}|{_SCREEN}.*\bmemes?\b|^\W*(?:mostra|mete|p[oõ]e|manda)(?:-me)?\s+(?:um\s+)?memes?\W*$",
                          re.IGNORECASE)
JUMPSCARE_REQUEST = re.compile(r"jump\s*-?\s*scare|jumsacre|jumscare|susto\s+" + _SCREEN + r"|assusta", re.IGNORECASE)
