"""Build docs/Project_Report.pdf from docs/Project_Report.md, with figures
computed from the raw score files in results/evaluation/.

    python docs/build_report.py            # metrics summary + figures + PDF
    python docs/build_report.py --metrics  # print the metrics only

Needs: matplotlib, reportlab (pip install -r docs/requirements-docs.txt).
The Markdown subset it understands: # / ## / ### headings, paragraphs,
"- " bullets, "> " notes, | tables |, ![caption](path) images,
**bold**, *italic*, `code`, and a line "<<<pagebreak>>>".
"""
from __future__ import annotations

import csv
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "results" / "evaluation"
DOCS = ROOT / "docs"
FIG = DOCS / "figures"
HORIZONS = (5, 10, 20)
DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
RATINGS = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]

# Runs scored by evaluate.py (cells_<name>.csv) that the report uses
RUNS = {
    "E1": ("baseline36_final", "Qwen3.6-27B, first evaluation (5 stocks, Jul-Oct 2026)"),
    "E3q": ("ds1", "Qwen3.6-27B, test set v1"),
    "E3g": ("gemma_ds1", "gemma-4-12B, test set v1"),
    "E5": ("gemma_ind_ds1", "gemma-4-12B + extra indicators, test set v1"),
    "A":("A", "Arm A: baseline"),
    "B": ("B", "Arm B: baseline repeat"),
    "C": ("C", "Arm C: extra indicators"),
}

# Colours: dataviz reference palette (categorical slots 1-2, neutral reference, diverging blue/red)
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#898781"
INK, INK2, GRID, AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
RATING_COLOURS = {"Buy": "#1c5cab", "Overweight": "#86b6ef", "Hold": "#d8d7d0",
                  "Underweight": "#e34948", "Sell": "#9e2a2a"}


# ---------------------------------------------------------------- metrics
def load_cells(name: str) -> dict:
    """{(ticker, date): {"rating", "group", h: alpha, f"raw{h}": raw}}"""
    cells: dict = {}
    path = EVAL / f"cells_{name}.csv"
    if not path.exists():
        return cells
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = cells.setdefault((r["ticker"], r["date"]),
                                 {"rating": r["rating"], "group": r.get("group", "")})
            if r["alpha"] not in ("", None):
                c[int(r["h"])] = float(r["alpha"])
                c[f"raw{r['h']}"] = float(r["raw"])
    return cells


def p_upper(k: int, n: int) -> float:
    """One-sided binomial p-value P(X >= k) for a fair coin (as in evaluate.py)."""
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n if n else float("nan")


def score(cells: dict, h: int, group: str | None = None) -> dict:
    rows = [c for c in cells.values() if h in c and (group is None or c["group"] == group)]
    directional = [c for c in rows if DIRECTION.get(c["rating"], 0) != 0]
    hits = sum(1 for c in directional if DIRECTION[c["rating"]] * c[h] > 0)
    raw_hits = sum(1 for c in directional if DIRECTION[c["rating"]] * c[f"raw{h}"] > 0)
    n = len(directional)
    return {
        "n_all": len(rows), "n": n, "hits": hits,
        "hit": hits / n if n else float("nan"), "p": p_upper(hits, n),
        "raw_hit": raw_hits / n if n else float("nan"),
        "always_buy": sum(1 for c in rows if c[h] > 0) / len(rows) if rows else float("nan"),
        "always_uw": sum(1 for c in rows if c[h] < 0) / len(rows) if rows else float("nan"),
        "captured": (sum(DIRECTION[c["rating"]] * c[h] for c in directional) / n) if n else float("nan"),
        "bearish": sum(1 for c in rows if DIRECTION.get(c["rating"], 0) < 0) / len(rows) if rows else float("nan"),
    }


def mix(cells: dict) -> Counter:
    return Counter(c["rating"] for c in cells.values())


