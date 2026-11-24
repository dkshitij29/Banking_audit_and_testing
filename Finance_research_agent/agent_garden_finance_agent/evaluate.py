"""Score TradingAgents backtest decisions at several holding periods.

The backtester scores each decision once, on 5-day alpha vs the benchmark. This
re-scores the same decisions (no agent re-runs) at 5, 10 and 20 trading days,
both against the benchmark (alpha) and on raw price direction, with baselines
and a significance test so a hit rate can be read against chance.

Prices come from the same functions the backtester settles with, so the 5-day
figures match its trading_memory.md exactly (to the 0.1% it rounds to).

Usage (from the TradingAgents folder, with its venv):
    .venv\\Scripts\\python.exe ..\\evaluate.py                     # every results\\backtest\\*\\trading_memory.md
    .venv\\Scripts\\python.exe ..\\evaluate.py --name A "eval_*"   # one experiment arm, by run-folder pattern
    .venv\\Scripts\\python.exe ..\\evaluate.py path\\to\\trading_memory.md ...
    .venv\\Scripts\\python.exe ..\\evaluate.py --name ds1 --groups ..\\dataset\\test_set_v1.csv "ds1_*"

Writes results\\evaluation\\cells.csv (one row per decision and horizon) and
results\\evaluation\\report.md, or cells_<name>.csv / report_<name>.md with --name.
--groups adds a section that splits the scores by the test set's "market" column
(falling / rising / flat), matched on ticker and date.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date, datetime, timedelta
from math import comb
from pathlib import Path

from tradingagents.dataflows.vendors.yahoo.market import get_closes
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.memory.settlement import _by_day, resolve_benchmark

ROOT = Path(__file__).resolve().parent
HORIZONS = (5, 10, 20)
DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
RATINGS = list(DIRECTION)
# "[2026-09-21 | NVDA | Underweight | -0.7% | +0.5% | 5d | resolved:...]" or "[... | pending]"
HEADER = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) \| ([^|\]]+?) \| ([^|\]]+?) \|")


def load_decisions(paths: list[Path]) -> list[dict]:
    """Every (ticker, date, rating) in the given memory logs; a later file wins a duplicate."""
    found = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            m = HEADER.match(line)
            if m:
                day, ticker, rating = (g.strip() for g in m.groups())
                found[(ticker, day)] = {"ticker": ticker, "date": day, "rating": rating,
                                        "source": path.parent.name}
    return sorted(found.values(), key=lambda d: (d["ticker"], d["date"]))


def price_history(symbols: set[str], first: str) -> dict:
    start = (datetime.strptime(first, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    return {s: _by_day(get_closes(s, start, end)) for s in sorted(symbols)}


def outcome(stock, bench, trade_date: str, h: int):
    """(raw, bench_ret, alpha, entry, exit) over h sessions from the first close after
    trade_date, the backtester's own rule; None while the window has not fully traded."""
    start = datetime.strptime(trade_date, "%Y-%m-%d")
    s = stock[stock.index > start]
    if len(s) <= h:
        return None
    entry, exit_ = s.index[0], s.index[h]
    if bench.empty or bench.index[0] > entry or bench.index[-1] < exit_:
        return None
    raw = float((s.iloc[h] - s.iloc[0]) / s.iloc[0])
    b0, b1 = bench.asof(entry), bench.asof(exit_)
    b = float((b1 - b0) / b0)
    return raw, b, raw - b, entry.strftime("%Y-%m-%d"), exit_.strftime("%Y-%m-%d")


def p_value(hits: int, n: int) -> float:
    """One-sided binomial P(X >= hits) for a coin flip: how likely this hit rate is by luck."""
    return sum(comb(n, k) for k in range(hits, n + 1)) / 2 ** n if n else 1.0


def pct(x) -> str:
    return "n/a" if x is None else f"{x:+.2%}"


