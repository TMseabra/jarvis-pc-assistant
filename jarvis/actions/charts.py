"""Gráficos feitos no PC (matplotlib), guardados em .jarvis/graficos e enviados no Telegram."""

from datetime import datetime
from pathlib import Path

from jarvis.actions.screen import ATTACHMENT
from jarvis.config import PROJECT_ROOT

CHARTS_DIR = PROJECT_ROOT / ".jarvis" / "graficos"
_KINDS = {"bar", "barh", "line", "pie"}


def make_chart(title: str, labels: list[str], values: list[float], kind: str = "bar", ylabel: str = "",
               folder: Path = CHARTS_DIR) -> str:
    """Barras, barras horizontais, linha ou circular. Devolve o texto com o ficheiro anexado."""
    import matplotlib

    matplotlib.use("Agg")  # sem janela
    import matplotlib.pyplot as plt

    if not labels or len(labels) != len(values):
        raise ValueError("Para o gráfico preciso de nomes e valores em igual número.")
    values = [float(v) for v in values]
    kind = kind if kind in _KINDS else "bar"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"grafico_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    colors = plt.cm.cool([i / max(len(values) - 1, 1) for i in range(len(values))])
    if kind == "pie":
        ax.pie(values, labels=labels, autopct="%1.0f%%", colors=colors, startangle=90)
        ax.axis("equal")
    elif kind == "line":
        ax.plot(labels, values, marker="o", color="#00c8ff", linewidth=2.5)
        ax.fill_between(range(len(values)), values, alpha=0.15, color="#00c8ff")
    elif kind == "barh":
        bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1])
        ax.bar_label(bars, fmt="%g", padding=4)
    else:
        bars = ax.bar(labels, values, color=colors)
        ax.bar_label(bars, fmt="%g", padding=3)
        plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    if ylabel and kind != "pie":
        (ax.set_xlabel if kind == "barh" else ax.set_ylabel)(ylabel)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=14)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return f"Fiz o gráfico \"{title}\".\n{ATTACHMENT}{path}"
