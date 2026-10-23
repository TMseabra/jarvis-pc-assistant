"""Code red: bloquear o PC se alguém tocar no teclado/rato (sem ganchos reais)."""

from jarvis import guard
from jarvis.guard import Guard, should_lock


def test_parse_code_red_and_green():
    assert guard.parse("jarvis code red") == "arm"
    assert guard.parse("Código vermelho") == "arm"
    assert guard.parse("code green") == "disarm"
    assert guard.parse("desativa o code red") == "disarm"
    assert guard.parse("abre o spotify") is None
    assert guard.parse("/codered") == "arm" and guard.parse("/codegreen") == "disarm"  # atalhos do Telegram
    assert guard.parse("abre o codeblocks") is None


def test_only_people_after_the_grace_period_lock():
    assert not should_lock(None, 100, injected=False)  # desligado
    assert not should_lock(10, 12, injected=False)  # ainda na margem para te afastares
    assert not should_lock(10, 100, injected=True)  # o próprio Jarvis a mexer no PC
    assert should_lock(10, 16, injected=False)


def test_lock_happens_once_and_notifies(monkeypatch):
    locked, told = [], []
    g = Guard(lock=lambda: locked.append(1))
    g.listeners.append(lambda: told.append(1))
    monkeypatch.setattr(g, "_start_hooks", lambda: setattr(g, "hooks_ok", True))
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
    monkeypatch.setattr(g, "_start_hooks", lambda: setattr(g, "hooks_ok", True))
    monkeypatch.setattr(g, "_stop_hooks", lambda: None)
    g.arm()
    assert "desativado" in g.disarm()
    assert not g.armed


def test_grace_period_comes_from_the_config():
    from jarvis.config import config

    old = config.code_red_grace
    object.__setattr__(config, "code_red_grace", 30.0)  # a Config é imutável: repõe-se no fim
    try:
        assert not should_lock(10, 20, injected=False)  # 10 s < 30 s
        assert should_lock(10, 45, injected=False)
    finally:
        object.__setattr__(config, "code_red_grace", old)


def test_does_not_claim_to_be_armed_when_windows_refuses_the_hooks(monkeypatch):
    g = Guard(lock=lambda: None)
    monkeypatch.setattr(g, "_start_hooks", lambda: None)  # hooks_ok fica False
    monkeypatch.setattr(g, "_stop_hooks", lambda: None)
    assert "Não consegui" in g.arm()
    assert not g.armed
    assert g.on_input() is False