def rate(hits: int, n: int) -> str:
    return "n/a" if not n else f"{hits / n:.0%} ({hits}/{n})"


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def score(rows: list[dict], h: int) -> list[str]:
    done = [r for r in rows if r["h"] == h and r["alpha"] is not None]
    pending = sum(1 for r in rows if r["h"] == h and r["alpha"] is None)
    calls = [r for r in done if r["dir"]]
    a_hits = sum(r["dir"] * r["alpha"] > 0 for r in calls)
    r_hits = sum(r["dir"] * r["raw"] > 0 for r in calls)
    bull = [r["alpha"] for r in calls if r["dir"] > 0]
    bear = [r["alpha"] for r in calls if r["dir"] < 0]
    out = [f"### Holding period: {h} trading days",
           f"Scored decisions: {len(done)} (directional {len(calls)}, Hold {len(done) - len(calls)}) · "
           f"pending (window not over yet): {pending}", ""]
    if not done:
        return out + ["Nothing to score at this horizon yet.", ""]
    out += [
        "| Metric | Value | What it means |",
        "|---|---|---|",
        f"| **Alpha hit rate** | {rate(a_hits, len(calls))} | Buy/Overweight beat SPY, or Underweight/Sell lagged it |",
        f"| p-value vs coin flip | {p_value(a_hits, len(calls)):.2f} | below 0.05 = unlikely to be luck |",
        f"| **Raw direction hit rate** | {rate(r_hits, len(calls))} | the stock itself moved the way the call said |",
        f"| p-value vs coin flip | {p_value(r_hits, len(calls)):.2f} | |",
        f"| Mean alpha of bullish calls | {pct(mean(bull))} | should be positive |",
        f"| Mean alpha of bearish calls | {pct(mean(bear))} | should be negative |",
        f"| **Long-short spread** | {pct(mean(bull) - mean(bear)) if bull and bear else 'n/a'} | bullish minus bearish; > 0 = the ratings separate winners from losers |",
        f"| Avg alpha captured per call | {pct(mean([r['dir'] * r['alpha'] for r in calls]))} | following each call (long on bullish, short on bearish) |",
        f"| Baseline: stocks that beat SPY | {rate(sum(r['alpha'] > 0 for r in done), len(done))} | an 'always Buy' agent's alpha hit rate |",
        f"| Baseline: stocks that rose | {rate(sum(r['raw'] > 0 for r in done), len(done))} | an 'always Buy' agent's raw hit rate |",
        "",
        "| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |",
        "|---|---|---|---|---|---|",
    ]
    for rating in RATINGS:
        rs = [r for r in done if r["rating"] == rating]
        if not rs:
            continue
        d = DIRECTION[rating]
        hit_a = rate(sum(d * r["alpha"] > 0 for r in rs), len(rs)) if d else "no direction"
        hit_r = rate(sum(d * r["raw"] > 0 for r in rs), len(rs)) if d else "no direction"
        out.append(f"| {rating} | {len(rs)} | {pct(mean([r['raw'] for r in rs]))} | "
                   f"{pct(mean([r['alpha'] for r in rs]))} | {hit_a} | {hit_r} |")
    return out + [""]


def load_groups(path: str) -> dict:
    """(ticker, date) -> market label from a test-set CSV with ticker, date and market columns."""
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["ticker"], r["date"]): r["market"] for r in csv.DictReader(f)}


def score_by_group(rows: list[dict]) -> list[str]:
    """Per market condition and horizon: how bearish the agent was and how often it was right."""
    labels = sorted({r["group"] for r in rows if r.get("group")})
    out = ["## By market condition", "",
           "A bearish agent should do well in falling markets and badly in rising ones; "
           "a skilled one beats the 'always Buy' baseline in every condition.", ""]
    for h in HORIZONS:
        out += [f"### {h} trading days", "",
                "| Market | Decisions | Bearish calls | Alpha hit rate | p-value | Raw hit rate | "
                "Always Buy (alpha) | Avg alpha captured |",
                "|---|---|---|---|---|---|---|---|"]
        for g in labels:
            done = [r for r in rows if r["h"] == h and r.get("group") == g and r["alpha"] is not None]
            calls = [r for r in done if r["dir"]]
            a_hits = sum(r["dir"] * r["alpha"] > 0 for r in calls)
            r_hits = sum(r["dir"] * r["raw"] > 0 for r in calls)
            bear = sum(r["dir"] < 0 for r in done)
            out.append(f"| {g} | {len(done)} | {rate(bear, len(done))} | {rate(a_hits, len(calls))} | "
                       f"{p_value(a_hits, len(calls)):.2f} | {rate(r_hits, len(calls))} | "
                       f"{rate(sum(r['alpha'] > 0 for r in done), len(done))} | "
                       f"{pct(mean([r['dir'] * r['alpha'] for r in calls]))} |")
        out.append("")
    return out


