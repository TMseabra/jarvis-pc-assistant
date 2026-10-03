import pytest

from jarvis.actions.messaging import (
    ChatMessage,
    MessagingError,
    format_messages,
    get_platform,
    name_matches,
    parse_whatsapp_meta,
    pick_result,
)
from jarvis.brain import Brain, is_action_request
from jarvis.llm import ChatProvider, LLMError, StepResult, ToolCall
from jarvis.main import is_yes
from jarvis.tools import TOOL_SPECS, ToolExecutor, extract_dictated_message


class FakeLLM(ChatProvider):
    """Provider falso: devolve StepResults pré-definidos e regista os resultados das ferramentas."""

    def __init__(self, steps, max_turns=10):
        super().__init__(system_prompt="", tools=TOOL_SPECS, max_turns=max_turns)
        self.steps = list(steps)
        self.tool_results = []

    def _user_message(self, text):
        return {"role": "user", "content": text}

    def step(self):
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        self._append({"role": "assistant", "content": step.text})
        return step

    def add_tool_results(self, results):
        self.tool_results.extend(results)
        self._append({"role": "tool", "content": [r.content for r in results]})


class FakeMessenger:
    def __init__(self):
        self.sent = []

    def read_messages(self, platform, contact, count):
        return f"{platform}/{contact}/{count}"

    def send_message(self, platform, contact, message, confirm=None):
        if confirm is not None:
            message = confirm(contact)  # como o real: confirma com a conversa já aberta
            if not message:
                return None
        self.sent.append((platform, contact, message))
        return "enviada"

    def close(self):
        pass


def call(name, **args):
    return StepResult(text="", tool_calls=[ToolCall(name=name, args=args)])


def make_brain(steps, messenger=None, confirm=None):
    llm = FakeLLM(steps)
    return Brain(llm=llm, executor=ToolExecutor(messenger=messenger or FakeMessenger(), confirm=confirm)), llm


def test_tool_specs_are_valid():
    names = [t["name"] for t in TOOL_SPECS]
    assert len(names) == len(set(names))
    for tool in TOOL_SPECS:
        params = tool["parameters"]
        assert set(params["required"]) <= set(params["properties"])


def test_plain_answer_without_tools():
    brain, llm = make_brain([StepResult("Olá!")])
    assert brain.handle("olá") == "Olá!"
    assert llm.turns[0][0] == {"role": "user", "content": "olá"}


def test_tool_loop_runs_tool_and_returns_final_text(monkeypatch):
    opened = []
    monkeypatch.setattr("jarvis.actions.system.open_url", opened.append)
    brain, llm = make_brain([call("open_website", url="https://www.youtube.com"), StepResult("Abri o YouTube.")])

    assert brain.handle("abre o youtube") == "Abri o YouTube."
    assert opened == ["https://www.youtube.com"]
    assert not llm.tool_results[0].is_error


def test_empty_final_text_falls_back_to_tool_result(monkeypatch):
    monkeypatch.setattr("jarvis.actions.system.open_url", lambda url: None)
    brain, _ = make_brain([call("web_search", query="gatos"), StepResult("")])
    assert brain.handle("pesquisa gatos") == "Pesquisei por 'gatos'."


def test_send_message_respects_confirmation():
    messenger = FakeMessenger()
    brain, llm = make_brain(
        [call("send_message", platform="whatsapp", contact="Ana", message="Já vou"), StepResult("Cancelado.")],
        messenger=messenger,
        confirm=lambda *a: None,
    )
    brain.handle("diz à Ana que já vou")
    assert messenger.sent == []
    assert "cancelou" in llm.tool_results[0].content


def test_send_message_when_confirmed():
    messenger = FakeMessenger()
    seen = []

    def confirm(platform, contact, message):
        seen.append((platform, contact, message))
        return "oi, corrigido"

    ToolExecutor(messenger=messenger, confirm=confirm).run(
        "send_message", {"platform": "discord", "contact": "Rui", "message": "oi"}
    )
    assert seen == [("Discord", "Rui", "oi")]
    assert messenger.sent == [("discord", "Rui", "oi, corrigido")]


def test_dictated_text_wins_over_model_rewrite():
    messenger = FakeMessenger()
    brain, _ = make_brain(
        [
            call("send_message", platform="whatsapp", contact="Ana",
                 message="Sim, ficarei feliz em jantar com você amanhã às 20h."),
            StepResult("Enviei."),
        ],
        messenger=messenger,
        confirm=lambda p, c, m: m,
    )
    brain.handle("responde à Ana no whatsapp a dizer que sim, às 20h está ótimo")
    assert messenger.sent == [("whatsapp", "Ana", "Sim, às 20h está ótimo")]


