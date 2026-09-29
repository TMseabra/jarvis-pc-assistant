"""Baixar o som das outras apps (Spotify, jogos, browser...) enquanto o Jarvis fala.

Usa o misturador de volume do Windows (volume por app), por isso o volume geral não muda e o
som do próprio Jarvis fica igual. No fim volta tudo ao volume que estava, com um fade curto.
JARVIS_DUCK=0.2 põe as outras apps a 20% do volume delas; JARVIS_DUCK=1 desliga isto.
"""

import contextlib
import logging
import os
import time

from jarvis.config import config

log = logging.getLogger("jarvis")


def _sessions():
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        pass
    from pycaw.pycaw import AudioUtilities

    me = os.getpid()
    for session in AudioUtilities.GetAllSessions():
        if session.Process is not None and session.Process.pid != me:
            yield session.SimpleAudioVolume


def _fade(pairs, start: float, end: float, steps: int = 6, duration: float = 0.18):
    """pairs: [(volume, original)]; vai de original*start até original*end."""
    for i in range(1, steps + 1):
        factor = start + (end - start) * i / steps
        for volume, original in pairs:
            try:
                volume.SetMasterVolume(max(0.0, min(1.0, original * factor)), None)
            except Exception:
                pass
        time.sleep(duration / steps)


@contextlib.contextmanager
def ducked(level: float | None = None):
    """Enquanto dura o `with`, as outras apps ficam a `level` do volume que tinham."""
    level = config.duck_level if level is None else level
    pairs = []
    if 0 <= level < 1:
        try:
            for volume in _sessions():
                original = volume.GetMasterVolume()
                if original > 0.01 and not volume.GetMute():
                    pairs.append((volume, original))
            _fade(pairs, 1.0, level)
        except Exception as exc:  # sem pycaw / sem áudio: fala na mesma
            log.debug("ducking indisponível: %s", exc)
            pairs = []
    try:
        yield
    finally:
        if pairs:
            _fade(pairs, level, 1.0)