def resolve_logs(args: list[str]) -> list[Path]:
    """Memory logs from file paths or run-folder patterns (e.g. "eval_*") under results\\backtest."""
    if not args:
        return sorted(ROOT.glob("results/backtest/*/trading_memory.md"))
    paths = []
    for a in args:
        p = Path(a)
        paths += [p] if p.is_file() else sorted(ROOT.glob(f"results/backtest/{a}/trading_memory.md"))
    return paths


def main(argv: list[str]) -> None:
    name = groups_path = None
    while argv[:1] in (["--name"], ["--groups"]):
        if argv[0] == "--name":
            name = argv[1]
        else:
            groups_path = argv[1]
        argv = argv[2:]
    suffix = f"_{name}" if name else ""
    groups = load_groups(groups_path) if groups_path else {}
    paths = resolve_logs(argv)
    decisions = load_decisions(paths)
    if not decisions:
        sys.exit("no decisions found in: " + ", ".join(map(str, paths)))
    bench_of = {d["ticker"]: resolve_benchmark(d["ticker"], DEFAULT_CONFIG) for d in decisions}
    prices = price_history({d["ticker"] for d in decisions} | set(bench_of.values()),
                           min(d["date"] for d in decisions))

    rows = []
    for d in decisions:
        for h in HORIZONS:
            res = outcome(prices[d["ticker"]], prices[bench_of[d["ticker"]]], d["date"], h)
            raw, b, alpha, entry, exit_ = res if res else (None,) * 5
            rows.append({**d, "dir": DIRECTION.get(d["rating"], 0), "h": h, "benchmark": bench_of[d["ticker"]],
                         "entry": entry, "exit": exit_, "raw": raw, "bench": b, "alpha": alpha,
                         "group": groups.get((d["ticker"], d["date"]), "")})

    out_dir = ROOT / "results" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"cells{suffix}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "date", "rating", "h", "entry", "exit",
                                          "raw", "benchmark", "bench", "alpha", "source"]
                           + (["group"] if groups else []),
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    unknown = sorted({d["rating"] for d in decisions} - set(DIRECTION))
    lines = [f"# TradingAgents evaluation{f' - {name}' if name else ''} ({date.today()})", "",
             f"Decisions: {len(decisions)} from {len(paths)} log(s) · tickers: "
             f"{', '.join(sorted({d['ticker'] for d in decisions}))} · model: {DEFAULT_CONFIG.get('deep_think_llm')}",
             f"Entry = first close after the analysis date; benchmark: "
             f"{', '.join(sorted(set(bench_of.values())))}."]
    if unknown:
        lines.append(f"Unreadable ratings (counted as no direction): {', '.join(unknown)}")
    lines += ["", "## Every decision", "",
              "| Ticker | Date | Rating | " + " | ".join(f"{h}d raw / alpha" for h in HORIZONS) + " |",
              "|---|---|---|" + "---|" * len(HORIZONS)]
    for d in decisions:
        cells = []
        for h in HORIZONS:
            r = next(x for x in rows if x["ticker"] == d["ticker"] and x["date"] == d["date"] and x["h"] == h)
            cells.append("pending" if r["alpha"] is None else f"{r['raw']:+.1%} / {r['alpha']:+.1%}")
        lines.append(f"| {d['ticker']} | {d['date']} | {d['rating']} | " + " | ".join(cells) + " |")
    lines += ["", "## Scores", ""]
    for h in HORIZONS:
        lines += score(rows, h)
    if groups:
        matched = sum(1 for d in decisions if (d["ticker"], d["date"]) in groups)
        lines += [f"Test set {groups_path}: {matched} of {len(decisions)} decisions matched a sample.", ""]
        lines += score_by_group(rows)

    report = "\n".join(lines)
    (out_dir / f"report{suffix}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved: {out_dir / f'report{suffix}.md'} and {out_dir / f'cells{suffix}.csv'}")


if __name__ == "__main__":
    main(sys.argv[1:])
