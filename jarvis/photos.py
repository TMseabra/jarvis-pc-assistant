r"""Fotos que mandas ao bot do Telegram: o Jarvis vê-as, resume-as, explica-as e guarda tudo.

"Resume isto", "explica melhor", "o que diz aqui?", "traduz" (como legenda da foto, ou logo a
seguir em texto) -> um modelo de visão do Ollama (JARVIS_VISION_MODEL, por omissão qwen2.5vl:7b)
lê a imagem e responde. A foto e a resposta ficam guardadas em Ambiente de Trabalho\Jarvis\Fotos
recebidas (nunca são apagadas sozinhas), para poderes ver e procurar mais tarde.
"""

import re
import time

from jarvis import outputs
from jarvis.config import config
from jarvis.llm.base import LLMError

# Pedidos que querem que o Jarvis olhe para a foto (senão a foto é guardada como meme).
ANALYZE_REQUEST = re.compile(
    r"\b(?:resum\w*|explic\w*|descrev\w*|analis\w*|l[eê]\w*|traduz\w*|v[eê]\w*|olha\w*|"
    r"o\s+que\s+(?:[eé]|diz|está|esta|significa|tem)|que\s+(?:[eé]|diz)|diz-?me|conta-?me|"
    r"mais\s+(?:detalhe|pormenor)\w*|melhor|extrai|copia\s+o\s+texto|guarda\s+isto)\b",
    re.IGNORECASE,
)

SYSTEM = ("És o Jarvis, assistente pessoal. Respondes em português de Portugal, de forma clara e direta. "
          "Olha com atenção para a imagem (texto, tabelas, gráficos, pessoas, objetos) e faz o que o "
          "utilizador pede. Se for um documento ou texto, lê-o mesmo. Não inventes o que não se vê.")
DEFAULT_ASK = "Resume o que vês nesta imagem. Se tiver texto, lê o essencial."
FOLLOW_UP_SECONDS = 15 * 60


# Texto a seguir a uma foto: mais apertado, para "lê as mensagens" não ser confundido com a foto.
FOLLOW_UP_REQUEST = re.compile(
    r"\b(?:resum\w*|explic\w*|descrev\w*|analis\w*|traduz\w*|detalh\w*|pormenor\w*|extrai|melhor|"
    r"o\s+que\s+(?:[eé]|diz|significa)\s+(?:isto|isso|aqui)|"
    r"(?:l[eê]|v[eê]|olha|copia)\w*\s+(?:isto|isso|a\s+foto|a\s+imagem|o\s+print)|guarda\s+isto)\b",
    re.IGNORECASE,
)


def wants_analysis(text: str) -> bool:
    """Legenda de uma foto que pede para a ver/resumir/explicar."""
    return bool(ANALYZE_REQUEST.search(text or ""))


def wants_follow_up(text: str) -> bool:
    """Texto solto a seguir a uma foto ("faz um resumo disto", "explica melhor")."""
    return bool(FOLLOW_UP_REQUEST.search(text or ""))


def folder():
    path = outputs.folder("Fotos recebidas")  # nunca é limpa: são as tuas
    path.mkdir(parents=True, exist_ok=True)
    return path


def ask_vision(image: bytes, question: str, previous: str = "", client=None) -> str:
    """Pergunta ao modelo de visão (fotos sem texto: cenas, objetos); `previous` = resposta anterior."""
    messages = [{"role": "system", "content": SYSTEM}]
    if previous:
        messages += [{"role": "user", "content": "Olha para esta imagem.", "images": [image]},
                     {"role": "assistant", "content": previous},
                     {"role": "user", "content": question}]
    else:
        messages.append({"role": "user", "content": question or DEFAULT_ASK, "images": [image]})
    return _chat(config.vision_model, messages, client)


READ_PROMPT = ("Transcreve TODO o texto que aparece nesta imagem, tal e qual, pela ordem em que se lê, sem "
               "comentar nem resumir. Se a imagem não tiver texto legível, responde apenas: SEM TEXTO")
TEXT_SYSTEM = ("És o Jarvis, assistente pessoal. Respondes em português de Portugal, de forma clara e organizada. "
               "O utilizador mandou uma foto e o texto dela foi lido para ti (pode ter pequenas gralhas de leitura). "
               "Faz o que ele pede com esse texto: resumo, pontos importantes, explicação, tradução, correção, etc. "
               "Não inventes nada que não esteja no texto. Se não disser o que quer, faz um resumo curto e lista "
               "os pontos principais.")
