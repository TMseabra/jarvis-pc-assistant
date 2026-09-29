from jarvis import followups
from jarvis.brain import Brain
from jarvis.llm import StepResult
from jarvis.tools import ToolExecutor
from tests.test_brain import FakeLLM, FakeMessenger

SUMMARY = """WhatsApp (1 por ler):
- Rafael Pedro (16:50): olá
Discord:
- 👤 Nenhum amigo te mandou mensagem.
- 🌐 Comunidades: 3 servidores com mensagens por ler.
Instagram: nada de novo.
LinkedIn: tens 2 mensagens/notificações por ver."""


def labels(options):
    return [label for label, _ in options]


def test_message_followups_only_where_there_is_something():
    options = followups.message_followups(SUMMARY)
    assert labels(options) == ["WhatsApp", "LinkedIn"]
    assert options[1][1].args == {"url": "https://www.linkedin.com/messaging/"}


def test_match_follow_up_answers():
    options = followups.message_followups(SUMMARY)
    assert followups.match("abre o linkedin", options)[1][0].name == "open_website"
    assert followups.match("2", options)[1][0].args["url"].startswith("https://www.linkedin")
    assert len(followups.match("abre elas", options)[1]) == 2
    kind, question = followups.match("sim", options)
    assert kind == "ask" and "1. WhatsApp" in question
    assert followups.match("abre o spotify", options) is None
    assert followups.match("sim", options[:1])[1][0].args == {"name": "WhatsApp"}


def test_offer_from_model_reply():
    options = followups.offer_from_reply("Encontrei a conversa. Queres que abra o LinkedIn?")
    assert options[0][1].args == {"url": "https://www.linkedin.com/messaging/"}
    assert followups.offer_from_reply("Queres que abra o Spotify?")[0][1].args == {"name": "Spotify"}
    assert followups.offer_from_reply("Qual app gostarias de abrir?") == []


def test_brain_yes_opens_what_was_offered(monkeypatch):
    opened = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": opened.append((name, args)) or "feito")
    offer = StepResult(text="Tens mensagens no LinkedIn. Queres que abra o LinkedIn?", tool_calls=[])
    brain = Brain(llm=FakeLLM([offer, offer]), executor=executor)
    brain.handle("tenho mensagens no linkedin?")
    assert brain.handle("sim") == "feito"
    assert opened == [("open_website", {"url": "https://www.linkedin.com/messaging/"})]
    assert brain.followups == []


REPLY = ('Podes ouvir "After the Rain" de Zedd feat. Alessia Cara. É uma música com vibes semelhantes a '
         '"Free". Também "Stay" dos The Kid LAROI.')


def test_songs_suggested_by_the_model():
    options = followups.offer_from_reply(REPLY, "que musica tem vibes igual")
    assert [(label, call.args["query"]) for label, call in options] == [
        ("After the Rain", "After the Rain Zedd"), ("Stay", "Stay The Kid LAROI")]
    assert options[0][1].name == "music"


def test_mete_uma_dessas_plays_the_first_suggestion():
    options = followups.offer_from_reply(REPLY)
    kind, calls = followups.match("mete uma dessas ent", options)
    assert kind == "run" and calls[0].args == {"action": "play", "query": "After the Rain Zedd"}
    assert followups.match("põe a stay", options)[1][0].args["query"] == "Stay The Kid LAROI"
    assert followups.match("a segunda", options)[1][0].args["query"] == "Stay The Kid LAROI"
    assert followups.match("abre o discord", options) is None


def test_videos_suggested():
    options = followups.offer_from_reply('Encontrei "Top 10 golos do Ronaldo" no YouTube.')
    assert options[0][1].name == "play_video"
    assert followups.offer_from_reply('Ok, está bem. "Nada" aqui.') == []
