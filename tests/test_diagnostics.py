import pytest

from jarvis.actions import diagnostics


def test_gpu_info_parsing():
    out = "NVIDIA GeForce RTX 4070 Laptop GPU, 57, 11, 6956, 8188\n"
    assert diagnostics.gpu_info(run=lambda cmd: out) == [
        {"name": "NVIDIA GeForce RTX 4070 Laptop GPU", "temp": 57, "util": 11, "mem_used": 6956, "mem_total": 8188}]
    assert diagnostics.gpu_info(run=lambda cmd: "") == []


def test_board_temperature_kelvin():
    assert diagnostics.board_temperature(run=lambda cmd: "301\n") == 27.9
    assert diagnostics.board_temperature(run=lambda cmd: "") is None


def test_verdict():
    assert "tudo bem" in diagnostics.verdict(10, 50, 50, [{"temp": 60}])
    warn = diagnostics.verdict(95, 95, 50, [{"temp": 90}])
    assert "CPU" in warn and "RAM" in warn and "90 ºC" in warn


@pytest.mark.parametrize("text,expected", [
    ("como está o pc?", True), ("faz um diagnóstico", True), ("qual é a temperatura do pc", True),
    ("mostra o gestor de tarefas", True), ("que apps tenho abertas", True), ("como está o desempenho", True),
    ("temperatura em lisboa amanhã", False), ("abre o spotify", False),
])
def test_request(text, expected):
    assert bool(diagnostics.REQUEST.search(text)) == expected


def test_pc_status_live_shape():
    pytest.importorskip("psutil")
    text = diagnostics.pc_status()
    assert "CPU:" in text and "RAM:" in text and "Disco C:" in text
