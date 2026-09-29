"""Controlo do Jarvis por Telegram.

Segurança:
- Só aceita mensagens de IDs de utilizador na lista JARVIS_TELEGRAM_ALLOWED_IDS (.env).
  Mensagens de qualquer outra pessoa são ignoradas (nem têm resposta) e ficam no registo.
- Antes de ações sensíveis (ferramentas em SENSITIVE_TOOLS: lançar o Claude Code a mexer em
  código, e no futuro apagar ficheiros, git push, comandos de terminal) pede confirmação no
  chat com botões ✅/❌; sem resposta em 2 minutos, não faz.
"""

import queue
import re
import secrets
import threading
import time
from collections.abc import Callable

import httpx

from jarvis.log import log

API = "https://api.telegram.org/bot{token}/{method}"

# Pedidos mais antigos do que isto (enviados com o Jarvis desligado) não são executados.
STALE_SECONDS = 120

# Ferramentas que precisam de confirmação quando o pedido vem pelo Telegram.
SENSITIVE_TOOLS = {"continue_work", "open_project", "delete_file", "git_push", "run_command"}


def is_sensitive(name: str, args: dict) -> bool:
    if name == "open_project":
        return bool(str(args.get("claude_prompt") or "").strip())  # só se lançar o Claude Code
    return name in SENSITIVE_TOOLS


class TelegramAPI:
    def __init__(self, token: str):
        self.token = token
        self.http = httpx.Client(timeout=40)

    def call(self, method: str, **params) -> dict | list:
        response = self.http.post(API.format(token=self.token, method=method), json=params)
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data.get('description', response.status_code)}")
        return data["result"]

    def send_file(self, chat: int, path, caption: str = ""):
        """Imagens como foto (se o Telegram aceitar), o resto como ficheiro."""
        from pathlib import Path

        path = Path(path)
        is_image = path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        attempts = [("sendPhoto", "photo")] if is_image and path.stat().st_size < 10_000_000 else []
        attempts.append(("sendDocument", "document"))
        error = None
        for method, field in attempts:
            with path.open("rb") as f:
                response = self.http.post(API.format(token=self.token, method=method),
                                          data={"chat_id": chat, "caption": caption[:1000]},
                                          files={field: (path.name, f)}, timeout=120)
            data = response.json()
            if data.get("ok"):
                return data["result"]
            error = data.get("description")  # ex.: foto grande demais -> tenta como ficheiro
        raise RuntimeError(f"Telegram: não consegui enviar {path.name}: {error}")


    def send_photo_bytes(self, chat: int, data: bytes, caption: str = "") -> dict:
        response = self.http.post(API.format(token=self.token, method="sendPhoto"),
                                  data={"chat_id": chat, "caption": caption},
                                  files={"photo": ("ecra.jpg", data, "image/jpeg")}, timeout=60)
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description"))
        return result["result"]

    def edit_photo_bytes(self, chat: int, message_id: int, data: bytes, caption: str = "") -> dict:
        import json

        media = {"type": "photo", "media": "attach://ecra", "caption": caption}
        response = self.http.post(API.format(token=self.token, method="editMessageMedia"),
                                  data={"chat_id": chat, "message_id": message_id, "media": json.dumps(media)},
                                  files={"ecra": ("ecra.jpg", data, "image/jpeg")}, timeout=60)
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description"))
        return result["result"]


    def download(self, file_id: str) -> tuple[bytes, str]:
        """Ficheiro que mandaste ao bot -> (bytes, caminho no Telegram)."""
        info = self.call("getFile", file_id=file_id)
        url = f"https://api.telegram.org/file/bot{self.token}/{info['file_path']}"
        return self.http.get(url, timeout=60).content, info["file_path"]


MEME_LINK = re.compile(r"https?://(?:www\.)?(?:tenor\.com|giphy\.com|media\d*\.giphy\.com|media\d*\.tenor\.com|"
                       r"i\.imgur\.com|imgur\.com)/\S+", re.IGNORECASE)
LIVE_SECONDS = 60
LIVE_REQUEST = re.compile(
    r"(?:ecr[aã]|tela|pc|computador).*(?:ao\s+vivo|em\s+direto|tempo\s+real|\blive\b)|"
    r"(?:ao\s+vivo|em\s+direto|tempo\s+real|\blive\b).*(?:ecr[aã]|tela|pc|computador)",
    re.IGNORECASE,
)