def test_claimed_send_without_tool_call_is_retried():
    messenger = FakeMessenger()
    brain, llm = make_brain(
        [
            StepResult("Enviaste a mensagem à Ana."),  # mentira: não chamou a ferramenta
            call("send_message", platform="whatsapp", contact="Ana", message="sim"),
            StepResult("Enviei."),
        ],
        messenger=messenger,
        confirm=lambda p, c, m: m,
    )
    assert brain.handle("responde à Ana que sim") == "Enviei."
    assert messenger.sent == [("whatsapp", "Ana", "Sim")]
    assert "Nota do sistema" in llm.turns[-1][2]["content"]


def test_claimed_send_twice_is_reported_honestly():
    brain, _ = make_brain([StepResult("Enviado!"), StepResult("Já enviei.")])
    # A resposta falsa do modelo ("Já enviei.") não é mostrada.
    assert brain.handle("diz à Ana que já vou") == "Não enviei nenhuma mensagem. Tenta pedir outra vez."


def test_claimed_action_without_tool_call_is_retried(monkeypatch):
    monkeypatch.setattr("jarvis.actions.system.open_app", lambda name: f"Abri {name}.")
    brain, llm = make_brain([
        StepResult("Olá!"),                 # turno anterior
        StepResult("Spotify foi aberto."),  # mentira: não chamou a ferramenta
        StepResult("", [ToolCall("open_app", {"name": "Spotify"})]),
        StepResult("Abri o Spotify."),
    ])
    seen_history = []
    original_step = llm.step
    llm.step = lambda: (seen_history.append(len(llm.turns)), original_step())[1]

    brain.handle("olá")
    assert brain.handle("abre o spotify") == "Abri o Spotify."
    # 1.ª tentativa com os 2 turnos; a nova tentativa só com o turno atual.
    assert seen_history == [1, 2, 1, 2]
    assert llm.tool_results[0].content == "Abri Spotify."
    # A resposta falsa foi descartada e o turno anterior continua no histórico.
    assert [t[0]["content"] for t in llm.turns] == ["olá", "abre o spotify"]
    assert "foi aberto" not in str(llm.turns[-1])


def test_claimed_action_twice_is_reported_honestly():
    brain, _ = make_brain([StepResult("Aberto."), StepResult("Já está aberto.")])
    assert brain.handle("Jarvis, abre a calculadora") == "Não consegui fazer isso. Tenta dizer de outra forma."


def test_clarifying_question_is_not_nudged():
    # Tenta uma vez (sem histórico); se voltar a perguntar, a pergunta passa.
    brain, llm = make_brain([StepResult("Que aplicação queres abrir?"), StepResult("Qual aplicação?")])
    assert brain.handle("abre aquela app") == "Qual aplicação?"


@pytest.mark.parametrize("text, expected", [
    ("abre o Spotify", True),
    ("Jarvis, podes pesquisar o tempo", True),
    ("lê as mensagens da Ana", True),
    ("por favor manda um email", True),
    ("qual é a capital de França?", False),
    ("diz-me que horas são", False),
    ("o spotify abre sozinho?", False),
])
def test_is_action_request(text, expected):
    assert is_action_request(text) is expected


def test_no_nudge_for_normal_requests():
    brain, llm = make_brain([StepResult("São 10h.")])
    assert brain.handle("diz-me que horas são") == "São 10h."
    assert len(llm.turns[-1]) == 2


def test_two_sends_in_one_request_keep_model_texts():
    messenger = FakeMessenger()
    step = StepResult("", [
        ToolCall("send_message", {"platform": "whatsapp", "contact": "Ana", "message": "Sim"}),
        ToolCall("send_message", {"platform": "whatsapp", "contact": "Rui", "message": "Não"}),
    ])
    brain, _ = make_brain([step, StepResult("Feito.")], messenger=messenger, confirm=lambda p, c, m: m)
    brain.handle("diz à Ana que sim e ao Rui que não")
    assert messenger.sent == [("whatsapp", "Ana", "Sim"), ("whatsapp", "Rui", "Não")]


