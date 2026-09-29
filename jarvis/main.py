"""Ponto de entrada: `python -m jarvis.main [--modo texto|falar|maos-livres]`."""

import argparse
import re
import sys
import threading
import time

from jarvis.actions.desktop_chat import ChatRouter
from jarvis.actions.messaging import Messenger
from jarvis.actions.system import list_start_apps
from jarvis.brain import Brain
from jarvis.commands import split_commands
from jarvis.config import config
from jarvis.llm import LLMError
from jarvis.log import log
from jarvis.log import setup as setup_log
from jarvis.tools import ToolExecutor
from jarvis.ui import MODES, UI
from jarvis import updates
from jarvis.verify import verify
from jarvis.voice import strip_wake_word

EXIT_WORDS = {"sair", "adeus", "exit", "quit", "tchau"}
RESET_WORDS = {"esquece", "reset", "nova conversa"}
YES_WORDS = {"s", "sim", "y", "yes", "claro", "confirmo", "envia", "podes"}
# Mãos-livres: segundos, depois de o Jarvis responder, em que não é preciso dizer "Jarvis".
FOLLOW_UP_SECONDS = 8


def is_yes(answer: str | None) -> bool:
    words = (answer or "").lower().replace(",", " ").replace(".", " ").split()
    return bool(words) and words[0] in YES_WORDS


def _model_label() -> str:
    if config.provider == "gemini":
        return f"{config.gemini_model}"
    return f"Ollama · {config.ollama_model} (local)"


def _short_mic_name(name: str) -> str:
    """'Microfone (HyperX Quadcast)' -> 'HyperX Quadcast'."""
    m = re.match(r"^(?:Microfone|Microphone)\s*\((.*)\)$", name)
    return m.group(1) if m else name


