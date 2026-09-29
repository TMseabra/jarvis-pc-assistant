import pytest

from jarvis.power_intents import parse_power


@pytest.mark.parametrize("text,action", [
    ("Fecha o pc", "lock"), ("Windows L", "lock"), ("Lock pc", "lock"), ("Lock_pc", "lock"),
    ("bloqueia o computador", "lock"), ("desliga o pc", "shutdown"), ("encerra o computador", "shutdown"),
    ("reinicia o pc", "restart"), ("põe o pc a dormir", "sleep"), ("suspende o pc", "sleep"),
    ("cancela o desligar", "cancel"), ("fecha o spotify", None), ("desliga a música", None),
])
def test_parse_power(text, action):
    got = parse_power(text)
    assert (got[0] if got else None) == action


def _brain(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    calls = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": calls.append((name, args)) or "feito")
    return Brain(llm=FakeLLM([]), executor=executor), calls


def test_lock_asks_then_locks(monkeypatch):
    brain, calls = _brain(monkeypatch)
    assert "Windows + L" in brain.handle("Fecha o pc") and calls == []
    assert brain.handle("sim") == "feito"
    assert calls == [("lock_pc", {})]


def test_shutdown_asks_and_no_cancels(monkeypatch):
    brain, calls = _brain(monkeypatch)
    assert "Desligo o PC?" in brain.handle("desliga o pc")
    assert "não fiz nada" in brain.handle("não")
    assert calls == []
    brain.handle("desliga o pc")
    brain.handle("sim")
    assert calls == [("power", {"action": "shutdown"})]
    brain.handle("cancela o desligar")
    assert calls[-1] == ("power", {"action": "cancel"})
