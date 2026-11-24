"""Compare experiment arms scored by evaluate.py, on the cells they all share.

    .venv\\Scripts\\python.exe ..\\compare.py A B C

reads results\\evaluation\\cells_A.csv, cells_B.csv, cells_C.csv. The first two
arms are read as baseline and repeat-baseline: how far they differ is the
run-to-run noise, the yardstick any later arm has to clear. Writes
results\\evaluation\\report_compare.md.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL = ROOT / "results" / "evaluation"
HORIZONS = (5, 10, 20)
DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
RATINGS = list(DIRECTION)


def load(name: str) -> dict:
    """{(ticker, date): {"rating": str, h: (raw, alpha) or None}}"""
    cells = {}
    with open(EVAL / f"cells_{name}.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = cells.setdefault((r["ticker"], r["date"]), {"rating": r["rating"]})
            c[int(r["h"])] = (float(r["raw"]), float(r["alpha"])) if r["alpha"] else None
    return cells


def pct(x):
    return "n/a" if x is None else f"{x:+.2%}"


def rate(hits, n):
    return "n/a" if not n else f"{hits / n:.0%} ({hits}/{n})"


def metrics(arm: dict, keys: list, h: int) -> dict:
    scored = [k for k in keys if arm[k].get(h)]
    calls = [k for k in scored if DIRECTION.get(arm[k]["rating"], 0)]
    d = lambda k: DIRECTION.get(arm[k]["rating"], 0)
    bull = [arm[k][h][1] for k in calls if d(k) > 0]
    bear = [arm[k][h][1] for k in calls if d(k) < 0]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return {
        "n": len(calls),
        "alpha_hits": sum(d(k) * arm[k][h][1] > 0 for k in calls),
        "raw_hits": sum(d(k) * arm[k][h][0] > 0 for k in calls),
        "spread": mean(bull) - mean(bear) if bull and bear else None,
        "captured": mean([d(k) * arm[k][h][1] for k in calls]),
    }


def main(names: list[str]) -> None:
    if len(names) < 2:
        sys.exit("give at least two arm names, e.g. A B C")
    arms = {n: load(n) for n in names}
    shared = sorted(set.intersection(*(set(a) for a in arms.values())))
    if not shared:
        sys.exit("the arms share no (ticker, date) cells")

    out = [f"# Experiment comparison: {' vs '.join(names)}", "",
           f"Cells all arms share: {len(shared)} "
           f"({', '.join(sorted({t for t, _ in shared}))}; {shared[0][1]} to {shared[-1][1]}). "
           "Every number below uses only these cells, so the arms are scored on identical stock-date pairs.", ""]

    out += ["## Rating mix", "", "| Arm | " + " | ".join(RATINGS) + " | Bearish share |",
            "|---|" + "---|" * (len(RATINGS) + 1)]
    for n, a in arms.items():
        c = Counter(a[k]["rating"] for k in shared)
        bearish = sum(c[r] for r in RATINGS if DIRECTION[r] < 0)
        out.append(f"| {n} | " + " | ".join(str(c[r]) for r in RATINGS) + f" | {bearish / len(shared):.0%} |")

    out += ["", "## Agreement between arms (same stock, same date)", "",
            "| Pair | Same rating | Same direction (bullish / neutral / bearish) |", "|---|---|---|"]
    sign = lambda r: DIRECTION.get(r, 0)
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            same = sum(arms[x][k]["rating"] == arms[y][k]["rating"] for k in shared)
            same_dir = sum(sign(arms[x][k]["rating"]) == sign(arms[y][k]["rating"]) for k in shared)
            out.append(f"| {x} vs {y} | {rate(same, len(shared))} | {rate(same_dir, len(shared))} |")
    if len(names) >= 2:
        out += ["", f"{names[0]} vs {names[1]} is the noise floor: the same setup run twice. "
                "A later arm only shows a real effect if it moves further from the baseline than that."]

    for h in HORIZONS:
        out += ["", f"## {h} trading days", "",
                "| Arm | Alpha hit rate | Raw direction hit rate | Long-short spread | Avg alpha captured per call |",
                "|---|---|---|---|---|"]
        for n, a in arms.items():
            m = metrics(a, shared, h)
            out.append(f"| {n} | {rate(m['alpha_hits'], m['n'])} | {rate(m['raw_hits'], m['n'])} | "
                       f"{pct(m['spread'])} | {pct(m['captured'])} |")

    report = "\n".join(out)
    (EVAL / "report_compare.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved: {EVAL / 'report_compare.md'}")


if __name__ == "__main__":
    main(sys.argv[1:])