def _load_voice(ui: UI):
    from jarvis.voice import Voice

    with ui.status("A carregar o reconhecimento de voz…"):
        return Voice(
            language=config.language,
            mic=config.mic,
            whisper_model=config.whisper_model,
            whisper_device=config.whisper_device,
            tts_voice=config.tts_voice,
            tts_engine=config.tts_engine,
            wake_threshold=config.wake_threshold or None,
            voice_style=config.voice_style,
            end_silence=config.end_silence,
            manual_silence=config.manual_silence,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis — assistente pessoal para o PC.")
    parser.add_argument("--modo", choices=[m[0] for m in MODES.values()], help="modo de interação")
    parser.add_argument("--voz", action="store_true", help="atalho para --modo maos-livres")
    parser.add_argument("--testar-jarvis", action="store_true", help="testa a deteção do 'Hey Jarvis'")
    parser.add_argument("--telegram", action="store_true", help="liga o Jarvis ao teu bot do Telegram")
    parser.add_argument("--classroom", action="store_true", help="liga o Jarvis ao teu Google Classroom")
    parser.add_argument("--servico", action="store_true", help="só o Telegram, em segundo plano")
    args = parser.parse_args(argv)

    if args.telegram:
        from jarvis.telegram_setup import run as setup_telegram

        return setup_telegram()
    if args.classroom:
        from jarvis.classroom_setup import run as setup_classroom

        return setup_classroom()
    if args.servico:
        setup_log()
        from jarvis.remote import run_service

        return run_service()

    if args.testar_jarvis:
        from jarvis.wake_test import run as test_wake

        return test_wake()

    # A consola do Windows nem sempre usa UTF-8 (acentos saem como "�").
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    setup_log()
    log.info("=== Jarvis arrancou (%s)", _model_label())
    ui = UI()
    ui.banner([("🧠", _model_label())])
    # Telegram logo ao arrancar (antes da escolha do modo), se estiver configurado e nenhum
    # serviço em segundo plano o estiver a ler.
    from jarvis.remote import TelegramController, claim_bot, telegram_configured

    if telegram_configured():
        if claim_bot():
            TelegramController(ui=ui).start_background()
            log.info("telegram: bot ligado nesta janela")
            ui.info("📱 Telegram ligado: podes mandar pedidos pelo teu bot.")
        else:
            ui.info("📱 O serviço do Telegram já está a correr em segundo plano.")

    mode = "maos-livres" if args.voz else (args.modo or ui.choose_mode())

    voice = None
    voice_out = True  # passa a False se a resposta falada falhar
    awake_until = 0.0  # mãos-livres: até quando aceita frases sem "Jarvis"
    update_notified = False
    if mode != "texto":
        try:
            voice = _load_voice(ui)
            device = "GPU" if voice.transcriber.device == "cuda" else "CPU"
            ui.banner([
                ("🧠", _model_label()),
                ("🎤", _short_mic_name(voice.mic_name)),
                ("🗣", f"{config.tts_voice.split('-')[-1].replace('Neural', '')} · Whisper {device}"),
            ])
        except Exception as exc:
            ui.error(f"Não consegui ativar a voz: {exc}\nVou continuar em modo texto.")
            mode = "texto"

    def say(text: str, seconds: float | None = None):
        nonlocal voice_out
        ui.reply(text, seconds)
        if voice and voice_out:
            try:
                with ui.status("A falar…", spinner="point"):
                    voice.say(text)
            except Exception as exc:
                voice_out = False
                ui.error(f"A resposta falada falhou ({exc}). Continuo só com texto.")

    def confirm(platform: str, contact: str, message: str) -> str | None:
        if mode != "maos-livres":
            return ui.confirm_send(platform, contact, message)
        with ui.paused_status():
            say(f"Vou enviar a {contact} no {platform}: {message}. Confirmas?")
            answer = listen("diz sim ou não", wait=8, show=False)
            ui.heard(answer or "(nada)")
        if is_yes(answer):
            return message
        ui.info("Envio cancelado.")
        return None

    def listen(hint: str, manual: bool = False, wait: float | None = 30, show: bool = True,
               hands_free: bool = False) -> str | None:
        """Grava (com indicador ao vivo) e transcreve."""
        nonlocal mode
        stop_hint = " · Enter para terminar" if manual else ""

        def progress(speaking: bool, seconds: float, silence: float):
            if speaking:
                pause = f" · pausa {silence:.0f}s" if silence >= 1 else ""
                ui.update_status(f"🔴 A gravar {seconds:.0f}s{pause}{stop_hint}")

        try:
            with ui.status(f"🎤 {hint}"):
                audio = voice.record(manual=manual, on_progress=progress, wait_for_speech=wait,
                                     hands_free=hands_free)
                if audio is None:
                    return None
                ui.update_status("A transcrever…")
                text = voice.transcribe(audio)
        except Exception as exc:  # microfone desligado, ocupado, ...
            ui.error(f"Problema com o microfone: {exc}")
            if mode == "maos-livres":
                ui.info("Passei para o modo Falar: escreve, ou carrega em Enter para tentar ouvir outra vez.")
                mode = "falar"
            return None
        log.info("ouvido: %r", text)
        if text and show:
            ui.heard(text)
        return text

    def next_hands_free_command() -> str | None:
        """No mãos-livres só reage a frases começadas por "Jarvis", exceto logo a seguir a responder."""
        nonlocal awake_until
        awake = time.monotonic() < awake_until
        text = listen("À escuta… diz “Hey Jarvis, …”" if not awake else "À escuta… podes continuar",
                      hands_free=True)
        if not text:
            return None
        command = strip_wake_word(text)
        if command is None and voice.wake_detected:
            # O openWakeWord ouviu "Hey Jarvis" mas o Whisper escreveu-o de outra forma
            # ("Ei, Travis..."): o pedido é a frase toda.
            command = text
        if command is None:
            return text if awake else None
        if not command:  # só "Jarvis"
            say("Sim?")
            awake_until = time.monotonic() + FOLLOW_UP_SECONDS
            return None
        return command

    executor = ToolExecutor(
        # WhatsApp/Discord pelas apps de desktop quando estão instaladas; Telegram pela web.
        messenger=ChatRouter(Messenger(config.browser_profile, notify=ui.info), config.messaging),
        confirm=confirm if config.confirm_send else None,
    )
    if config.confirm_ai_replies:
        executor.confirm_ai = confirm  # respostas escritas pelo Jarvis: mostrar antes de enviar
    try:
        turn_results: list = []  # resultados das ações do pedido atual, para a verificação final

        def on_result(result):
            ui.tool_result(result)
            turn_results.append(result)

        brain = Brain(executor=executor, on_tool=ui.tool, on_tool_result=on_result)
    except LLMError as exc:
        ui.error(str(exc))
        return 1

    # Carrega o modelo e a lista de apps em segundo plano, para o 1.º pedido ser rápido.
    threading.Thread(target=lambda: (brain.llm.warmup(), list_start_apps()), daemon=True).start()

    ui.help(mode)
    say("Olá, sou o Jarvis. Em que posso ajudar?")
    try:
        while True:
            if mode == "maos-livres":
                command = next_hands_free_command()
            else:
                command = ui.ask()
                if not command and mode == "falar":
                    command = listen("Fala quando quiseres… (Enter para terminar)", manual=True, wait=15)
            if not command:
                continue

            lowered = command.lower().strip(" .!?")
            if lowered in EXIT_WORDS:
                say("Até já.")
                break
            if lowered in RESET_WORDS:
                brain.reset()
                say("Pronto, começámos uma conversa nova.")
                continue

            # "abre o Spotify e a Steam e manda..." -> um pedido de cada vez.
            parts = split_commands(command)
            log.info("pedido: %r -> %s", command, parts)
            answers = []
            turn_results.clear()
            started = time.monotonic()
            for i, part in enumerate(parts, 1):
                label = f"A pensar… ({i}/{len(parts)}: {part})" if len(parts) > 1 else "A pensar…"
                try:
                    with ui.status(label):
                        answers.append(brain.handle(part))
                    log.info("resposta: %r", answers[-1])
                except LLMError as exc:
                    log.warning("erro do modelo: %s", exc)
                    ui.error(str(exc))
                    break
            if answers:
                # Verificação final: diz o que ficou feito e o que falhou, e que terminou.
                check = verify(turn_results)
                spoken = " ".join(answers)
                if check:
                    ui.verification(check)
                    log.info("verificação: %s", check.ui_line())
                    spoken = f"{spoken} {check.spoken()}"
                say(spoken, time.monotonic() - started)
                if not update_notified and updates.newer_code_available():
                    update_notified = True
                    ui.info("🔄 Há uma versão nova do Jarvis: fecha e abre o Jarvis para a usar.")
                awake_until = time.monotonic() + FOLLOW_UP_SECONDS
    except (KeyboardInterrupt, EOFError):
        ui.console.print()
    finally:
        executor.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
