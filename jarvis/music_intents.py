"""Pedidos de música que o Jarvis percebe sem o modelo (o modelo local às vezes falhava):

- "mete/põe/toca/coloca uma música do Bad Bunny"  -> tocar "Bad Bunny"
- "mete outra música", "troca de música", "salta"  -> seguinte
- "mete uma música parecida", "do mesmo género", "que música tem vibes iguais?"
  -> vê o que está a tocar no Spotify e procura músicas parecidas
"""

import re

_PLAY_VERB = r"(?:mete|meter|mete-me|p[oõ]e|p[oô]r|p[oõ]e-me|toca|tocar|toca-me|coloca|colocar|bota|reproduz)"
_LEAD = r"^\W*(?:(?:jarvis|podes|consegues|por\s+favor|ent[aã]o|ent|e|agora)\W+)*"

SIMILAR = re.compile(
    r"parecid[ao]s?|mesmo\s+(?:g[eé]nero|estilo|tipo|vibe)|vibes?\s+(?:igua(?:l|is)|parecidas?|semelhantes?)|"
    r"semelhantes?|do\s+g[eé]nero\s+desta|como\s+esta\b",
    re.IGNORECASE,
)
_MUSIC = re.compile(r"m[uú]sicas?|som\b|sons\b|can[cç](?:[aã]o|[õo]es)|spotify|vibes?", re.IGNORECASE)
_WANTS_PLAY = re.compile(_LEAD + _PLAY_VERB + r"\b", re.IGNORECASE)

NEXT = re.compile(
    _LEAD + r"(?:(?:mete|p[oõ]e|toca|coloca)\s+(?:a\s+)?(?:outra|pr[oó]xima|seguinte)(?:\s+m[uú]sica)?|"
    r"(?:troca|trocar|muda|mudar)\s+(?:de\s+|a\s+)?m[uú]sica|"
    r"(?:passa|passar|salta|saltar|skip|skipa|skipar)(?:\s+(?:[aà]|a|para\s+a)\s+(?:pr[oó]xima|seguinte)|\s+(?:a\s+|esta\s+)?m[uú]sica|\s+esta)?|"
    r"pr[oó]xima(?:\s+m[uú]sica)?|next)\W*$",
    re.IGNORECASE,
)

PLAY = re.compile(
    _LEAD + _PLAY_VERB + r"\s+(?:(?:uma|umas|um|uns|a|o|as|os)\s+)?"
    r"(?:m[uú]sicas?|som|sons|can[cç](?:[aã]o|[õo]es)|cena)\s+(?:d[oa]s?|de)\s+(?P<q>.+?)"
    r"(?:\s+(?:no|na)\s+spotify)?\W*$"
    r"|" + _LEAD + _PLAY_VERB + r"\s+(?P<q2>.+?)\s+(?:no|na)\s+spotify\W*$",
    re.IGNORECASE,
)


# "Bad Bunny a tocar", "Bad Bunny para ouvir agora por favor" -> "Bad Bunny"
_TRAILING = re.compile(r"(?:\s+(?:a\s+tocar|para\s+(?:ouvir|tocar)|agora|j[aá]|por\s+favor|pf|pff|se\s+faz\s+favor))+\W*$",
                       re.IGNORECASE)


def parse_music(text: str) -> tuple[str, str] | None:
    """-> ("next", "") | ("similar", "play"|"suggest") | ("play", consulta) | None."""
    if NEXT.match(text) and not SIMILAR.search(text):
        return "next", ""
    if SIMILAR.search(text) and _MUSIC.search(text):
        return "similar", "play" if _WANTS_PLAY.match(text) else "suggest"
    m = PLAY.match(text)
    if m:
        query = _TRAILING.sub("", (m.group("q") or m.group("q2") or "").strip())
        if query and not SIMILAR.search(query):
            return "play", query
    return None


SIMILAR_SYSTEM = (
    "És um especialista em música. Respondes APENAS com 3 linhas, cada uma no formato "
    "Título - Artista, sem números, sem aspas e sem mais texto."
)


def parse_suggestions(text: str, playing: str = "") -> list[tuple[str, str]]:
    """'After the Rain - Zedd\\n2. Stay - The Kid LAROI' -> [(título, artista)], sem a que está a tocar."""
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\W*\d+[.)]\s*", "", line).strip().strip("\"“”*- ")
        if " - " not in line:
            continue
        title, artist = (part.strip().strip("\"“”*") for part in line.split(" - ", 1))
        if title and artist and title.lower() not in playing.lower():
            out.append((title, artist))
    return out[:3]
