"""Chart renderer — all matplotlib code lives here, never in metric providers."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from services.dashboard.base import MetricResult


def cleanup_old_charts(directory: Path | None = None, max_age_hours: float | None = None) -> int:
    """Delete PNG files older than max_age_hours from directory. Returns count removed."""
    from config import settings
    effective_dir = directory if directory is not None else settings.CHARTS_DIR
    effective_ttl = max_age_hours if max_age_hours is not None else settings.CHARTS_TTL_HOURS
    if not effective_dir.exists():
        return 0
    cutoff = time.time() - effective_ttl * 3600
    removed = 0
    for f in effective_dir.glob("*.png"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def render_chart(
    result: MetricResult,
    chart_type: str,
    charts_dir: Path | None = None,
) -> str:
    """Render result to a PNG and return its public URL.

    charts_dir overrides CHARTS_DIR from config (useful in tests).
    """
    from config import settings
    effective_dir = charts_dir if charts_dir is not None else settings.CHARTS_DIR
    effective_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_charts(effective_dir)

    filename = f"dashboard_{uuid.uuid4().hex[:8]}.png"
    filepath = effective_dir / filename
    style = settings.CHART_STYLE

    if chart_type == "pie":
        _render_pie(result, filepath, style)
    elif chart_type == "line":
        _render_line(result, filepath, style)
    elif chart_type == "horizontal_bar":
        _render_horizontal_bar(result, filepath, style)
    else:  # "bar" (default)
        _render_bar(result, filepath, style)

    return f"{settings.CHARTS_BASE_URL}/static/charts/{filename}"


# ---- Private rendering helpers ----------------------------------------------

def _apply_dark_style(ax, style: dict, grid_axis: str = "y") -> None:
    ax.set_facecolor(style["ax_facecolor"])
    ax.tick_params(colors=style["tick_color"])
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(style["spine_color"])
    ax.grid(axis=grid_axis, color=style["grid_color"], alpha=0.5, linestyle="--")


def _add_bar_labels(ax, bars, values: list, style: dict, sign_aware: bool = False) -> None:
    for bar, val in zip(bars, values):
        if val == 0:
            continue
        if sign_aware and val < 0:
            offset, fw = -12, "bold"
        else:
            offset, fw = 3, "normal"
        ax.annotate(
            str(val),
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, offset),
            textcoords="offset points",
            ha="center",
            color=style["text_color"],
            fontsize=8,
            fontweight=fw,
        )


def _shorten_label(label: str) -> str:
    return label.replace("COMPUTER-", "COMP\n")


def _render_bar(result: MetricResult, filepath: Path, style: dict) -> None:
    rows = result.rows
    short_labels = [_shorten_label(r["label"]) for r in rows]
    x = np.arange(len(rows))
    series = result.series if result.series else ["value"]
    has_secondary = bool(result.secondary_series)
    colors = style["colors"]

    fig, axes = plt.subplots(1, 2 if has_secondary else 1, figsize=(16 if has_secondary else 9, 6))
    fig.patch.set_facecolor(style["fig_facecolor"])
    ax1 = axes[0] if has_secondary else axes

    # Primary panel — grouped bars (one group per row, one bar per series field)
    n = len(series)
    width = 0.8 / n
    offsets = np.linspace(-(n - 1) * width / 2, (n - 1) * width / 2, n)
    for i, (field_name, offset) in enumerate(zip(series, offsets)):
        vals = [r.get(field_name, 0) for r in rows]
        bars = ax1.bar(
            x + offset, vals, width,
            label=field_name.replace("_", " ").title(),
            color=colors[i % len(colors)],
            alpha=0.9,
        )
        _add_bar_labels(ax1, bars, vals, style)

    panel_title = result.primary_title if has_secondary else result.title
    ax1.set_title(panel_title, color=style["text_color"], fontsize=13, fontweight="bold", pad=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(short_labels, color=style["tick_color"], fontsize=9)
    ax1.set_ylabel(result.y_label or "Count", color=style["tick_color"])
    if result.x_label:
        ax1.set_xlabel(result.x_label, color=style["tick_color"])
    _apply_dark_style(ax1, style)
    if n > 1:
        ax1.legend(
            facecolor=style["fig_facecolor"],
            edgecolor=style["spine_color"],
            labelcolor=style["text_color"],
            fontsize=9,
        )

    # Secondary panel — sign-coloured single-series bars (e.g. shortage/surplus)
    if has_secondary:
        ax2 = axes[1]
        sec_field = result.secondary_series[0]
        sec_vals = [r.get(sec_field, 0) for r in rows]
        bar_colors = [
            style["shortage_color"] if v > 0 else style["surplus_color"]
            for v in sec_vals
        ]
        bars2 = ax2.bar(x, sec_vals, color=bar_colors, alpha=0.9)
        ax2.set_title(
            result.secondary_title or sec_field.replace("_", " ").title(),
            color=style["text_color"], fontsize=13, fontweight="bold", pad=12,
        )
        ax2.set_xticks(x)
        ax2.set_xticklabels(short_labels, color=style["tick_color"], fontsize=9)
        ax2.axhline(0, color="#78909c", linewidth=1)
        ax2.set_ylabel("Units", color=style["tick_color"])
        _apply_dark_style(ax2, style)
        _add_bar_labels(ax2, bars2, sec_vals, style, sign_aware=True)
        patches = [
            mpatches.Patch(color=style["shortage_color"], label="Shortage (needs replenishment)"),
            mpatches.Patch(color=style["surplus_color"], label="Surplus (overstocked)"),
        ]
        ax2.legend(
            handles=patches,
            facecolor=style["fig_facecolor"],
            edgecolor=style["spine_color"],
            labelcolor=style["text_color"],
            fontsize=9,
        )
        fig.suptitle(result.title, color=style["text_color"], fontsize=16, fontweight="bold", y=1.01)

    plt.tight_layout()
    plt.savefig(filepath, dpi=_chart_dpi(), bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def _render_horizontal_bar(result: MetricResult, filepath: Path, style: dict) -> None:
    rows = result.rows
    labels = [_shorten_label(r["label"]) for r in rows]
    field_name = (result.series or ["value"])[0]
    vals = [r.get(field_name, 0) for r in rows]
    y = np.arange(len(rows))
    colors = style["colors"]

    fig, ax = plt.subplots(figsize=(10, max(4, len(rows) * 0.5 + 2)))
    fig.patch.set_facecolor(style["fig_facecolor"])
    bars = ax.barh(y, vals, color=colors[0], alpha=0.9)

    for bar, val in zip(bars, vals):
        if val == 0:
            continue
        ax.annotate(
            str(val),
            xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(3, 0),
            textcoords="offset points",
            va="center",
            color=style["text_color"],
            fontsize=8,
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style["tick_color"], fontsize=9)
    ax.set_xlabel(result.y_label or "Count", color=style["tick_color"])
    ax.set_title(result.title, color=style["text_color"], fontsize=13, fontweight="bold", pad=12)
    _apply_dark_style(ax, style, grid_axis="x")
    plt.tight_layout()
    plt.savefig(filepath, dpi=_chart_dpi(), bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def _render_line(result: MetricResult, filepath: Path, style: dict) -> None:
    rows = result.rows
    labels = [r["label"] for r in rows]
    field_name = (result.series or ["value"])[0]
    vals = [r.get(field_name, 0) for r in rows]
    x = np.arange(len(rows))
    colors = style["colors"]

    fig, ax = plt.subplots(figsize=(max(10, len(rows) * 0.8 + 2), 6))
    fig.patch.set_facecolor(style["fig_facecolor"])
    ax.plot(x, vals, color=colors[0], linewidth=2, marker="o", markersize=5)
    ax.fill_between(x, vals, alpha=0.2, color=colors[0])

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=style["tick_color"], fontsize=8, rotation=45, ha="right")
    ax.set_ylabel(result.y_label or "Count", color=style["tick_color"])
    if result.x_label:
        ax.set_xlabel(result.x_label, color=style["tick_color"])
    ax.set_title(result.title, color=style["text_color"], fontsize=13, fontweight="bold", pad=12)
    _apply_dark_style(ax, style)
    plt.tight_layout()
    plt.savefig(filepath, dpi=_chart_dpi(), bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def _render_pie(result: MetricResult, filepath: Path, style: dict) -> None:
    rows = result.rows
    labels = [r["label"] for r in rows]
    vals = [r.get("value", 0) for r in rows]
    colors = style["colors"]
    wedge_colors = [colors[i % len(colors)] for i in range(len(rows))]

    fig, ax = plt.subplots(figsize=(8, 8))
    fig.patch.set_facecolor(style["fig_facecolor"])
    _, _, autotexts = ax.pie(
        vals, labels=labels, colors=wedge_colors,
        autopct="%1.1f%%", startangle=140,
        textprops={"color": style["text_color"]},
    )
    for at in autotexts:
        at.set_color(style["text_color"])
    ax.set_title(result.title, color=style["text_color"], fontsize=14, fontweight="bold", pad=16)
    plt.tight_layout()
    plt.savefig(filepath, dpi=_chart_dpi(), bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def _chart_dpi() -> int:
    from config import settings
    return settings.CHART_DPI