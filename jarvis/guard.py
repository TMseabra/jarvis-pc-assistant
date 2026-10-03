"""Code red: "Jarvis, code red" -> se alguém tocar numa tecla ou mexer no rato, o PC bloqueia (Win+L).

- Tens 5 segundos para te afastares depois de dizeres "code red" (senão bloqueava logo contigo).
- O teclado e o rato são vigiados com ganchos de baixo nível do Windows. O que o próprio Jarvis
  faz no PC (abrir apps, escrever, clicar) é "injetado" e não conta.
- Quando bloqueia, o code red desliga-se sozinho (e avisa no Telegram, se o pediste por lá).
- Desligas com "code green" / "desativa o code red" (por voz ou Telegram), sem tocar em nada.
"""

import re
import threading
import time

from jarvis.log import log

GRACE_SECONDS = 5.0

_ARM = re.compile(r"\bc[oó]d(?:e|igo)?\s*[-_]?\s*(?:red|vermelho)\b", re.IGNORECASE)
_DISARM = re.compile(
    r"\bc[oó]d(?:e|igo)?\s*[-_]?\s*(?:green|verde)\b|"
    r"\b(?:desativa|desliga|cancela|p[aá]ra|acaba|tira)\w*\s+(?:o\s+)?c[oó]d(?:e|igo)?\s*[-_]?\s*(?:red|vermelho)\b",
    re.IGNORECASE,
)


def parse(text: str) -> str | None:
    """"code red" -> "arm"; "code green" / "desativa o code red" -> "disarm"; senão None."""
    if _DISARM.search(text):
        return "disarm"
    if _ARM.search(text):
        return "arm"
    return None


def should_lock(armed_at: float | None, now: float, injected: bool, grace: float = GRACE_SECONDS) -> bool:
    """Um evento de teclado/rato bloqueia se o code red está ativo, já passou a margem e foi uma pessoa."""
    return armed_at is not None and not injected and now - armed_at >= grace


class Guard:
    def __init__(self, lock=None):
        if lock is None:
            from jarvis.actions.system import lock_pc as lock
        self._lock = lock
        self.armed_at: float | None = None
        self.listeners: list = []  # chamados (sem argumentos) quando o code red bloqueia o PC
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    @property
    def armed(self) -> bool:
        return self.armed_at is not None

    def arm(self) -> str:
        if self.armed:
            return "O code red já está ativo."
        self.armed_at = time.monotonic()
        self._start_hooks()
        log.info("code red ativado")
        return (f"🔴 Code red ativo dentro de {int(GRACE_SECONDS)} segundos. Afasta-te do teclado e do rato: "
                "se alguém lhes tocar, bloqueio o PC. Diz \"code green\" para desligar.")

    def disarm(self) -> str:
        was = self.armed
        self.armed_at = None
        self._stop_hooks()
        log.info("code red desativado")
        return "🟢 Code green: code red desativado." if was else "O code red não estava ativo."

    def on_input(self, injected: bool = False) -> bool:
        """Chamado por cada tecla/movimento do rato. True se bloqueou."""
        if not should_lock(self.armed_at, time.monotonic(), injected):
            return False
        self.armed_at = None  # uma só vez
        log.warning("code red: alguém mexeu no PC, a bloquear")
        threading.Thread(target=self._trigger, daemon=True, name="code-red").start()
        return True

    def _trigger(self):
        try:
            self._lock()
        finally:
            self._stop_hooks()
            for listener in list(self.listeners):
                try:
                    listener()
                except Exception:
                    log.exception("code red: erro num aviso")

    # --- ganchos do Windows --------------------------------------------------------

    def _start_hooks(self):
        if self._thread is not None and self._thread.is_alive():
            return
        ready = threading.Event()
        self._thread = threading.Thread(target=self._hook_loop, args=(ready,), daemon=True, name="code-red-hooks")
        self._thread.start()
        ready.wait(2)

    def _stop_hooks(self):
        import ctypes

        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive() and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT

    def _hook_loop(self, ready: threading.Event):
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.CallNextHookEx.restype = LRESULT
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        class KBD(ctypes.Structure):  # KBDLLHOOKSTRUCT
            _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_void_p)]

        class MOUSE(ctypes.Structure):  # MSLLHOOKSTRUCT
            _fields_ = [("pt", wintypes.POINT), ("data", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_void_p)]

        def keyboard(code, wparam, lparam):
            if code >= 0 and self.armed:
                self.on_input(bool(ctypes.cast(lparam, ctypes.POINTER(KBD)).contents.flags & 0x10))  # LLKHF_INJECTED
            return user32.CallNextHookEx(None, code, wparam, lparam)

        def mouse(code, wparam, lparam):
            if code >= 0 and self.armed:
                self.on_input(bool(ctypes.cast(lparam, ctypes.POINTER(MOUSE)).contents.flags & 0x01))  # LLMHF_INJECTED
            return user32.CallNextHookEx(None, code, wparam, lparam)

        keyboard_proc, mouse_proc = HOOKPROC(keyboard), HOOKPROC(mouse)  # têm de ficar referenciados
        module = kernel32.GetModuleHandleW(None)
        hooks = [user32.SetWindowsHookExW(13, keyboard_proc, module, 0),  # WH_KEYBOARD_LL
                 user32.SetWindowsHookExW(14, mouse_proc, module, 0)]  # WH_MOUSE_LL
        self._thread_id = kernel32.GetCurrentThreadId()
        ready.set()
        if not all(hooks):
            log.error("code red: não consegui vigiar o teclado/rato")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:  # mantém os ganchos vivos
            pass
        for hook in hooks:
            if hook:
                user32.UnhookWindowsHookEx(hook)


instance = Guard()  # um só, partilhado pela voz e pelo Telegram
