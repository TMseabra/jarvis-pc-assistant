"""Bot do Telegram com uma API falsa (sem rede)."""

import threading
import time

from jarvis import remote
from jarvis.llm import ChatProvider, StepResult, ToolCall, ToolResult
from jarvis.telegram_bot import TelegramBot, is_sensitive, parse_allowed_ids
from jarvis.telegram_setup import write_env
from jarvis.tools import TOOL_SPECS

ME, STRANGER = 111, 999


class FakeAPI:
    def __init__(self):
        self.sent, self.updates, self.next_id = [], [], 1

    def push(self, kind, payload):
        self.updates.append({"update_id": self.next_id, kind: payload})
        self.next_id += 1

    def call(self, method, **params):
        if method == "getUpdates":
            out, self.updates = self.updates, []
            return out
        if method == "sendMessage":
            self.sent.append(params)
        return {}


def message(user, text, age=0):
    import time
    return {"from": {"id": user}, "chat": {"id": user}, "text": text, "date": int(time.time() - age)}


def test_parse_allowed_ids():
    assert parse_allowed_ids("111, 222;-100") == {111, 222, -100}
    assert parse_allowed_ids("") == set()


def test_only_allowed_users_are_handled():
    api = FakeAPI()
    handled = []
    bot = TelegramBot(api, {ME}, lambda text, chat: handled.append(text) or "ok")
    api.push("message", message(STRANGER, "apaga tudo"))
    api.push("message", message(ME, "abre o Spotify"))
    bot.poll_once()
    assert list(bot.jobs.queue) == [("abre o Spotify", ME)]
    assert api.sent == []  # ao estranho nem se responde


def test_confirmation_with_buttons():
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("ok", bot.confirm(ME, "Confirmas?", timeout=5)))
    thread.start()
    for _ in range(50):
        if api.sent:
            break
        time.sleep(0.02)
    buttons = api.sent[-1]["reply_markup"]["inline_keyboard"][0]
    # Um estranho a carregar no botão não conta.
    api.push("callback_query", {"id": "a", "from": {"id": STRANGER}, "data": buttons[0]["callback_data"]})
    api.push("callback_query", {"id": "b", "from": {"id": ME}, "data": buttons[0]["callback_data"]})
    bot.poll_once()
    thread.join(timeout=5)
    assert result["ok"] is True


def test_confirmation_times_out_as_no():
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    assert bot.confirm(ME, "Confirmas?", timeout=0.1) is False
    assert "não fiz nada" in api.sent[-1]["text"]


def test_sensitive_tools():
    assert is_sensitive("continue_work", {})
    assert is_sensitive("open_project", {"name": "TaskFlow", "claude_prompt": "continua"})
    assert not is_sensitive("open_project", {"name": "TaskFlow", "claude_prompt": ""})
    assert not is_sensitive("open_app", {"name": "Spotify"})


def test_format_reply():
    ok = ToolResult(ToolCall("open_app", {}), "Abri Spotify.")
    bad = ToolResult(ToolCall("send_message", {}), "Não encontrei a conversa 'Zé'.", is_error=True)
    reply = remote.format_reply(["Abri o Spotify."], [ok, bad])
    assert "✅ Abri Spotify." in reply and "❌ Não encontrei" in reply and "1/2" in reply


class FakeLLM(ChatProvider):
    def __init__(self, steps):
        super().__init__(system_prompt="", tools=TOOL_SPECS)
        self.steps = list(steps)

    def _user_message(self, text):
        return {"role": "user", "content": text}

    def step(self):
        step = self.steps.pop(0)
        self._append({"role": "assistant", "content": step.text})
        return step

    def add_tool_results(self, results):
        self._append({"role": "tool"})


def test_controller_asks_before_sensitive_action(monkeypatch):
    ran = []
    monkeypatch.setattr("jarvis.actions.projects.continue_work", lambda name="": ran.append(name) or "Abri.")
    controller = remote.TelegramController(api=FakeAPI())
    controller.brain.llm = FakeLLM([StepResult("", [ToolCall("continue_work", {})]), StepResult("Não fiz.")])
    monkeypatch.setattr(controller.bot, "confirm", lambda chat, question: False)  # carrega em ❌
    reply = controller.handle("continua o trabalho no GitHub", ME)
    assert ran == []  # recusado: não correu
    assert "não autorizou" in reply


def test_write_env_updates_and_appends(tmp_path):
    env = tmp_path / ".env"
    env.write_text("JARVIS_BROWSER=opera\n# JARVIS_TELEGRAM_TOKEN=\n", encoding="utf-8")
    write_env("JARVIS_TELEGRAM_TOKEN", "123:abc", env)
    write_env("JARVIS_TELEGRAM_ALLOWED_IDS", "111", env)
    assert env.read_text(encoding="utf-8").splitlines() == [
        "JARVIS_BROWSER=opera", "JARVIS_TELEGRAM_TOKEN=123:abc", "JARVIS_TELEGRAM_ALLOWED_IDS=111",
    ]


