from jarvis import ducking


class Vol:
    def __init__(self, v, muted=False):
        self.v, self.muted, self.history = v, muted, []

    def GetMasterVolume(self):
        return self.v

    def GetMute(self):
        return self.muted

    def SetMasterVolume(self, v, ctx):
        self.v = v
        self.history.append(round(v, 3))


def test_ducks_other_apps_and_restores(monkeypatch):
    spotify, game, muted = Vol(0.8), Vol(0.5), Vol(0.6, muted=True)
    monkeypatch.setattr(ducking, "_sessions", lambda: [spotify, game, muted])
    monkeypatch.setattr(ducking.time, "sleep", lambda s: None)
    with ducking.ducked(0.2):
        assert round(spotify.v, 3) == 0.16 and round(game.v, 3) == 0.1
    assert round(spotify.v, 3) == 0.8 and round(game.v, 3) == 0.5
    assert muted.history == []


def test_level_one_disables(monkeypatch):
    spotify = Vol(0.8)
    monkeypatch.setattr(ducking, "_sessions", lambda: [spotify])
    with ducking.ducked(1.0):
        pass
    assert spotify.history == []


def test_errors_do_not_stop_speaking(monkeypatch):
    def boom():
        raise OSError("sem áudio")

    monkeypatch.setattr(ducking, "_sessions", boom)
    ran = []
    with ducking.ducked(0.2):
        ran.append(1)
    assert ran == [1]
