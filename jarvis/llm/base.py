"""Interface comum aos providers de LLM."""

from dataclasses import dataclass, field


class LLMError(Exception):
    """Falha ao falar com o modelo (servidor em baixo, chave inválida, pedido bloqueado...)."""


@dataclass
class ToolCall:
    name: str
    args: dict
    id: str | None = None


@dataclass
class StepResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolResult:
    call: ToolCall
    content: str
    is_error: bool = False


class ChatProvider:
    """Guarda o histórico como uma lista de turnos (cada turno começa numa mensagem do
    utilizador) para poder descartar só os turnos mais antigos sem partir a conversa."""

    def __init__(self, system_prompt: str, tools: list[dict], max_turns: int = 10):
        self.system_prompt = system_prompt
        self.tools = tools
        self.max_turns = max_turns
        self.turns: list[list] = []

    def reset(self):
        self.turns = []

    def begin_turn(self, text: str):
        self.turns.append([self._user_message(text)])
        del self.turns[: -self.max_turns]

    def add_note(self, text: str):
        """Acrescenta uma nota (como mensagem do utilizador) ao turno atual."""
        self._append(self._user_message(text))

    def retry_without_history(self) -> "StepResult":
        """Volta a pedir o turno atual só com a mensagem do utilizador, sem os turnos anteriores
        nem a resposta que falhou. Com o mesmo pedido no histórico, modelos pequenos tendem a
        copiar a resposta anterior em vez de chamarem a ferramenta; sem histórico acertam."""
        previous, current = self.turns[:-1], self.turns[-1]
        fresh = [current[0]]
        self.turns = [fresh]
        try:
            return self.step()
        finally:
            self.turns = previous + [fresh]

    def discard_turn(self):
        if self.turns:
            self.turns.pop()

    def history(self) -> list:
        return [message for turn in self.turns for message in turn]

    def _append(self, message):
        self.turns[-1].append(message)

    def warmup(self):
        """Opcional: prepara o modelo antes do primeiro pedido."""

    # --- a implementar por cada provider -----------------------------------

    def _user_message(self, text: str):
        raise NotImplementedError

    def step(self) -> StepResult:
        """Chama o modelo com o histórico atual e acrescenta a resposta ao turno."""
        raise NotImplementedError

    def add_tool_results(self, results: list[ToolResult]):
        raise NotImplementedError