def test_old_messages_are_not_executed():
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    api.push("message", message(ME, "abre a calculadora", age=600))  # enviada há 10 min
    bot.poll_once()
    assert list(bot.jobs.queue) == []
    assert "quando estava desligado" in api.sent[-1]["text"]


def test_screenshot_is_sent_to_chat(tmp_path, monkeypatch):
    from jarvis.actions import screen

    shot = tmp_path / "print.png"
    shot.write_bytes(b"png")
    monkeypatch.setattr(screen, "screenshot", lambda monitor=0: f"Tirei um print.\n📎 {shot}")
    api = FakeAPI()
    sent_files = []
    api.send_file = lambda chat, path, caption="": sent_files.append((chat, path))
    controller = remote.TelegramController(api=api)
    controller.brain.llm = FakeLLM([StepResult("", [ToolCall("screenshot", {})]), StepResult("Aqui está.")])
    reply = controller.handle("manda-me um print", ME)
    assert sent_files == [(ME, shot)]
    assert "Tirei um print." in reply and "📎" not in reply.split("\n")[0]


def test_restart_acknowledges_update_and_ignores_old_restart(monkeypatch):
    from jarvis import updates

    restarts = []
    monkeypatch.setattr(updates, "restart", lambda *a, **k: restarts.append(1))
    api = FakeAPI()
    calls = []
    real_call = api.call
    api.call = lambda method, **p: calls.append((method, p)) or real_call(method, **p)
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")

    # /reiniciar enviado ANTES deste arranque: ignorado (evita o ciclo de reinícios).
    monkeypatch.setattr(updates, "STARTED", 10**10)
    api.push("message", message(ME, "/reiniciar"))
    bot.poll_once()
    assert restarts == []

    # /reiniciar novo: confirma a leitura ao Telegram ANTES de reiniciar.
    monkeypatch.setattr(updates, "STARTED", 0)
    api.push("message", message(ME, "/reiniciar"))
    bot.poll_once()
    assert restarts == [1]
    acks = [p for m, p in calls if m == "getUpdates" and p.get("timeout") == 0]
    assert acks and acks[-1]["offset"] == bot.offset


# --- ecrã ao vivo -------------------------------------------------------------

def test_live_screen_updates_same_message():
    from jarvis.telegram_bot import LIVE_REQUEST, TelegramBot

    class API:
        def __init__(self):
            self.sent, self.edits, self.calls = [], [], []

        def send_photo_bytes(self, chat, data, caption=""):
            self.sent.append((chat, data))
            return {"message_id": 7}

        def edit_photo_bytes(self, chat, message_id, data, caption=""):
            self.edits.append((message_id, data))

        def call(self, method, **params):
            self.calls.append(method)

    api = API()
    bot = TelegramBot(api, {1}, handle=lambda text, chat: "")
    bot.live_screen(5, seconds=0.25, interval=0.05, grab=lambda: b"jpg")
    assert api.sent == [(5, b"jpg")] and api.edits and all(m == 7 for m, _ in api.edits)
    assert api.calls == ["editMessageCaption"]
    assert LIVE_REQUEST.search("mostra-me o ecrã ao vivo") and LIVE_REQUEST.search("quero ver o pc em tempo real")
    assert not LIVE_REQUEST.search("manda-me um print do ecrã")


def test_photos_and_links_are_saved_as_memes(monkeypatch, tmp_path):
    import time as _time

    from jarvis import memes
    from jarvis.telegram_bot import TelegramBot

    monkeypatch.setattr(memes, "my_folder", lambda: tmp_path)

    class API:
        def __init__(self):
            self.messages = []

        def call(self, method, **params):
            if method == "sendMessage":
                self.messages.append(params["text"])
            return {}

        def download(self, file_id):
            return b"JPEGDATA", "photos/file_1.jpg"

    api = API()
    bot = TelegramBot(api, {1}, handle=lambda text, chat: "")
    msg = {"from": {"id": 1}, "chat": {"id": 1}, "date": _time.time(), "caption": "Macaco fixe",
           "photo": [{"file_id": "small"}, {"file_id": "big"}]}
    bot.save_meme(1, msg, msg["photo"][-1])
    assert (tmp_path / "Macaco fixe.jpg").read_bytes() == b"JPEGDATA"
    assert "Guardei o meme \"Macaco fixe\"" in api.messages[-1]
    assert bot.jobs.empty()


def test_live_screen_numbers_and_order():
    from jarvis.telegram_bot import live_screen_number, screens

    assert live_screen_number("/aovivo") == 0 and live_screen_number("/aovivo 2") == 2
    assert live_screen_number("mostra o ecrã 3 ao vivo") == 3 and live_screen_number("ecrã ao vivo") == 0
    mons = [{"left": -1920, "top": 0}, {"left": 1920, "top": 0}, {"left": -1920, "top": 0}, {"left": 0, "top": 0}]
    assert [m["left"] for m in screens(mons)] == [-1920, 0, 1920]
