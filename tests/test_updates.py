"""Aviso de versão nova: não percorre o código a cada resposta."""

from jarvis import updates


def test_new_code_is_checked_at_most_every_few_seconds(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("x")
    monkeypatch.setattr(updates, "CODE_DIR", tmp_path)
    monkeypatch.setattr(updates, "_found", False)
    monkeypatch.setattr(updates, "_last_check", 0.0)
    assert updates.newer_code_available(since=10**12) is False  # nada mais novo
    scans = []
    real = type(tmp_path).rglob
    monkeypatch.setattr(type(tmp_path), "rglob", lambda self, pat: scans.append(1) or real(self, pat))
    for _ in range(5):
        updates.newer_code_available(since=0)
    assert scans == []  # ainda dentro dos 10 s: nem olhou para a pasta
    monkeypatch.setattr(updates, "_last_check", 0.0)
    assert updates.newer_code_available(since=0) is True  # agora sim, encontra
    assert updates.newer_code_available(since=10**12) is True  # e fica assim
