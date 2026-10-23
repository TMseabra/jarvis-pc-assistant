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


# --- fotos: ver, resumir, explicar e guardar ---------------------------------------

def photo_message(caption=""):
    msg = message(ME, "")
    msg.pop("text")
    msg["photo"] = [{"file_id": "x"}]
    if caption:
        msg["caption"] = caption
    return msg


def test_photo_requests_are_recognised():
    from jarvis import photos

    assert photos.wants_analysis("faz um resumo disto")
    assert photos.wants_analysis("explica melhor")
    assert not photos.wants_analysis("macaco a dançar")
    assert photos.wants_follow_up("explica melhor")
    assert photos.wants_follow_up("lê isto")
    assert not photos.wants_follow_up("lê as mensagens do WhatsApp")


def test_photo_with_request_is_analysed_not_saved_as_meme(monkeypatch):
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    calls = []
    monkeypatch.setattr(bot, "analyze_photo", lambda chat, media, req: calls.append((media, req)))
    monkeypatch.setattr(bot, "save_meme", lambda *a: calls.append("meme"))
    api.push("message", photo_message("resume isto"))
    api.push("message", photo_message())
    bot.poll_once()
    time.sleep(0.2)
    assert ({"file_id": "x"}, "resume isto") in calls and "meme" in calls


def test_follow_up_text_uses_last_photo(monkeypatch):
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    calls = []
    monkeypatch.setattr(bot, "analyze_photo", lambda chat, media, req: calls.append((media, req)))
    api.push("message", message(ME, "explica melhor"))
    bot.poll_once()
    assert list(bot.jobs.queue) == [("explica melhor", ME)]  # sem foto recente: pedido normal
    bot.photo.remember(b"img", ".jpg")
    api.push("message", message(ME, "explica melhor"))
    bot.poll_once()
    time.sleep(0.2)
    assert calls == [(None, "explica melhor")]


def test_photo_with_text_is_read_once_then_answered_by_the_text_model(tmp_path, monkeypatch):
    from jarvis import photos

    monkeypatch.setenv("JARVIS_OUTPUT_DIR", str(tmp_path))
    memory = photos.PhotoMemory()
    memory.remember(b"img", ".jpg")
    reads, answers = [], iter(["resumo", "mais detalhe"])
    read = lambda image: reads.append(1) or "Texto do documento sobre o resumo académico e as suas regras."
    seen = []
    respond = lambda text, question, previous: seen.append((text[:5], previous)) or next(answers)
    assert memory.analyze("resume", read=read, answer_text=respond) == "resumo"
    assert memory.analyze("explica melhor", read=read, answer_text=respond) == "mais detalhe"
    assert reads == [1]  # a foto só é lida uma vez
    assert seen == [("Texto", ""), ("Texto", "resumo")]  # o 2.º pedido sabe o que já foi dito
    text = memory.path.with_suffix(".txt").read_text(encoding="utf-8")
    assert "Texto do documento" in text and "resumo" in text and "mais detalhe" in text


def test_photo_without_text_goes_to_the_vision_model(tmp_path, monkeypatch):
    from jarvis import photos

    monkeypatch.setenv("JARVIS_OUTPUT_DIR", str(tmp_path))
    memory = photos.PhotoMemory()
    memory.remember(b"img", ".jpg")
    answer = memory.analyze("o que é isto?", read=lambda image: "", ask=lambda image, q, prev: "Um gato.")
    assert answer == "Um gato."


def group_message(text):
    msg = message(ME, text)
    msg["chat"] = {"id": -100, "type": "supergroup"}
    return msg


def test_group_only_answers_when_called_by_name():
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    for text in ("ola pessoal", "o jarvis é fixe", "Jarvis, abre o Spotify", "Ei Jarvis abre a calculadora",
                 "@openjarvis_tomas_bot abre o Chrome"):
        api.push("message", group_message(text))
    bot.poll_once()
    assert list(bot.jobs.queue) == [("abre o Spotify", -100), ("abre a calculadora", -100), ("abre o Chrome", -100)]
    assert api.sent == []  # às outras mensagens nem se responde


def test_private_chat_does_not_need_the_name():
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    api.push("message", message(ME, "abre o Spotify"))
    bot.poll_once()
    assert list(bot.jobs.queue) == [("abre o Spotify", ME)]


