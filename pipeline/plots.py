"""Estilo dos gráficos dos notebooks (matplotlib), com a mesma paleta dos tokens do site.

Os notebooks são estáticos (o GitHub não executa JS), então o interativo fica no site e aqui é
matplotlib. Cores em `web/assets/style.css` (--attack, --defense, --gold…): mude nos dois lugares.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl

INK = "#16191f"
MUTED = "#6b7280"
GRID = "#e6e8ec"
ATTACK = "#d64545"
DEFENSE = "#2b7a83"
GOLD = "#c8962e"
NEUTRAL = "#4a5568"
REGION = {"americas": "#bc541a", "emea": "#bd9f1a", "pacific": "#3a81d7", "china": "#9a0027"}
TIER = {"vct": INK, "vcl": "#9aa3b2"}

DOCS_IMG = Path(__file__).resolve().parents[1] / "docs" / "img"


def setup() -> None:
    mpl.rcParams.update(
        {
            "figure.dpi": 110,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "axes.prop_cycle": mpl.cycler(color=[INK, ATTACK, DEFENSE, GOLD, NEUTRAL]),
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "font.size": 9,
            "font.family": "sans-serif",
        }
    )


def forest(ax, labels, values, lows, highs, *, null=None, colors=None, fmt="{:.3f}"):
    """Gráfico de floresta: estimativa e IC 95% por linha, com a linha do nulo."""
    y = range(len(labels))
    colors = colors or [INK] * len(labels)
    for i, (v, lo, hi, c) in enumerate(zip(values, lows, highs, colors, strict=True)):
        ax.plot([lo, hi], [i, i], color=c, lw=2, solid_capstyle="butt")
        ax.plot(v, i, "o", color=c, ms=5)
        ax.annotate(
            fmt.format(v),
            (hi, i),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=7,
            color=MUTED,
        )
    if null is not None:
        ax.axvline(null, color=MUTED, lw=0.8, ls="--")
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)


def save(fig, name: str) -> Path:
    """Exporta a figura para docs/img (README e post)."""
    DOCS_IMG.mkdir(parents=True, exist_ok=True)
    path = DOCS_IMG / name
    fig.savefig(path)
    return path