def grab_screen_jpeg(width: int = 1280, quality: int = 60) -> bytes:
    """Print do ecrã principal em JPEG pequeno (rápido de enviar)."""
    import io

    import mss
    from PIL import Image

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    if img.width > width:
        img = img.resize((width, int(img.height * width / img.width)))
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def parse_allowed_ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(";", ",").split(",") if x.strip().lstrip("-").isdigit()}


class TelegramBot:
    """Lê mensagens (long polling) e entrega os pedidos dos utilizadores autorizados a `handle`.

    Os pedidos correm um de cada vez numa thread à parte, para o bot continuar a receber as
    respostas aos botões de confirmação enquanto um pedido está a correr.
    """

    def __init__(self, api, allowed_ids: set[int], handle: Callable[[str, int], str]):
        self.api = api
        self.allowed_ids = allowed_ids
        self.handle = handle
        self.offset = 0
        self.jobs: queue.Queue = queue.Queue()
        self._pending: dict[str, dict] = {}  # confirmações à espera de resposta
        self.stop = threading.Event()
        self.live_stop = threading.Event()  # /parar acaba o ecrã ao vivo

    # --- receber -------------------------------------------------------------

    def poll_once(self, timeout: int = 30):
        updates = self.api.call("getUpdates", offset=self.offset, timeout=timeout,
                                allowed_updates=["message", "callback_query"])
        for update in updates:
            self.offset = update["update_id"] + 1
            if "callback_query" in update:
                self._on_callback(update["callback_query"])
            elif "message" in update:
                self._on_message(update["message"])

    def _on_message(self, message: dict):
        user = (message.get("from") or {}).get("id")
        chat = (message.get("chat") or {}).get("id")
        text = (message.get("text") or "").strip()
        if user not in self.allowed_ids:
            log.warning("Telegram: mensagem ignorada de um utilizador não autorizado (%s)", user)
            return
        media = message.get("animation") or message.get("document") or \
            (message["photo"][-1] if message.get("photo") else None)
        if media or MEME_LINK.search(text):
            threading.Thread(target=self.save_meme, args=(chat, message, media), daemon=True).start()
            return
        if not text:
            self.send(chat, "Por agora só percebo mensagens de texto, fotos e GIFs.")
            return
        if time.time() - message.get("date", time.time()) > STALE_SECONDS:
            # Chegou enquanto o Jarvis estava desligado: não executar pedidos antigos de repente.
            log.info("Telegram: pedido antigo ignorado: %r", text)
            self.send(chat, f"Recebi \"{text[:60]}\" quando estava desligado, por isso não fiz nada. "
                            "Se ainda quiseres, manda outra vez.")
            return
        if text in ("/start", "/help", "/ajuda"):
            from jarvis.help import HELP_TEXT

            self.send(chat, HELP_TEXT)
            return
        if text in ("/reiniciar", "/restart"):
            from jarvis import updates

            if message.get("date", 0) <= updates.STARTED:
                # Pedido anterior a este arranque: já foi cumprido (é por causa dele que estamos aqui).
                return
            self.send(chat, "🔄 A reiniciar o Jarvis com a versão mais recente… Dá-me uns segundos.")
            # Confirma ao Telegram que este /reiniciar já foi lido; senão o Jarvis novo recebia-o
            # outra vez e reiniciava em ciclo.
            self.api.call("getUpdates", offset=self.offset, timeout=0)
            updates.restart()
            return
        if text.lower() in ("/parar", "/stop", "para o ecrã", "para o ecra", "parar"):
            self.live_stop.set()
            if text.startswith("/"):
                return
        if text.lower() in ("/aovivo", "/ecra", "/ecrã") or LIVE_REQUEST.search(text):
            self.live_stop.clear()
            threading.Thread(target=self.live_screen, args=(chat,), daemon=True, name="ecra-ao-vivo").start()
            return
        self.jobs.put((text, chat))

    # --- memes que mandas ao bot ---------------------------------------------------

    def save_meme(self, chat: int, message: dict, media: dict | None):
        """Fotos, GIFs e links do Tenor/Giphy -> Ambiente de Trabalho\\Jarvis\\Meus memes."""
        from jarvis import memes

        caption = (message.get("caption") or "").strip()
        try:
            if media:
                name = caption or media.get("file_name", "").rsplit(".", 1)[0] or ""
                mime = media.get("mime_type", "image/jpeg")
                if not (mime.startswith("image/") or mime.startswith("video/")):
                    self.send(chat, "Esse ficheiro não é uma imagem nem um GIF: não o guardei.")
                    return
                data, file_path = self.api.download(media["file_id"])
                ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ".jpg"
                path = memes.save_meme(data, name or f"meme {time.strftime('%d-%m %H-%M-%S')}", ext)
            else:
                url = MEME_LINK.search(message.get("text", "")).group(0)
                name = MEME_LINK.sub("", message.get("text", "")).strip()
                path = memes.save_from_link(url, name)
        except Exception as exc:
            self.send(chat, f"Não consegui guardar esse meme: {exc}")
            return
        self.send(chat, f"😂 Guardei o meme \"{path.stem}\". Diz \"mete o meme {path.stem} na tela\" para o pôr no ecrã. "
                        "(Se escreveres uma legenda na foto, fica com esse nome.)")

    # --- ecrã ao vivo ----------------------------------------------------------

    def live_screen(self, chat: int, seconds: float = LIVE_SECONDS, interval: float = 2.0, grab=None):
        """Manda uma foto do ecrã e vai-a atualizando (quase como um vídeo) durante `seconds`."""
        grab = grab or grab_screen_jpeg
        try:
            first = self.api.send_photo_bytes(chat, grab(), f"🔴 Ecrã ao vivo ({int(seconds)} s). /parar para acabar.")
        except Exception as exc:
            self.send(chat, f"Não consegui mostrar o ecrã: {exc}")
            return
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self.live_stop.wait(interval):
            try:
                left = int(end - time.monotonic())
                self.api.edit_photo_bytes(chat, first["message_id"], grab(),
                                          f"🔴 Ecrã ao vivo ({left} s). /parar para acabar.")
            except Exception as exc:  # ex.: imagem igual à anterior ("message is not modified")
                log.debug("ecrã ao vivo: %s", exc)
        try:
            self.api.call("editMessageCaption", chat_id=chat, message_id=first["message_id"],
                          caption="⏹ Fim do ecrã ao vivo. Manda /aovivo para ver outra vez.")
        except Exception:
            pass

    def _on_callback(self, callback: dict):
        user = (callback.get("from") or {}).get("id")
        data = callback.get("data") or ""
        answer, _, key = data.partition(":")
        pending = self._pending.get(key)
        if user in self.allowed_ids and pending is not None:
            pending["ok"] = answer == "ok"
            pending["event"].set()
        try:
            self.api.call("answerCallbackQuery", callback_query_id=callback["id"])
        except Exception:
            pass

    # --- enviar / confirmar --------------------------------------------------

    def send(self, chat: int, text: str, **extra):
        return self.api.call("sendMessage", chat_id=chat, text=text[:4000], **extra)

    def confirm(self, chat: int, question: str, timeout: float = 120) -> bool:
        key = secrets.token_hex(4)
        pending = {"event": threading.Event(), "ok": False}
        self._pending[key] = pending
        self.send(chat, f"⚠️ {question}", reply_markup={"inline_keyboard": [[
            {"text": "✅ Sim", "callback_data": f"ok:{key}"},
            {"text": "❌ Não", "callback_data": f"no:{key}"},
        ]]})
        answered = pending["event"].wait(timeout)
        self._pending.pop(key, None)
        if not answered:
            self.send(chat, "Sem resposta: não fiz nada.")
        return answered and pending["ok"]

    # --- ciclo ---------------------------------------------------------------

    def _worker(self):
        while not self.stop.is_set():
            try:
                text, chat = self.jobs.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.api.call("sendChatAction", chat_id=chat, action="typing")
                reply = self.handle(text, chat)
            except Exception as exc:
                log.exception("Telegram: erro a tratar %r", text)
                reply = f"Erro: {exc}"
            from jarvis import updates

            if updates.newer_code_available():
                reply += "\n\n" + updates.NOTICE
            self.send(chat, reply)

    def run(self):
        threading.Thread(target=self._worker, daemon=True, name="telegram-worker").start()
        while not self.stop.is_set():
            try:
                self.poll_once()
            except httpx.HTTPError as exc:
                log.warning("Telegram sem ligação: %s", exc)
                self.stop.wait(5)
            except Exception as exc:
                log.warning("Telegram: %s", exc)
                self.stop.wait(5)
