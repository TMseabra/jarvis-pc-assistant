"""Controlo do Jarvis por Telegram.

Segurança:
- Só aceita mensagens de IDs de utilizador na lista JARVIS_TELEGRAM_ALLOWED_IDS (.env).
  Mensagens de qualquer outra pessoa são ignoradas (nem têm resposta) e ficam no registo.
- Antes de ações sensíveis (ferramentas em SENSITIVE_TOOLS: lançar o Claude Code a mexer em
  código, e no futuro apagar ficheiros, git push, comandos de terminal) pede confirmação no
  chat com botões ✅/❌; sem resposta em 2 minutos, não faz.
"""

import queue
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
        if not text:
            self.send(chat, "Por agora só percebo mensagens de texto.")
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

            self.send(chat, "🔄 A reiniciar o Jarvis com a versão mais recente… Dá-me uns segundos.")
            updates.restart()
            return
        self.jobs.put((text, chat))

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