def test_big_photos_are_shrunk_before_vision():
    import io

    from PIL import Image

    from jarvis import photos

    big = io.BytesIO()
    Image.new("RGB", (4000, 3000), "white").save(big, "PNG")
    small = Image.open(io.BytesIO(photos.shrink(big.getvalue())))
    assert max(small.size) == photos.MAX_SIDE
    tiny = io.BytesIO()
    Image.new("RGB", (200, 100)).save(tiny, "PNG")
    assert photos.shrink(tiny.getvalue()) == tiny.getvalue()  # pequenas ficam como estão
    assert photos.shrink(b"nao e imagem") == b"nao e imagem"


def test_very_long_photo_text_is_trimmed_not_silently_cut(monkeypatch):
    from jarvis import photos

    sent = []
    monkeypatch.setattr(photos, "_chat", lambda model, messages, *a, **k: sent.append(messages) or "ok")
    photos.respond("x" * 50_000, "resume")
    assert "texto cortado" in sent[0][1]["content"] and len(sent[0][1]["content"]) < photos.MAX_TEXT + 200


def test_long_replies_are_split_not_cut():
    from jarvis.telegram_bot import split_message

    assert split_message("curto") == ["curto"]
    text = "\n".join(f"linha {i} " + "x" * 90 for i in range(100))  # ~9500 caracteres
    parts = split_message(text)
    assert len(parts) == 3 and all(len(p) <= 4000 for p in parts)
    assert "\n".join(parts).replace("\n", " ").split() == text.replace("\n", " ").split()  # nada se perde
    assert len(split_message("y" * 9000)) == 3  # sem espaços: corta a direito


def test_send_puts_buttons_only_on_the_last_part():
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    bot.send(ME, "a" * 5000 + " fim", reply_markup={"inline_keyboard": []})
    assert len(api.sent) == 2 and "reply_markup" not in api.sent[0] and "reply_markup" in api.sent[1]


def test_photos_are_analysed_one_at_a_time(monkeypatch):
    class Api(FakeAPI):
        def download(self, file_id):
            return b"img", "photos/a.jpg"

    api = Api()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    running, peak = [0], [0]

    def slow_analyze(question):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        time.sleep(0.15)
        running[0] -= 1
        bot.photo.path = type("P", (), {"parent": type("D", (), {"name": "Fotos"})()})()
        return "ok"

    monkeypatch.setattr(bot.photo, "analyze", slow_analyze)
    threads = [threading.Thread(target=bot.analyze_photo, args=(ME, {"file_id": "x"}, "resume")) for _ in range(3)]
    [t.start() for t in threads]
    [t.join(timeout=5) for t in threads]
    assert peak[0] == 1


def test_meme_captions_and_chat_are_not_mistaken_for_photo_requests():
    from jarvis import photos

    for caption in ("vem aí", "melhor meme", "verdade", "a vez do macaco", "lembra-te", "macaco a dançar"):
        assert not photos.wants_analysis(caption), caption
    for text in ("qual é melhor, menta ou morango?", "lembra isto", "lê as mensagens do WhatsApp"):
        assert not photos.wants_follow_up(text), text
    assert photos.wants_analysis("jarvis isto ta certo? faz me resumo disso")
    assert photos.wants_analysis("pontos importantes") and photos.wants_follow_up("traduz isto")


def test_typing_is_renewed_while_a_photo_is_analysed(monkeypatch):
    class Api(FakeAPI):
        actions = 0

        def call(self, method, **params):
            if method == "sendChatAction":
                self.actions += 1
            return super().call(method, **params)

    api = Api()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    done = threading.Event()
    thread = threading.Thread(target=bot._keep_typing, args=(ME, done, 0.05))
    thread.start()
    time.sleep(0.3)
    done.set()
    thread.join(timeout=2)
    assert api.actions >= 3 and not thread.is_alive()


# --- fotos: erros do Ollama e leitura do texto --------------------------------------

class FakeVisionClient:
    def __init__(self, reply="", error=None):
        self.reply, self.error, self.calls = reply, error, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return type("R", (), {"message": type("M", (), {"content": self.reply})()})()


