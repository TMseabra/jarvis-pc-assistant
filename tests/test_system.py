import pytest

from jarvis.actions import system


def test_normalize_url_adds_scheme():
    assert system.normalize_url("youtube.com") == "https://youtube.com"
    assert system.normalize_url(" http://a.pt ") == "http://a.pt"


def test_normalize_url_rejects_other_schemes():
    for bad in ("file:///C:/Windows", "ftp://servidor/x", "https://"):
        with pytest.raises(ValueError):
            system.normalize_url(bad)


def test_app_name_rejects_paths_and_shell_chars():
    assert system.validate_app_name(" Spotify ") == "Spotify"
    assert system.validate_app_name("ms-settings:") == "ms-settings:"
    for bad in ("calc & del x", "C:\\evil.exe", "../x", "a|b", ""):
        with pytest.raises(ValueError):
            system.validate_app_name(bad)


def test_search_url_encodes_query():
    assert system.search_url("tempo em Lisboa") == "https://www.google.com/search?q=tempo+em+Lisboa"


START_APPS = [
    ("Calculadora", "Microsoft.WindowsCalculator!App"),
    ("Câmara", "Microsoft.WindowsCamera!App"),
    ("Spotify", "C:\\Spotify.exe"),
    ("Spotify Uninstall", "uninstall"),
    ("Visual Studio Code", "Microsoft.VisualStudioCode"),
    ("Microsoft Edge", "MSEdge"),
    ("Microsoft Edge Dev Tools", "EdgeDev"),
]


@pytest.mark.parametrize("name, expected", [
    ("calculadora", "Calculadora"),
    ("camara", "Câmara"),            # sem acento
    ("spotify", "Spotify"),          # exato, não o desinstalador
    ("visual studio", "Visual Studio Code"),
    ("edge", "Microsoft Edge"),      # "contém": o mais curto
    ("code", "Visual Studio Code"),
    ("a", None),                     # demasiado curto para correspondência parcial
    ("xpto", None),
])
def test_find_start_app(name, expected):
    found = system.find_start_app(name, START_APPS)
    assert (found[0] if found else None) == expected


def test_find_shortcut_prefers_exact_match(tmp_path):
    (tmp_path / "Spotify").mkdir()
    (tmp_path / "Spotify" / "Spotify.lnk").touch()
    (tmp_path / "Spotify Helper Tool.lnk").touch()
    assert system.find_windows_shortcut("spotify", [tmp_path]).stem == "Spotify"


def test_find_shortcut_partial_and_ignores_uninstall(tmp_path):
    (tmp_path / "Uninstall Code.lnk").touch()
    (tmp_path / "Visual Studio Code.lnk").touch()
    assert system.find_windows_shortcut("code", [tmp_path]).stem == "Visual Studio Code"


def test_find_shortcut_missing(tmp_path):
    assert system.find_windows_shortcut("nada", [tmp_path]) is None
    assert system.find_windows_shortcut("  ", [tmp_path]) is None


def test_open_app_unknown_does_not_call_startfile(monkeypatch):
    monkeypatch.setattr(system.sys, "platform", "win32")
    monkeypatch.setattr(system, "list_start_apps", lambda: [])
    monkeypatch.setattr(system, "find_windows_shortcut", lambda name: None)
    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    called = []
    monkeypatch.setattr(system.os, "startfile", called.append, raising=False)
    assert "Não encontrei" in system.open_app("xpto")
    assert called == []


def test_open_app_uses_apps_folder(monkeypatch):
    monkeypatch.setattr(system.sys, "platform", "win32")
    monkeypatch.setattr(system, "list_start_apps", lambda: START_APPS)
    called = []
    monkeypatch.setattr(system.os, "startfile", called.append, raising=False)
    assert system.open_app("calculadora") == "Abri Calculadora."
    assert called == ["shell:AppsFolder\\Microsoft.WindowsCalculator!App"]


def test_open_website_uses_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(system.webbrowser, "open", opened.append)
    system.open_website("youtube.com")
    assert opened == ["https://youtube.com"]
