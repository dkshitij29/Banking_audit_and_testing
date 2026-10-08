"""Static India peer universe — CSV-driven, manual refresh.

Used by ``find_peers()`` when ``market="IN"`` so the peer set is under our
control instead of depending on a yfinance screener.

Expected CSV columns:
    symbol, name, sector, industry, market_cap_inr, snapshot_date
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from datetime import date


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_UNIVERSE_FILE = _DATA_DIR / "in_universe.csv"


@dataclass
class UniverseEntry:
    symbol: str           # e.g. "RELIANCE.NS"
    name: str
    sector: str
    industry: str
    market_cap_inr: float | None
    snapshot_date: date | None


class IndiaStaticUniverse:
    """Reads ``data/in_universe.csv`` once at construction."""

    def __init__(self, path: Path | None = None):
        self._entries: list[UniverseEntry] = []
        self._by_sector: dict[str, list[UniverseEntry]] = {}
        self._by_symbol: dict[str, UniverseEntry] = {}
        self._load(path or _UNIVERSE_FILE)

    # ── Internal ────────────────────────────────────────────────────────────

    def _load(self, path: Path):
        if not path.exists():
            return
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row.get("symbol", "").strip().upper()
                if not symbol:
                    continue
                entry = UniverseEntry(
                    symbol=symbol,
                    name=row.get("name", symbol).strip(),
                    sector=row.get("sector", "").strip(),
                    industry=row.get("industry", "").strip(),
                    market_cap_inr=float(row["market_cap_inr"]) if row.get("market_cap_inr", "").strip() else None,
                    snapshot_date=None,  # parse if the column exists
                )
                self._entries.append(entry)
                self._by_symbol[symbol] = entry
                self._by_sector.setdefault(entry.sector, []).append(entry)

    # ── Public API ──────────────────────────────────────────────────────────

    def find_peers(self, ticker: str, sector: str | None = None, industry: str | None = None, n: int = 5) -> list[UniverseEntry]:
        """Return up to *n* peers in the same sector / industry, excluding *ticker*.

        Strategy:
        1. If *industry* is provided and matches ≥ ``n+1`` entries → filter by industry.
        2. Otherwise filter by *sector*.
        3. Fall back to all entries if neither matches.
        """
        ticker = ticker.upper()

        pool: list[UniverseEntry] = []
        if industry:
            pool = [e for e in self._entries if e.industry.lower() == industry.lower()]
        if not pool and sector:
            pool = self._by_sector.get(sector, [])
        if not pool:
            pool = list(self._entries)

        # Exclude self, prefer entries with market cap (proxy for liquidness)
        candidates = [e for e in pool if e.symbol != ticker]
        candidates.sort(key=lambda e: e.market_cap_inr or 0, reverse=True)
        return candidates[:n]

    def get_entry(self, symbol: str) -> UniverseEntry | None:
        return self._by_symbol.get(symbol.upper())

    def get_all_sectors(self) -> set[str]:
        return set(self._by_sector.keys())

    @property
    def snapshot_date(self) -> date | None:
        """Return the latest snapshot date in the CSV, if any."""
        return None  # no date parsing yet

    @property
    def size(self) -> int:
        return len(self._entries)

    def is_loaded(self) -> bool:
        return bool(self._entries)