@pytest.mark.parametrize("request_text, expected", [
    ("diz à Ana que já vou", "Já vou"),
    ("responde-lhe que sim", "Sim"),
    ("responde à Ana no whatsapp a dizer que sim, às 20h está ótimo", "Sim, às 20h está ótimo"),
    ("manda uma mensagem ao Rui a dizer que chego às 8 no discord", "Chego às 8"),
    ('envia ao Rui "bom jogo!"', "Bom jogo!"),
    ("escreve à Joana «parabéns»", "Parabéns"),
    ("responde à Ana a perguntar a que horas é o jantar", None),
    ("pergunta à Ana se quer jantar", None),
    ("responde à Ana", None),
    ("abre o spotify", None),
    ("diz-me que horas são", None),
    ("diz à Ana Silva no whatsapp que já saí", "Já saí"),
    ("envia uma mensagem para o Rui a dizer que ok", "Ok"),
    ("manda à Ana o link do YouTube que te mandei", None),
    ("diz à Ana que o que ela quiser está bem", "O que ela quiser está bem"),
    ("responde que sim", "Sim"),
    ("diz ao Rui \"d'acordo\"", "D'acordo"),
    ("mandei-lhe uma foto que tirei", None),
    ("manda uma mensagem ao Rafosto a dizer anda jogar no Discord", "Anda jogar"),
    ("envia ao Rui dizendo: chego já", "Chego já"),
])
def test_extract_dictated_message(request_text, expected):
    assert extract_dictated_message(request_text) == expected


def test_read_messages_are_marked_untrusted_and_count_is_clamped():
    out = ToolExecutor(messenger=FakeMessenger()).run(
        "read_messages", {"platform": "telegram", "contact": "X", "count": "999"}
    )
    assert out.startswith("<mensagens_recebidas>\ntelegram/X/50\n</mensagens_recebidas>")


def test_missing_argument_is_an_error():
    brain, llm = make_brain([call("open_app"), StepResult("Qual app?")])
    brain.handle("abre")
    assert llm.tool_results[0].is_error
    assert "name" in llm.tool_results[0].content


def test_tool_errors_are_reported_to_model():
    class Broken(FakeMessenger):
        def read_messages(self, *a):
            raise MessagingError("Não encontrei a conversa")

    brain, llm = make_brain(
        [call("read_messages", platform="telegram", contact="X", count=5), StepResult("Não encontrei.")],
        messenger=Broken(),
    )
    brain.handle("lê o telegram do X")
    assert llm.tool_results[0].is_error


def test_llm_error_discards_turn():
    brain, llm = make_brain([StepResult("olá"), LLMError("em baixo")])
    brain.handle("primeiro")
    with pytest.raises(LLMError):
        brain.handle("segundo")
    assert len(llm.turns) == 1


def test_history_keeps_only_last_turns():
    llm = FakeLLM([StepResult(str(i)) for i in range(5)], max_turns=2)
    brain = Brain(llm=llm, executor=ToolExecutor(messenger=FakeMessenger()))
    for i in range(5):
        brain.handle(f"pedido {i}")
    assert [t[0]["content"] for t in llm.turns] == ["pedido 3", "pedido 4"]


def test_is_yes():
    assert is_yes("Sim, envia")
    assert is_yes("s")
    assert not is_yes("não")
    assert not is_yes("")
    assert not is_yes(None)


def test_platform_lookup():
    assert get_platform(" WhatsApp ").name == "WhatsApp"
    with pytest.raises(MessagingError):
        get_platform("msn")


def test_format_messages():
    msgs = [ChatMessage("Ana", "olá", "19:00"), ChatMessage("", "tudo bem?", outgoing=True), ChatMessage("", "?")]
    assert format_messages(msgs) == "[19:00] Ana: olá\nTu (enviada): tudo bem?\nOutra pessoa: ?"
    assert "Não encontrei" in format_messages([])


def test_name_matching():
    assert name_matches("Ana Silva 🌸", "ana")
    assert name_matches("Ána Sílva", "Ana Silva")
    assert not name_matches("Anabela", "Ana")
    assert not name_matches("Ana Costa", "Ana Silva")
    assert not name_matches("", "Ana")


def test_pick_result_prefers_exact_match():
    assert pick_result(["Anabela", "Ana Silva", "Ana"], "Ana") == 2
    assert pick_result(["Anabela", "Ana Silva"], "Ana") == 1
    assert pick_result(["Anabela"], "Ana") is None


def test_parse_whatsapp_meta():
    assert parse_whatsapp_meta("[12:34, 01/01/2026] Ana Silva: ") == ("Ana Silva", "12:34")
    assert parse_whatsapp_meta("sem formato") == ("", "")