def print_metrics(data: dict) -> None:
    for key, (name, label) in RUNS.items():
        cells = data[key]
        if not cells:
            print(f"{key} {name}: no cells file")
            continue
        m = mix(cells)
        print(f"\n{key} {name} - {label}: {len(cells)} decisions, mix {dict(m)}")
        for h in HORIZONS:
            s = score(cells, h)
            print(f"  {h:>2}d  hit {s['hits']}/{s['n']} = {s['hit']:.0%}  p={s['p']:.2f}  raw {s['raw_hit']:.0%}"
                  f"  alwaysBuy {s['always_buy']:.0%}  alwaysUW {s['always_uw']:.0%}"
                  f"  captured {s['captured']:+.2%}  scored {s['n_all']}")
        groups = sorted({c["group"] for c in cells.values() if c["group"]})
        for g in groups:
            for h in HORIZONS:
                s = score(cells, h, g)
                print(f"    {g:<8}{h:>2}d  hit {s['hits']}/{s['n']} = {s['hit']:.0%}  p={s['p']:.2f}"
                      f"  raw {s['raw_hit']:.0%}  alwaysBuy {s['always_buy']:.0%}  bearish {s['bearish']:.0%}")


# ---------------------------------------------------------------- figures
def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def fig_hit_rates(data: dict, path: Path) -> None:
    import matplotlib.pyplot as plt
    q, g = data["E3q"], data["E3g"]
    fig, ax = plt.subplots(figsize=(6.6, 2.9), dpi=200)
    _style(ax)
    width, gap = 0.26, 0.02
    for i, h in enumerate(HORIZONS):
        sq, sg = score(q, h), score(g, h)
        bars = [(sq["hit"], BLUE, None, f"{sq['hits']}/{sq['n']}"),
                (sg["hit"], ORANGE, None, f"{sg['hits']}/{sg['n']}") if g else (float("nan"), ORANGE, None, ""),
                (sq["always_buy"], "white", "////", "")]
        for j, (v, colour, hatch, frac) in enumerate(bars):
            if math.isnan(v):
                continue
            x = i + (j - 1) * (width + gap)
            ax.bar(x, v, width, color=colour, edgecolor=GREY if hatch else colour,
                   hatch=hatch, linewidth=0.8)
            ax.text(x, v + 0.015, f"{v:.0%}", ha="center", va="bottom", fontsize=8, color=INK,
                    bbox=dict(boxstyle="square,pad=0.25", fc="white", ec="none"))
            if frac:
                ax.text(x, 0.02, frac, ha="center", va="bottom", fontsize=6.5, color="white")
    ax.axhline(0.5, color=INK2, linewidth=0.9, linestyle=(0, (4, 3)))
    ax.set_xticks(range(3), [f"{h} trading days" for h in HORIZONS])
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_ylabel("Alpha hit rate", fontsize=8.5, color=INK2)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label="Qwen3.6-27B agent"),
                       Patch(color=ORANGE, label="gemma-4-12B agent"),
                       Patch(facecolor="white", edgecolor=GREY, hatch="////", label="Always-Buy baseline"),
                       Line2D([], [], color=INK2, linewidth=0.9, linestyle=(0, (4, 3)), label="Coin flip (50%)")],
              fontsize=7.5, frameon=False, loc="upper left", ncol=4, bbox_to_anchor=(0, 1.13))
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def fig_rating_mix(data: dict, path: Path) -> None:
    import matplotlib.pyplot as plt
    rows = [("E1", "Qwen3.6, first evaluation (36)"),
            ("E3q", "Qwen3.6, test set (20)"),
            ("E3g", "gemma, test set (20)"),
            ("E5", "gemma + indicators, test set (20)")]
    rows = [r for r in rows if data[r[0]]]
    fig, ax = plt.subplots(figsize=(6.6, 0.55 + 0.42 * len(rows)), dpi=200)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0, labelsize=8, colors=INK2)
    for y, (key, label) in enumerate(reversed(rows)):
        m, total, left = mix(data[key]), len(data[key]), 0.0
        for rating in RATINGS:
            share = m.get(rating, 0) / total
            if share == 0:
                continue
            ax.barh(y, share, left=left, color=RATING_COLOURS[rating], edgecolor="white", linewidth=1.5, height=0.62)
            if share >= 0.07:
                ink = "white" if rating in ("Buy", "Underweight", "Sell") else INK
                ax.text(left + share / 2, y, f"{m[rating]}", ha="center", va="center", fontsize=7.5, color=ink)
            left += share
    ax.set_yticks(range(len(rows)), [r[1] for r in reversed(rows)])
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=RATING_COLOURS[r], label=r) for r in RATINGS],
              fontsize=7.5, frameon=False, ncol=5, loc="lower left", bbox_to_anchor=(0, 1.0))
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def fig_agent_garden(path: Path) -> None:
    """Where the finance agent sits in Agent Garden: agents -> AI gateway -> Model Garden."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig, ax = plt.subplots(figsize=(7.2, 3.1), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 43)
    ax.axis("off")

    def group(x, y, w, h, label):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.5", fc="#f6f6f4", ec=GRID, lw=0.8))
        ax.text(x + 1.0, y + h - 0.8, label, ha="left", va="top", fontsize=6.6, color=INK2, style="italic")

    def box(x, y, w, h, title, sub="", fc="#ffffff", ec=AXIS, ls="-"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.0", fc=fc, ec=ec, lw=0.9, ls=ls))
        if sub:
            ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=6.9, color=INK, fontweight="bold")
            ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=5.9, color=INK2)
        else:
            ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=6.9, color=INK, fontweight="bold")

    def arrow(x1, y1, x2, y2, color=INK2, ls="-"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=0.9, ls=ls, mutation_scale=8, shrinkA=0, shrinkB=0))

    def label(x, y, text, ha="center", color=INK2):
        ax.text(x, y, text, fontsize=5.9, color=color, ha=ha, va="center",
                bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))

    # Agents
    group(1, 9, 24, 33, "Agent Garden agents")
    for k, name in enumerate(["Coding agent", "Healthcare agent", "Banking agent"]):
        box(3, 31 - k * 6.3, 20, 4.6, name)
    box(3, 11.2, 20, 5.6, "Finance agent", "this report", fc="#fff4ef", ec=ORANGE)

    # Gateway
    group(31, 9, 34, 33, "AI gateway (partner group)")
    box(34, 27, 28, 9, "LiteLLM", "API keys, rate limits, spend tracking", fc="#eef4fc", ec=BLUE)
    box(34, 12.5, 28, 9.5, "vLLM Semantic Router", "judges each request and picks a model", fc="#eef4fc", ec=BLUE)
    arrow(48, 26.8, 48, 22.2)
    label(53.5, 24.5, "2 judge")

    # Model Garden
    group(71, 9, 28, 33, "Model Garden")
    box(73, 28.5, 24, 7.5, "gemma-4-12B", "small model: easy requests")
    box(73, 19.5, 24, 7.5, "Qwen3.6-27B", "large model: medium and hard requests")
    box(73, 11, 24, 6.8, "Planned", "a separate medium model", ls="--")

    # Planned flow
    arrow(25.3, 31.5, 33.8, 31.5)
    label(29.5, 33.5, "1 request")
    arrow(62.2, 17.2, 72.8, 31.5)
    arrow(62.2, 17.2, 72.8, 23.2)
    label(67.5, 27.4, "3 route")
    label(48, 10.6, "4-5 the answer returns through the gateway")

    # What our runs did: direct calls, gateway not connected
    ax.plot([13, 13, 85, 85], [11.0, 4.0, 4.0, 8.6], color=ORANGE, lw=1.0, ls=(0, (4, 2)))
    arrow(85, 7.0, 85, 8.8, color=ORANGE)
    label(49, 4.0, "our runs (E1-E5): direct calls to the model endpoints; gateway not yet connected", color=ORANGE)

    fig.tight_layout(pad=0.2)
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def fig_architecture(path: Path) -> None:
    """Component and data-flow diagram of the deployed system."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig, ax = plt.subplots(figsize=(7.2, 5.3), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 74)
    ax.axis("off")

    def box(x, y, w, h, title, lines=(), fc="#ffffff", ec=AXIS):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.0", fc=fc, ec=ec, lw=0.9))
        ax.text(x + w / 2, y + h - 1.3, title, ha="center", va="top", fontsize=6.9, color=INK, fontweight="bold")
        for k, line in enumerate(lines):
            ax.text(x + w / 2, y + h - 4.3 - k * 2.45, line, ha="center", va="top", fontsize=5.9, color=INK2)

    def group(x, y, w, h, label):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.5", fc="#f6f6f4", ec=GRID, lw=0.8))
        ax.text(x + 1.0, y + h - 0.7, label, ha="left", va="top", fontsize=6.3, color=INK2, style="italic")

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=INK2, lw=0.9, mutation_scale=8, shrinkA=0, shrinkB=0))

    def label(x, y, text, ha="left"):
        ax.text(x, y, text, fontsize=5.8, color=INK2, ha=ha, va="center",
                bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))

    # Compute layer
    group(1, 60, 98, 13, "Lab GPU server: Slurm job on slurm-comp01  |  trust boundary: reachable only through the SSH tunnel")
    box(4, 61.3, 44, 8.6, "vLLM 0.28, OpenAI-compatible API", ["NVIDIA A100 80 GB, one model per job",
                                                                  "tool calling and structured output on"], fc="#eef4fc", ec=BLUE)
    box(52, 61.3, 44, 8.6, "Served models (one at a time)", ["Qwen3.6-27B on port 9000",
                                                              "gemma-4-12B-it on port 9003"], fc="#eef4fc", ec=BLUE)
    ax.annotate("", xy=(50, 50.2), xytext=(50, 60.4),
                arrowprops=dict(arrowstyle="<|-|>", color=INK2, lw=0.9, mutation_scale=8, shrinkA=0, shrinkB=0))
    label(51.2, 56.6, "model calls over an SSH tunnel (key authentication)")
    label(51.2, 53.9, "localhost:9000 / 9003 → slurm-comp01")

    # Agent graph
    group(1, 18.5, 98, 31.5, "Researcher laptop (Windows 11, Python 3.12): TradingAgents 0.7.1 on LangGraph, 12 LLM agents per decision")
    box(2.5, 21, 15, 25, "Data tools", ["Yahoo Finance:", "prices, indicators", "SEC EDGAR filings,", "as filed by the date",
                                       "Yahoo news *", "Reddit *, FRED *", "* failed or off for", "past dates"])
    box(21, 21, 15, 25, "Analyst team", ["Market", "Social sentiment", "News", "Fundamentals", "",
                                        "each calls its tools", "(up to 20 rounds)"])
    box(39.5, 34.5, 18, 11.5, "Research debate", ["Bull ↔ Bear", "Research Manager"])
    box(39.5, 21, 18, 10, "Trader", ["trade proposal"])
    box(61, 34.5, 18, 11.5, "Risk debate", ["Aggressive", "Neutral", "Conservative"])
    box(61, 21, 18, 10, "Portfolio Manager", ["PortfolioDecision", "(structured output)"], fc="#fff4ef", ec=ORANGE)
    box(82.5, 21, 15, 25, "Final rating", ["Buy", "Overweight", "Hold", "Underweight", "Sell", "",
                                          "+ written reports"], fc="#fff4ef", ec=ORANGE)
    arrow(17.7, 33.5, 20.8, 33.5)
    arrow(36.2, 40, 39.3, 40)
    arrow(48.5, 34.3, 48.5, 31.2)
    arrow(57.7, 26, 60.8, 38)
    arrow(70, 34.3, 70, 31.2)
    arrow(79.2, 26, 82.3, 30)

    # Evaluation harness (right to left: log -> scoring -> reports)
    group(1, 1, 98, 15.5, "Evaluation harness added by this project")
    box(2.5, 2.5, 23, 11.5, "Test set, launchers", ["dataset/test_set_v1.csv", "launch_dataset.ps1"])
    box(28.5, 2.5, 18.5, 11.5, "Reports", ["report_<run>.md", "cells_<run>.csv"])
    box(50.5, 2.5, 25, 11.5, "evaluate.py, compare.py", ["entry: next close after the date", "exit: +5 / 10 / 20 sessions",
                                                          "alpha = stock return − SPY"])
    box(78.5, 2.5, 19, 11.5, "Memory log", ["one per run:", "[date | ticker | rating]"])
    arrow(78.3, 8.3, 75.7, 8.3)
    arrow(50.3, 8.3, 47.2, 8.3)
    arrow(90, 20.8, 90, 14.2)
    label(91, 17.2, "rating")
    arrow(13.5, 14.2, 13.5, 20.8)
    label(14.5, 17.2, "ticker + date, one run per sample")
    fig.savefig(path, facecolor="white", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


# ---------------------------------------------------------------- PDF
def build_pdf(md_path: Path, pdf_path: Path, meta: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak,
                                    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

    fonts = Path("C:/Windows/Fonts")
    if (fonts / "segoeui.ttf").exists():
        pdfmetrics.registerFont(TTFont("Body", str(fonts / "segoeui.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Bold", str(fonts / "segoeuib.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Italic", str(fonts / "segoeuii.ttf")))
        pdfmetrics.registerFont(TTFont("Body-BoldItalic", str(fonts / "segoeuiz.ttf")))
        pdfmetrics.registerFont(TTFont("Mono", str(fonts / "consola.ttf")))
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-BoldItalic")
        body, bold, mono = "Body", "Body-Bold", "Mono"
    else:  # non-Windows fallback (limited glyphs)
        body, bold, mono = "Helvetica", "Helvetica-Bold", "Courier"

    ink, ink2 = colors.HexColor(INK), colors.HexColor(INK2)
    st = {
        "title": ParagraphStyle("title", fontName=bold, fontSize=17, leading=21, textColor=ink, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", fontName=body, fontSize=10, leading=13, textColor=ink2, spaceAfter=10),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=12.5, leading=16, textColor=ink, spaceBefore=10, spaceAfter=4,
                             keepWithNext=1),
        "h3": ParagraphStyle("h3", fontName=bold, fontSize=10, leading=13, textColor=ink, spaceBefore=6, spaceAfter=2,
                             keepWithNext=1),
        "p": ParagraphStyle("p", fontName=body, fontSize=9, leading=12.2, textColor=ink, spaceAfter=5, alignment=TA_LEFT),
        # A short bold label ("**Risks.**") or a line ending in ":" stays with what follows
        "label": ParagraphStyle("label", fontName=body, fontSize=9, leading=12.2, textColor=ink, spaceAfter=5,
                                alignment=TA_LEFT, keepWithNext=1),
        "note": ParagraphStyle("note", fontName=body, fontSize=8.6, leading=11.5, textColor=ink2, leftIndent=8,
                               borderPadding=(4, 6, 4, 6), backColor=colors.HexColor("#f6f6f4"), spaceAfter=7, spaceBefore=2),
        "cell": ParagraphStyle("cell", fontName=body, fontSize=7.7, leading=9.6, textColor=ink),
        "cellh": ParagraphStyle("cellh", fontName=bold, fontSize=7.7, leading=9.6, textColor=ink),
        "caption": ParagraphStyle("caption", fontName=body, fontSize=8, leading=10.5, textColor=ink2, spaceAfter=8),
        "bullet": ParagraphStyle("bullet", fontName=body, fontSize=9, leading=12, textColor=ink),
        "num": ParagraphStyle("num", fontName=body, fontSize=9, leading=12.2, textColor=ink, leftIndent=12,
                              firstLineIndent=-12, spaceAfter=3),
    }

    def inline(text: str) -> str:
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"`([^`]+)`", lambda m: f'<font face="{mono}" size="8">{m.group(1)}</font>', text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<i>\1</i>", text)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#1c5cab">\1</link>', text)
        for key, value in meta.items():
            text = text.replace("{{" + key + "}}", value)
        return text

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=meta.get("title", "Project Report"), author=meta.get("members", ""))
    frame_w = A4[0] - 4 * cm

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(body, 7.5)
        canvas.setFillColor(ink2)
        canvas.drawString(2 * cm, 1.1 * cm, meta.get("footer", ""))
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"{d.page}")
        canvas.restoreState()

    lines = md_path.read_text(encoding="utf-8").splitlines()
    story, para, bullets, table = [], [], [], []

    def take_kept():
        """Pop the trailing headings/labels that must stay with the next block."""
        kept = []
        while story and getattr(getattr(story[-1], "style", None), "keepWithNext", 0):
            kept.insert(0, story.pop())
        return kept

    def flush_para():
        if para:
            text = " ".join(para)
            is_label = len(text) < 120 and (text.startswith("**") or text.endswith(":"))
            story.append(Paragraph(inline(text), st["label" if is_label else "p"]))
            para.clear()

    def flush_bullets():
        if bullets:
            lst = ListFlowable([ListItem(Paragraph(inline(b), st["bullet"]), leftIndent=10, value="•")
                                for b in bullets], bulletType="bullet", start="•", leftIndent=10,
                               bulletFontSize=8, spaceAfter=5)
            kept = take_kept() if len(bullets) <= 5 else []
            story.append(KeepTogether(kept + [lst]) if kept else lst)
            bullets.clear()

    def flush_table():
        if not table:
            return
        rows = [[c.strip().replace("@@PIPE@@", "|") for c in r.strip().replace(chr(92) + "|", "@@PIPE@@").strip("|").split("|")]
                for r in table if not re.match(r"^\|?\s*:?-{2,}", r.strip())]
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        # Keep "57% (16/28)" on one line: join the rate and its count with a non-breaking space
        rows = [[re.sub(r"(\d%) (\(\d+/\d+\))", "\\1\xa0\\2", c) for c in r] for r in rows]
        def plain(c):
            return re.sub(r"[*`]", "", c)
        # Minimum width: the longest word (paths capped) must fit; desired width: content length.
        # Split on ordinary spaces only, so non-breaking spaces keep their words together.
        min_w = [min(max(len(w) for r in rows for w in (re.split(r"[ \t]+", plain(r[i])) or [""])), 22) * 4.6 + 9
                 for i in range(ncol)]
        desired = [max(6, max(min(len(plain(r[i])), 70) for r in rows)) for i in range(ncol)]
        widths = [frame_w * d / sum(desired) for d in desired]
        for _ in range(4):
            short = [i for i in range(ncol) if widths[i] < min_w[i]]
            if not short:
                break
            deficit = sum(min_w[i] - widths[i] for i in short)
            for i in short:
                widths[i] = min_w[i]
            spare = [i for i in range(ncol) if i not in short and widths[i] > min_w[i]]
            pool = sum(widths[i] - min_w[i] for i in spare)
            for i in spare:
                widths[i] -= deficit * (widths[i] - min_w[i]) / pool if pool else 0
        data = [[Paragraph(inline(c), st["cellh" if k == 0 else "cell"]) for c in r] for k, r in enumerate(rows)]
        t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efeeea")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(AXIS)),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor(GRID)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.5), ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
        ]))
        if len(rows) <= 7:   # short tables are not split, and stay with their heading or label
            story.append(KeepTogether(take_kept() + [t]))
        else:
            story.append(t)
        story.append(Spacer(1, 7))
        table.clear()

    def flush_all():
        flush_para(); flush_bullets(); flush_table()

    for line in lines:
        s = line.rstrip()
        if s.startswith("|"):
            flush_para(); flush_bullets(); table.append(s); continue
        flush_table()
        if not s.strip():
            flush_para(); flush_bullets(); continue
        if s.strip() == "<<<pagebreak>>>":
            flush_all(); story.append(PageBreak()); continue
        if s.startswith("# "):
            flush_all(); story.append(Paragraph(inline(s[2:]), st["title"])); continue
        if s.startswith("## "):
            flush_all(); story.append(Paragraph(inline(s[3:]), st["h2"])); continue
        if s.startswith("### "):
            flush_all(); story.append(Paragraph(inline(s[4:]), st["h3"])); continue
        if s.startswith("> "):
            flush_all(); story.append(Paragraph(inline(s[2:]), st["note"])); continue
        m = re.match(r"^!\[(.*)\]\((.+)\)$", s.strip())
        if m:
            flush_all()
            img_path = (md_path.parent / m.group(2)).resolve()
            from reportlab.lib.utils import ImageReader
            iw, ih = ImageReader(str(img_path)).getSize()
            w = frame_w
            story.append(KeepTogether([Image(str(img_path), width=w, height=w * ih / iw),
                                       Paragraph(inline(m.group(1)), st["caption"])]))
            continue
        if s.lstrip().startswith("- "):
            flush_para(); bullets.append(s.lstrip()[2:]); continue
        num = re.match(r"^(\d+)\. (.+)$", s.strip())
        if num:  # numbered item: its own paragraph with a hanging number
            flush_all()
            story.append(Paragraph(f"{num.group(1)}.&nbsp;&nbsp;" + inline(num.group(2)), st["num"]))
            continue
        if bullets and line.startswith("  "):
            bullets[-1] += " " + s.strip(); continue
        if s.startswith("*") and s.endswith("*") and not para and not s.startswith("**"):
            flush_all(); story.append(Paragraph(inline(s), st["subtitle"])); continue
        para.append(s.strip())
    flush_all()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    data = {key: load_cells(name) for key, (name, _) in RUNS.items()}
    print_metrics(data)
    if "--metrics" in sys.argv:
        return
    FIG.mkdir(parents=True, exist_ok=True)
    fig_agent_garden(FIG / "agent_garden.png")
    fig_architecture(FIG / "architecture.png")
    fig_hit_rates(data, FIG / "hit_rates.png")
    fig_rating_mix(data, FIG / "rating_mix.png")
    meta = {"title": "Agent Garden: Finance Agent",
            "footer": "Agent Garden: Finance Agent | CS5903 Project Report"}
    build_pdf(DOCS / "Project_Report.md", DOCS / "Project_Report.pdf", meta)
    print(f"\nWrote {DOCS / 'Project_Report.pdf'}")


if __name__ == "__main__":
    main()