def test_missing_vision_model_is_explained():
    import ollama
    import pytest

    from jarvis import photos
    from jarvis.llm import LLMError

    client = FakeVisionClient(error=ollama.ResponseError("model not found", 404))
    with pytest.raises(LLMError, match="ollama pull"):
        photos.ask_vision(b"img", "o que é?", client=client)


def test_ollama_down_is_explained():
    import pytest

    from jarvis import photos
    from jarvis.llm import LLMError

    with pytest.raises(LLMError, match="ollama serve"):
        photos.ask_vision(b"img", "o que é?", client=FakeVisionClient(error=ConnectionError("recusada")))


def test_vision_model_is_unloaded_right_after_use():
    from jarvis import photos

    client = FakeVisionClient("Um gato.")
    assert photos.ask_vision(b"img", "o que é?", client=client) == "Um gato."
    assert client.calls[0]["keep_alive"] == photos.VISION_KEEP_ALIVE


def test_read_text_ignores_pictures_without_text():
    from jarvis import photos

    assert photos.read_text(b"img", client=FakeVisionClient("SEM TEXTO")) == ""
    assert photos.read_text(b"img", client=FakeVisionClient("ok")) == ""  # demasiado curto: é uma cena
    long = "Um texto de verdade, com várias palavras, que ocupa mais de quarenta caracteres."
    assert photos.read_text(b"img", client=FakeVisionClient(long)) == long


def test_saved_photos_never_overwrite_each_other(tmp_path):
    from jarvis import photos

    first = photos.save(b"1", ".jpg", "resume", "resposta 1", name="CV", dest=tmp_path)
    second = photos.save(b"2", ".jpg", "resume", "resposta 2", name="CV", dest=tmp_path)
    assert first != second and first.read_bytes() == b"1" and second.read_bytes() == b"2"
    assert "resposta 2" in second.with_suffix(".txt").read_text(encoding="utf-8")


def test_saved_photo_names_are_safe_for_windows(tmp_path):
    from jarvis import photos

    path = photos.save(b"x", "png", "pedido", "ok", name='a<b>:c"/d\e|f?g*', dest=tmp_path)
    assert path.exists() and path.suffix == ".png"
    assert not set('<>:"/\|?*') & set(path.name)


def test_saved_text_file_keeps_the_text_read_from_the_photo(tmp_path):
    from jarvis import photos

    path = photos.save(b"x", ".jpg", "resume", "o resumo", dest=tmp_path, text="texto lido da foto")
    saved = path.with_suffix(".txt").read_text(encoding="utf-8")
    assert "texto lido da foto" in saved and "o resumo" in saved and "resume" in saved


def test_live_screen_requests_and_screen_numbers():
    from jarvis.telegram_bot import LIVE_REQUEST, live_screen_number

    assert live_screen_number("/aovivo") == 0  # sem número: todos os ecrãs
    assert live_screen_number("/aovivo 2") == 2
    assert live_screen_number("mostra o ecrã 3 ao vivo") == 3
    assert live_screen_number("vê o monitor 1") == 1
    assert LIVE_REQUEST.search("mostra o meu pc em direto")
    assert not LIVE_REQUEST.search("abre o spotify")


def test_screens_are_numbered_left_to_right():
    from jarvis.telegram_bot import screens

    monitors = [{"left": -1920, "top": 0}, {"left": 1920, "top": 0}, {"left": 0, "top": 0}]  # [0] = todos juntos
    assert [m["left"] for m in screens(monitors)] == [0, 1920]  # o 1 é o da esquerda


def test_group_photos_need_the_name_in_the_caption(monkeypatch):
    api = FakeAPI()
    bot = TelegramBot(api, {ME}, lambda t, c: "ok")
    analysed, memes = [], []
    monkeypatch.setattr(bot, "analyze_photo", lambda chat, media, req: analysed.append(req))
    monkeypatch.setattr(bot, "save_meme", lambda *a: memes.append(1))
    for caption in ("Jarvis, resume isto", "resume isto", ""):
        msg = photo_message(caption)
        msg["chat"] = {"id": -100, "type": "group"}
        api.push("message", msg)
    bot.poll_once()
    time.sleep(0.2)
    assert analysed == ["resume isto"]  # o "Jarvis" sai do pedido
    assert memes == []  # fotos de grupo sem o nome nem são guardadas como memes
    assert api.sent == []
