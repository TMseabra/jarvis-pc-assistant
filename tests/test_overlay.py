import pytest

from jarvis import overlay


@pytest.mark.parametrize("text,expected", [
    ("diz ola na tela do pc", "Olá"),
    ("escreve 'bom dia' no ecrã em grande", "Bom dia"),
    ("jarvis mostra Benfica campeão no ecrã do computador", "Benfica campeão"),
    ("mostra-me o ecrã", None),
    ("manda-me um print do ecrã", None),
])
def test_parse_overlay_request(text, expected):
    assert overlay.parse_request(text) == expected


def test_brain_overlay_shortcut(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    calls = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": calls.append((name, args)) or "ok")
    brain = Brain(llm=FakeLLM([]), executor=executor)
    brain.handle("diz ola na tela do pc")
    brain.handle("manda-me um print do ecrã")
    assert calls == [("show_on_screen", {"text": "Olá"}), ("screenshot", {})]
