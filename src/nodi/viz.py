"""Shared static-chart style (matplotlib). One palette for every PNG in the project."""
from __future__ import annotations

import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Bengali glyphs (৳) fall back to Nirmala UI (Windows) / Noto Sans Bengali when installed
plt.rcParams["font.family"] = ["DejaVu Sans", "Nirmala UI", "Noto Sans Bengali"]
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

INK, MUTED, ACCENT, ACCENT2, GRID = "#1f2937", "#6b7280", "#0f766e", "#b45309", "#e5e7eb"


def style(ax, title, subtitle=None):
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=INK, pad=16 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=8, color=MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def footer(fig):
    fig.text(0.01, 0.005, "Nodi Telecom is fictional. All data is synthetic.", fontsize=7, color=MUTED)
