"""Respostas curtas a uma oferta do Jarvis: "sim", "quero", "abre elas", "abre o LinkedIn", "2".

O modelo local só vê as últimas mensagens, e "abre elas" sozinho não diz nada. Por isso o
Jarvis guarda o que acabou de oferecer (ex.: depois de ver as mensagens novas: abrir o WhatsApp,
o Discord, o LinkedIn...) e trata ele próprio a resposta seguinte.
"""

import re
import unicodedata

from jarvis.llm import ToolCall

Option = tuple[str, ToolCall]  # (nome a mostrar, o que fazer)

_SOCIAL_URLS = {
    "instagram": "https://www.instagram.com/direct/inbox/",
    "tiktok": "https://www.tiktok.com/messages",
    "linkedin": "https://www.linkedin.com/messaging/",
}


def message_followups(summary: str) -> list[Option]:
    """Resultado do check_messages -> o que se pode abrir a seguir (só onde há mensagens)."""
    options: list[Option] = []
    lines = summary.splitlines()
    for i, line in enumerate(lines):
        low = line.lower()
        if low.startswith("whatsapp (") and "por ler" in low:
            options.append(("WhatsApp", ToolCall("open_app", {"name": "WhatsApp"})))
        elif low.startswith("discord:"):
            block = "\n".join(lines[i + 1:i + 5]).lower()
            if "amigos:" in block or "grupos:" in block or "pedido" in block:
                options.append(("Discord", ToolCall("open_app", {"name": "Discord"})))
        else:
            for key, url in _SOCIAL_URLS.items():
                if low.startswith(key + ": tens"):
                    options.append((line.split(":", 1)[0], ToolCall("open_website", {"url": url})))
    return options


# "Queres que abra o Spotify?", "Queres que eu abra a conversa no WhatsApp?"
_OFFER_OPEN = re.compile(
    r"queres\s+que\s+(?:eu\s+)?(?:te\s+)?abra\s+(?:o\s+|a\s+)?(?P<what>[^?.,!\n]{2,40})\?", re.IGNORECASE)


# "After the Rain" de Zedd feat. Alessia Cara  /  “Blinding Lights” dos The Weeknd
_QUOTED_TITLE = re.compile(
    r"[\"“«](?P<title>[^\"”»\n]{2,60})[\"”»](?:\s*,?\s*(?:de|dos|das|do|da|by|por)\s+(?P<artist>[A-Z0-9À-Ý][^,.;:!?\n\"“«]{1,50}))?")
_MUSIC_WORDS = re.compile(r"m[uú]sica|can[cç][aã]o|can[cç][õo]es|playlist|ouvir|tocar|spotify|[aá]lbum|artista|som\b",
                          re.IGNORECASE)
_VIDEO_WORDS = re.compile(r"v[ií]deo|youtube|tiktok|ver\b", re.IGNORECASE)


def titles_from_reply(reply: str, request: str = "") -> list[Option]:
    """Músicas/vídeos que o Jarvis sugeriu entre aspas -> opções para "mete uma dessas"."""
    context = reply + " " + request
    if _MUSIC_WORDS.search(context):
        make = lambda q: ToolCall("music", {"action": "play", "query": q})  # noqa: E731
    elif _VIDEO_WORDS.search(context):
        make = lambda q: ToolCall("play_video", {"query": q})  # noqa: E731
    else:
        return []
    options, seen = [], set()
    for m in _QUOTED_TITLE.finditer(reply):
        title = m.group("title").strip()
        # O que o utilizador já estava a ouvir ("vibes semelhantes a 'Free'") não é sugestão.
        before = reply[max(0, m.start() - 25):m.start()].lower()
        if title.lower() in seen or re.search(r"(?:semelhantes?|parecid[oa]s?|igua(?:l|is)|como)\s+(?:a|à|ao)?\s*$", before):
            continue
        seen.add(title.lower())
        artist = (m.group("artist") or "").strip()
        artist = re.split(r"\s+(?:feat\.?|ft\.?|com|e)(?:\s+|$)", artist)[0] if artist else ""
        options.append((title, make(f"{title} {artist}".strip())))
    return options


def offer_from_reply(reply: str, request: str = "") -> list[Option]:
    m = _OFFER_OPEN.search(reply)
    if not m:
        return titles_from_reply(reply, request)
    what = re.sub(r"^(?:conversa|app|aplica[cç][aã]o)\s+(?:d[oa]\s+|n[oa]\s+)?", "", m.group("what").strip(),
                  flags=re.IGNORECASE)
    site = next((url for key, url in _SOCIAL_URLS.items() if key in _fold(what).replace(" ", "")), None)
    if site:
        return [(what, ToolCall("open_website", {"url": site}))]
    return [(what, ToolCall("open_app", {"name": what}))]


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


_YES = re.compile(r"^\W*(?:sim|s|quero|ok|okay|claro|pode ser|podes|bora|yes|isso|abre|abrir|abra|mostra|mostra-me)"
                  r"(?:\s+(?:sim|por favor|jarvis))*\W*$")
_OPEN_WORDS = {"sim", "quero", "ok", "claro", "pode", "ser", "podes", "bora", "abre", "abrir", "abra", "mostra",
               "me", "mostrame", "por", "favor", "jarvis", "as", "os", "a", "o", "elas", "eles", "isso", "essa",
               "esse", "essas", "esses", "app", "apps", "aplicacao", "conversa", "conversas", "mensagens",
               "mensagem", "tudo", "todas", "todos", "ai", "la", "entao", "ent", "no", "na", "e", "s", "yes",
               "mete", "poe", "toca", "tocar", "por", "coloca", "essa", "uma", "um", "dessas", "desses", "destas",
               "delas", "deles", "ouvir", "musica", "video", "ver", "qualquer", "vai", "manda", "ja"}
_ALL = {"tudo", "todas", "todos", "elas", "eles", "essas", "esses"}
_ORDINAL = {"primeira": 1, "primeiro": 1, "segunda": 2, "segundo": 2, "terceira": 3, "terceiro": 3,
            "quarta": 4, "quarto": 4, "quinta": 5, "quinto": 5}


def match(text: str, options: list[Option]) -> tuple[str, list[ToolCall]] | None:
    """-> ("run", [chamadas]) | ("ask", pergunta) | None (não é resposta à oferta)."""
    if not options:
        return None
    words = re.findall(r"[a-z0-9]+", _fold(text))
    if not words or len(words) > 8:
        return None
    # Pelo nome: "abre o LinkedIn", "o whatsapp"
    named = [call for label, call in options if _fold(label).replace(" ", "") in "".join(words)
             or any(w == _fold(label).split()[0] for w in words)]
    if named:
        return "run", named
    # Pelo número: "2", "a segunda"
    number = next((int(w) for w in words if w.isdigit()), None) or next((_ORDINAL[w] for w in words if w in _ORDINAL), None)
    if number and 1 <= number <= len(options):
        return "run", [options[number - 1][1]]
    if not all(w in _OPEN_WORDS for w in words):
        return None  # é outro pedido
    if {"uma", "um", "qualquer", "essa", "esse"} & set(words) and not _ALL & set(words) - {"elas", "eles"}:
        return "run", [options[0][1]]  # "mete uma dessas", "põe essa": a primeira sugerida
    if len(options) == 1 or any(w in _ALL for w in words):
        return "run", [call for _, call in options]
    lines = [f"{i}. {label}" for i, (label, _) in enumerate(options, 1)]
    return "ask", "Qual queres abrir? " + ", ".join(lines) + " (ou \"todas\")."
