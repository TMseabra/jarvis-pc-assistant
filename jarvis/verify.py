"""Verificação no fim de cada pedido: as ações correram mesmo bem?

Cada ferramenta já confirma o seu resultado (o Spotify começou a tocar? a conversa aberta é
a da pessoa certa?). Aqui juntamos tudo e dizemos claramente o que ficou feito e o que falhou,
para o Jarvis nunca terminar a dizer "feito" quando algo correu mal.
"""

import re
from dataclasses import dataclass

from jarvis.llm import ToolResult

# Resultados que, mesmo sem erro técnico, dizem que a ação não aconteceu.
_FAILED_TEXT = re.compile(
    r"^(?:Não |Erro|O .+ recusou|Carreguei .+, mas|Abri a pesquisa .+ mas|O Spotify não)|"
    r"NÃO foi enviada|não consegui",
    re.IGNORECASE,
)


def failed(result: ToolResult) -> bool:
    return result.is_error or bool(_FAILED_TEXT.search(result.content.strip()))


@dataclass
class Verification:
    total: int
    failures: list[ToolResult]

    @property
    def ok(self) -> bool:
        return not self.failures

    def ui_line(self) -> str:
        if self.ok:
            return f"Verificado: {self.total}/{self.total} ações correram bem."
        return f"Verificado: {self.total - len(self.failures)}/{self.total} ações correram bem."

    def spoken(self) -> str:
        if self.ok:
            return "Terminei, correu tudo bem."
        first = self.failures[0].content.split("\n", 1)[0].rstrip(".")
        more = f" e mais {len(self.failures) - 1}" if len(self.failures) > 1 else ""
        return f"Terminei, mas nem tudo correu bem: {first}{more}."


def verify(results: list[ToolResult]) -> Verification | None:
    """None se o pedido não teve ações (ex.: uma pergunta de conhecimento geral)."""
    if not results:
        return None
    return Verification(total=len(results), failures=[r for r in results if failed(r)])
