"""Build test set v1: 20 samples = 10 stocks x 2 time periods each.

Design: 5 periods picked from SPY's real path so that the test covers falling,
rising and flat markets, not only the rising market of our first evaluation
(Jul-Oct 2026). 10 stocks from 10 sectors; each stock is tested in two different
periods (two different market conditions), and each period holds 4 stocks.

The script re-measures each period from Yahoo prices with the backtester's own rule
(entry = first close after the date, exit 20 sessions later), checks that every
period still matches its label and that every stock has prices around its date,
and writes test_set_v1.csv next to this file.

    cd TradingAgents
    .venv\\Scripts\\python.exe ..\\dataset\\build_dataset.py

The market columns describe the period for analysis only. The agent never reads
this file: it receives just a ticker and a date.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from tradingagents.dataflows.vendors.yahoo.market import get_closes
from tradingagents.memory.settlement import _by_day

HERE = Path(__file__).resolve().parent
OUT = HERE / "test_set_v1.csv"

# (period id, analysis date, market label). Each date is a Monday trading day.
PERIODS = {
    "P1": ("2024-08-19", "flat"),     # SPY next 20 sessions about +0.5%
    "P2": ("2025-03-10", "falling"),  # tariff sell-off, about -10%
    "P3": ("2025-04-21", "rising"),   # rebound, about +12%
    "P4": ("2026-02-23", "falling"),  # about -5%
    "P5": ("2026-04-06", "rising"),   # about +10%
}
SECTOR = {
    "NVDA": "Information technology", "META": "Communication services",
    "AMZN": "Consumer discretionary", "WMT": "Consumer staples",
    "JPM": "Financials", "XOM": "Energy", "JNJ": "Health care",
    "CAT": "Industrials", "NEE": "Utilities", "LIN": "Materials",
}
# Which stocks go in which period: every stock twice, every period 4 stocks.
# Six stocks get one falling and one rising period; four get the flat period
# plus one falling or rising period. Most stocks get one 2025 and one 2026 date.
ASSIGN = {
    "P1": ["WMT", "CAT", "NEE", "LIN"],
    "P2": ["NVDA", "AMZN", "XOM", "WMT"],
    "P3": ["META", "JPM", "JNJ", "CAT"],
    "P4": ["META", "JPM", "JNJ", "NEE"],
    "P5": ["NVDA", "AMZN", "XOM", "LIN"],
}
WINDOW = 20             # sessions, our longest scoring horizon
FALLING, RISING, FLAT = -3.0, 3.0, 1.0   # SPY % thresholds that define each label


def label_ok(label: str, nxt: float) -> bool:
    return {"falling": nxt <= FALLING, "rising": nxt >= RISING, "flat": abs(nxt) <= FLAT}[label]


def moves(closes, day: str):
    """(% move over the 20 sessions before, % move over the 20 after entry, scoreable-after date)."""
    t = datetime.strptime(day, "%Y-%m-%d")
    before, after = closes[closes.index <= t], closes[closes.index > t]
    if len(after) <= WINDOW or len(before) <= WINDOW:
        return None
    prev = float(before.iloc[-1] / before.iloc[-1 - WINDOW] - 1) * 100
    nxt = float(after.iloc[WINDOW] / after.iloc[0] - 1) * 100
    return prev, nxt, after.index[WINDOW].strftime("%Y-%m-%d")


def main() -> None:
    problems = []
    count = Counter(t for ts in ASSIGN.values() for t in ts)
    problems += [f"{t} appears {n} times, expected 2" for t, n in count.items() if n != 2]
    problems += [f"{t} has no sector" for t in count if t not in SECTOR]
    problems += [f"{p} has {len(ts)} stocks, expected 4" for p, ts in ASSIGN.items() if len(ts) != 4]

    today = datetime.today().strftime("%Y-%m-%d")
    spy = _by_day(get_closes("SPY", "2024-06-01", today))
    rows = []
    for pid, (day, label) in PERIODS.items():
        m = moves(spy, day)
        if m is None:
            problems.append(f"{pid} {day}: not enough SPY history around this date")
            continue
        prev, nxt, ready = m
        if not label_ok(label, nxt):
            problems.append(f"{pid} {day}: labelled {label} but SPY moved {nxt:+.1f}%")
        for ticker in ASSIGN[pid]:
            stock = _by_day(get_closes(ticker, "2024-06-01", today))
            if moves(stock, day) is None:
                problems.append(f"{pid}-{ticker}: no prices around {day}")
            rows.append({
                "sample_id": f"{pid}-{ticker}",
                "ticker": ticker,
                "sector": SECTOR.get(ticker, ""),
                "date": day,
                "period": pid,
                "market": label,
                "spy_prev_20d_pct": round(prev, 1),
                "spy_next_20d_pct": round(nxt, 1),
                "model_may_know_period": "likely" if day < "2026-01-01" else "less likely",
                "scoreable_after": ready,
            })
    if problems:
        sys.exit("Dataset check failed:\n  " + "\n  ".join(problems))
    rows.sort(key=lambda r: (r["ticker"], r["date"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} samples, {len(count)} stocks, {len(PERIODS)} periods -> {OUT}\n")
    print(f"{'ticker':6} {'sector':24} {'first sample':24} second sample")
    for t in sorted(count):
        a, b = [r for r in rows if r["ticker"] == t]
        print(f"{t:6} {SECTOR[t]:24} {a['date']} {a['market']:10} {b['date']} {b['market']}")


if __name__ == "__main__":
    main()