MIN_TEXT = 40  # menos do que isto: é uma foto de uma cena, não de um documento


def _chat(model: str, messages: list, client=None, temperature: float = 0.3) -> str:
    import httpx
    import ollama

    client = client or ollama.Client(host=config.ollama_host)
    try:
        response = client.chat(model=model, messages=messages,
                               options={"temperature": temperature, "num_ctx": 8192}, keep_alive="10m")
    except ollama.ResponseError as exc:
        if exc.status_code == 404:
            raise LLMError(f"O modelo '{model}' não está instalado. Corre no PC: ollama pull {model}") from exc
        raise LLMError(f"Erro do Ollama: {exc.error}") from exc
    except (ConnectionError, httpx.HTTPError) as exc:
        raise LLMError("Não consegui ligar ao Ollama. Confirma que está a correr (ollama serve).") from exc
    return (response.message.content or "").strip()


def read_text(image: bytes, client=None) -> str:
    """O texto que está na foto (modelo de visão); "" se não tiver texto que se leia."""
    text = _chat(config.vision_model, [{"role": "user", "content": READ_PROMPT, "images": [image]}],
                 client, temperature=0.0)
    return "" if text.upper().startswith("SEM TEXTO") or len(text) < MIN_TEXT else text


def respond(text: str, question: str, previous: str = "", client=None) -> str:
    """Faz o que pediste com o texto da foto (modelo normal, melhor a resumir e explicar)."""
    messages = [{"role": "system", "content": TEXT_SYSTEM},
                {"role": "user", "content": f'Texto da foto:\n"""\n{text}\n"""'}]
    if previous:
        messages.append({"role": "assistant", "content": previous})
    messages.append({"role": "user", "content": question or DEFAULT_ASK})
    return _chat(config.ollama_model, messages, client)


def save(image: bytes, ext: str, question: str, answer: str, name: str = "", dest=None, text: str = ""):
    """Guarda a foto e, ao lado, um .txt com o pedido e a resposta. Devolve o caminho da foto."""
    dest = dest or folder()
    stamp = time.strftime("%Y-%m-%d %H-%M-%S")
    base = re.sub(r'[<>:"/\\|?*\n]+', " ", name).strip()[:40]
    stem = f"{stamp} {base}".strip()
    photo = dest / f"{stem}{ext if ext.startswith('.') else '.' + ext}"
    n = 2
    while photo.exists():
        photo = dest / f"{stem} ({n}){photo.suffix}"
        n += 1
    photo.write_bytes(image)
    read = f"Texto da foto:\n{text}\n\n" if text else ""
    photo.with_suffix(".txt").write_text(f"{read}Pedido: {question or DEFAULT_ASK}\n\n{answer}\n", encoding="utf-8")
    return photo


class PhotoMemory:
    """A última foto recebida (na memória), para "explica melhor" sem mandar a foto outra vez."""

    def __init__(self):
        self.image: bytes | None = None
        self.ext = ".jpg"
        self.answer = ""
        self.text: str | None = None  # texto lido da foto (None = ainda não lido; "" = sem texto)
        self.path = None
        self.when = 0.0

    def remember(self, image: bytes, ext: str):
        self.image, self.ext, self.answer, self.text, self.path, self.when = image, ext, "", None, None, time.time()

    @property
    def fresh(self) -> bool:
        return self.image is not None and time.time() - self.when < FOLLOW_UP_SECONDS

    def analyze(self, question: str, ask=ask_vision, read=read_text, answer_text=respond) -> str:
        """Lê o texto da foto (uma vez), faz o que pediste com ele e guarda tudo ao lado da foto."""
        if self.text is None:
            self.text = read(self.image)
        if self.text:  # documento/texto: o modelo normal resume e explica melhor do que o de visão
            answer = answer_text(self.text, question, self.answer)
        else:  # foto de uma cena: o modelo de visão responde diretamente
            answer = ask(self.image, question or DEFAULT_ASK, self.answer)
        if self.path is None:
            self.path = save(self.image, self.ext, question, answer, text=self.text)
        else:
            try:
                with self.path.with_suffix(".txt").open("a", encoding="utf-8") as f:
                    f.write(f"\n--- {question}\n{answer}\n")
            except OSError:
                pass
        self.answer = answer
        self.when = time.time()
        return answer
