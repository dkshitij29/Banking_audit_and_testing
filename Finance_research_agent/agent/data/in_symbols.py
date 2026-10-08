"""Indian ticker resolver — NSE (.NS) / BSE (.BO) via committed CSV masters.

Usage:
    resolver = IndianSymbolResolver()   # auto-loads data/in_equities_nse.csv
    resolver.resolve("RELIANCE")        → ResolvedSymbol(ticker="RELIANCE.NS", …)
    resolver.resolve("500325")          → ResolvedSymbol(ticker="RELIANCE.BO", …)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz


@dataclass
class ResolvedSymbol:
    """Single unambiguous resolution."""
    ticker: str                  # e.g. "RELIANCE.NS"
    exchange: str                # "NSE" | "BSE"
    name: str
    isin: str | None = None


@dataclass
class AmbiguousSymbol:
    """Multiple close candidates."""
    raw: str
    candidates: list[ResolvedSymbol]


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# ── Column expectations ──────────────────────────────────────────────────────
_NSE_COLUMNS = {"symbol", "name", "isin"}          # symbol, name, isin
_BSE_COLUMNS = {"code", "symbol", "name", "isin"}  # code, symbol, name, isin


class IndianSymbolResolver:
    """Resolve raw tickers / BSE codes / names → yf-compatible symbols."""

    def __init__(self, data_dir: Path | None = None):
        base = data_dir or _DATA_DIR
        self._nse: dict[str, ResolvedSymbol] = {}   # symbol → info
        self._bse: dict[str, ResolvedSymbol] = {}   # code (str) → info
        self._name_to_nse: dict[str, ResolvedSymbol] = {}

        self._load_nse(base / "in_equities_nse.csv")
        self._load_bse(base / "in_scrips_bse.csv")

    # ── Internal loading ────────────────────────────────────────────────────

    def _load_nse(self, path: Path):
        if not path.exists():
            return
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row.get("symbol", "").strip().upper()
                if not symbol:
                    continue
                name = row.get("name", symbol).strip()
                isin = row.get("isin", "").strip() or None
                sym = ResolvedSymbol(
                    ticker=f"{symbol}.NS", exchange="NSE", name=name, isin=isin,
                )
                self._nse[symbol] = sym
                # normalise name for reverse lookup
                self._name_to_nse[name.upper()] = sym

    def _load_bse(self, path: Path):
        if not path.exists():
            return
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("code", "").strip()
                symbol = row.get("symbol", "").strip().upper()
                if not code or not symbol:
                    continue
                name = row.get("symbol", symbol).strip()
                isin = row.get("isin", "").strip() or None
                self._bse[code] = ResolvedSymbol(
                    ticker=f"{symbol}.BO", exchange="BSE", name=name, isin=isin,
                )

    # ── Public API ──────────────────────────────────────────────────────────

    def resolve(self, raw: str) -> ResolvedSymbol | AmbiguousSymbol:
        """Resolve *raw* to a yf-compatible symbol.

        Priority:
        1. Already ends in ``.NS`` / ``.BO`` → validate.
        2. Exact match on NSE symbol → ``SYMBOL.NS``.
        3. Numeric BSE code → ``SYMBOL.BO``.
        4. Fuzzy name match (rapidfuzz, threshold 85).
        """
        raw = raw.strip().upper()

        # 1 — already suffixed
        if raw.endswith(".NS"):
            base = raw[:-3]
            if base in self._nse:
                return self._nse[base]
        if raw.endswith(".BO"):
            base = raw[:-3]
            for code, sym in self._bse.items():
                if sym.ticker == raw:
                    return sym

        # 2 — exact NSE symbol
        if raw in self._nse:
            return self._nse[raw]

        # 3 — numeric BSE code
        if raw.isdigit():
            if raw in self._bse:
                return self._bse[raw]

        # 4 — fuzzy name match (NSE first, then BSE)
        candidates: list[ResolvedSymbol] = []
        threshold = 80

        for sym in self._nse.values():
            score = fuzz.partial_ratio(raw, sym.name.upper())
            if score >= threshold:
                candidates.append(sym)

        for sym in self._bse.values():
            score = fuzz.partial_ratio(raw, sym.name.upper())
            if score >= threshold and sym not in candidates:
                candidates.append(sym)

        if not candidates:
            raise ValueError(f"Unknown symbol or name: {raw!r}")
        if len(candidates) == 1:
            return candidates[0]

        # More than one — is there a clear winner?
        # Sort by score (approximate via name similarity)
        best = max(candidates, key=lambda s: fuzz.partial_ratio(raw, s.name.upper()))
        runner_up = max(
            (c for c in candidates if c.ticker != best.ticker),
            default=None,
            key=lambda s: fuzz.partial_ratio(raw, s.name.upper()),
        )
        if runner_up is None or (
            fuzz.partial_ratio(raw, best.name.upper())
            - fuzz.partial_ratio(raw, runner_up.name.upper())
            > 10
        ):
            return best

        return AmbiguousSymbol(raw=raw, candidates=candidates[:5])

    def is_loaded(self) -> bool:
        return bool(self._nse)