def test_claimed_action_in_reply_is_retried_even_without_action_verb(monkeypatch):
    monkeypatch.setattr("jarvis.actions.files.open_path", lambda name: "Abri as Definições: Bluetooth.")
    brain, llm = make_brain([
        StepResult("Abro as definições do Bluetooth para ti."),  # afirma, mas não chamou nada
        StepResult("", [ToolCall("open_path", {"name": "bluetooth"})]),
        StepResult("Abri as definições do Bluetooth."),
    ])
    assert brain.handle("o bluetooth não está a funcionar") == "Abri as definições do Bluetooth."


def test_normal_answer_with_passive_words_is_not_a_claim():
    brain, _ = make_brain([StepResult("O museu está aberto até às 18h.")])
    assert brain.handle("a que horas fecha o museu?") == "O museu está aberto até às 18h."


# --- envio em dois passos ------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("manda msg ao rafosto no discord", ("discord", "rafosto")),
    ("envia uma mensagem à Ana pelo whatsapp", ("whatsapp", "Ana")),
    ("manda mensagem pelo discord ao Rafosto", ("discord", "Rafosto")),
    ("jarvis, manda msg ao J no wpp", ("whatsapp", "J")),
    ("manda ao rafosto no discord a dizer bora", None),  # já tem o texto: não é isto
    ("abre o discord", None),
])
def test_parse_send_target(text, expected):
    from jarvis.tools import parse_send_target
    result = parse_send_target(text)
    if expected is None:
        assert result is None or extract_dictated_message(text)
    else:
        assert result == expected


def test_two_step_send_uses_next_message_as_is():
    messenger = FakeMessenger()
    brain, llm = make_brain([], messenger=messenger)  # o modelo nem é chamado
    assert brain.handle("manda msg ao rafosto no discord") == "Que mensagem queres enviar ao rafosto no Discord?"
    brain.handle("ent bro nao vieste a escola?")
    assert messenger.sent == [("discord", "rafosto", "ent bro nao vieste a escola?")]
    assert brain.pending_send is None


def test_two_step_send_can_be_cancelled():
    messenger = FakeMessenger()
    brain, _ = make_brain([], messenger=messenger)
    brain.handle("manda msg ao rafosto no discord")
    assert brain.handle("cancela") == "Ok, não enviei nada."
    assert messenger.sent == []


def test_two_step_send_new_command_cancels_pending(monkeypatch):
    monkeypatch.setattr("jarvis.actions.system.open_app", lambda name: f"Abri {name}.")
    messenger = FakeMessenger()
    brain, _ = make_brain([StepResult("", [ToolCall("open_app", {"name": "Spotify"})]), StepResult("Abri.")],
                          messenger=messenger)
    brain.handle("manda msg ao rafosto no discord")
    assert brain.handle("abre o spotify") == "Abri."
    assert messenger.sent == []


def test_enviando_is_a_claim():
    brain, _ = make_brain([StepResult("Enviando mensagem para o Rafosto."), StepResult("Enviando…")])
    assert "Não enviei" in brain.handle("diz ao rafosto no discord que já vou")


def test_screenshot_and_help_shortcuts_skip_the_model(monkeypatch):
    monkeypatch.setattr("jarvis.actions.screen.screenshot", lambda monitor=0: "Tirei um print de todos os ecrãs.")
    brain, llm = make_brain([])  # o modelo não é chamado
    assert brain.handle("Podes me manda foto no que esta na tela") == "Tirei um print de todos os ecrãs."
    assert brain.handle("Mostra me a tela") == "Tirei um print de todos os ecrãs."
    assert "sei fazer" in brain.handle("podes me dizer o que ele ja faz?")


def test_photo_of_what_was_just_said(monkeypatch):
    from jarvis.actions import find

    seen = []
    monkeypatch.setattr(find, "find_image", lambda query, *a: seen.append(query) or f"Foto de {query}")
    brain, llm = make_brain([StepResult(text="O de morango é mais doce, eu escolho esse.")])
    llm.complete = lambda system, prompt: "gelado de morango\n"
    assert "morango" in brain.handle("qual é melhor, gelado de menta ou de morango?")
    assert brain.handle("manda foto desse") == "Foto de gelado de morango"
    assert seen == ["gelado de morango"]


def test_photo_of_that_without_context_goes_to_the_model():
    brain, llm = make_brain([StepResult(text="De que queres a foto?")] * 2)
    assert brain.handle("manda foto desse") == "De que queres a foto?"
