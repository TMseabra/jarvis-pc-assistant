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
