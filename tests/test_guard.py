"""Code red: bloquear o PC se alguém tocar no teclado/rato (sem ganchos reais)."""

from jarvis import guard
from jarvis.guard import Guard, should_lock


def test_parse_code_red_and_green():
    assert guard.parse("jarvis code red") == "arm"
    assert guard.parse("Código vermelho") == "arm"
    assert guard.parse("code green") == "disarm"
    assert guard.parse("desativa o code red") == "disarm"
    assert guard.parse("abre o spotify") is None


def test_only_people_after_the_grace_period_lock():
    assert not should_lock(None, 100, injected=False)  # desligado
    assert not should_lock(10, 12, injected=False)  # ainda na margem para te afastares
    assert not should_lock(10, 100, injected=True)  # o próprio Jarvis a mexer no PC
    assert should_lock(10, 16, injected=False)


def test_lock_happens_once_and_notifies(monkeypatch):
    locked, told = [], []
    g = Guard(lock=lambda: locked.append(1))
    g.listeners.append(lambda: told.append(1))
    monkeypatch.setattr(g, "_start_hooks", lambda: None)
    monkeypatch.setattr(g, "_stop_hooks", lambda: None)
    g.arm()
    g.armed_at -= 10  # a margem já passou
    assert g.on_input() is True
    assert g.on_input() is False  # já desligou
    for _ in range(50):
        if told:
            break
        import time
        time.sleep(0.02)
    assert locked == [1] and told == [1] and not g.armed


def test_disarm(monkeypatch):
    g = Guard(lock=lambda: None)
    monkeypatch.setattr(g, "_start_hooks", lambda: None)
    monkeypatch.setattr(g, "_stop_hooks", lambda: None)
    g.arm()
    assert "desativado" in g.disarm()
    assert not g.armed
