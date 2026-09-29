import threading

from jarvis.gui.app import Api, GuiUI, state_for
from jarvis.llm import ToolCall, ToolResult


class FakeWindow:
    def __init__(self):
        self.js = []

    def evaluate_js(self, code):
        self.js.append(code)


def test_state_mapping():
    assert state_for("🎤 À escuta… começa por “Ei Jarvis, …”") == "listening"
    assert state_for("🔴 A gravar 3s") == "recording"
    assert state_for("A falar…") == "speaking"
    assert state_for("A pensar…") == "thinking"


def test_events_wait_for_page_then_flush():
    ui = GuiUI()
    ui.window = FakeWindow()
    ui.reply("Olá")
    assert ui.window.js == []
    ui.page_ready()
    ui.tool(ToolCall("music", {"action": "next"}))
    ui.tool_result(ToolResult(ToolCall("music", {}), "A tocar X.\nmais"))
    assert '"type": "reply"' in ui.window.js[0] and '"type": "action"' in ui.window.js[1]
    assert '"A tocar X."' in ui.window.js[2]


def test_status_context_restores_state():
    ui = GuiUI()
    ui.window = FakeWindow()
    ui.page_ready()
    ui.voice_enabled = True
    with ui.status("A pensar…"):
        pass
    assert '"thinking"' in ui.window.js[0] and '"listening"' in ui.window.js[-1]


def test_confirm_send_waits_for_answer():
    ui = GuiUI()
    ui.window = FakeWindow()
    ui.page_ready()
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("v", ui.confirm_send("WhatsApp", "Rafa", "olá")))
    t.start()
    while not ui._answers:
        pass
    Api(ui).answer(next(iter(ui._answers)), "olá editado")
    t.join(2)
    assert out["v"] == "olá editado"


def test_stop_and_commands(monkeypatch):
    from jarvis import voice

    stopped = []
    monkeypatch.setattr(voice, "stop_speaking", lambda: stopped.append(1))
    ui = GuiUI()
    ui.window = FakeWindow()
    api = Api(ui)
    api.send("abre o spotify")
    assert ui.next_command() == ("abre o spotify", False)
    api.stop()
    assert ui.cancel.is_set() and stopped == [1]
    api.toggle_mic()
    assert ui.mic_on is False
