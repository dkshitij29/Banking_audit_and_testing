"""lxml-based XBRL fact extractor — no network, no taxonomy download.

Parses Indian XBRL instance documents (.xbrl / .xml) and maps facts
to ``Item`` codes using ``xbrl_mapping.yaml``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import lxml.etree as ET

from agent.aoc4.models import Item, PeriodStatements, Source, Provenance, Basis, Framework


# ── Namespaces ───────────────────────────────────────────────────────────────

_NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
    "link": "http://www.xbrl.org/2003/linkbase",
    "iso4217": "http://www.iso.org/iso/4217",
}

INR_MONETARY = "{http://www.xbrl.org/2003/instance}items"  # placeholder
INR_UNIT = "{http://www.xbrl.org/2003/instance}INR"


def extract_facts(instance_path: str | Path) -> list[PeriodStatements]:
    """Parse an XBRL instance and return ``PeriodStatements`` per period found.

    Strategy:
    1. Parse contexts → identify duration/instant periods
    2. Parse facts → keep non-dimensional, monetary (INR) facts
    3. Map concept local names → Item via _CONCEPT_MAP
    4. Return one PeriodStatements per context period
    """
    tree = ET.parse(str(instance_path))
    root = tree.getroot()

    # ── Parse contexts ───────────────────────────────────────────────────
    contexts: dict[str, dict] = {}
    for ctx in root.iter(f"{{{_NS['xbrli']}}}context"):
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue

        info: dict = {"id": ctx_id, "period_start": None, "period_end": None, "is_instant": False}

        period_el = ctx.find(f"{{{_NS['xbrli']}}}period", _NS)
        if period_el is not None:
            instant = period_el.find(f"{{{_NS['xbrli']}}}instant", _NS)
            if instant is not None and instant.text:
                info["is_instant"] = True
                info["period_end"] = _parse_date(instant.text)
            else:
                start_el = period_el.find(f"{{{_NS['xbrli']}}}startDate", _NS)
                end_el = period_el.find(f"{{{_NS['xbrli']}}}endDate", _NS)
                if start_el is not None and start_el.text:
                    info["period_start"] = _parse_date(start_el.text)
                if end_el is not None and end_el.text:
                    info["period_end"] = _parse_date(end_el.text)

        # Skip dimensional contexts (segments with explicitMember/typedMember)
        segment = ctx.find(f"{{{_NS['xbrli']}}}segment", _NS)
        if segment is not None:
            has_dims = bool(segment.findall(f".//{{{_NS['xbrldi']}}}explicitMember", _NS))
            has_dims |= bool(segment.findall(f".//{{{_NS['xbrldi']}}}typedMember", _NS))
            if has_dims:
                continue

        scenario = ctx.find(f"{{{_NS['xbrli']}}}scenario", _NS)
        if scenario is not None:
            has_dims = bool(scenario.findall(f".//{{{_NS['xbrldi']}}}explicitMember", _NS))
            has_dims |= bool(scenario.findall(f".//{{{_NS['xbrldi']}}}typedMember", _NS))
            if has_dims:
                continue

        contexts[ctx_id] = info

    # ── Parse units ──────────────────────────────────────────────────────
    units: dict[str, str] = {}
    for unit_el in root.iter(f"{{{_NS['xbrli']}}}unit"):
        unit_id = unit_el.get("id")
        if not unit_id:
            continue
        measure = unit_el.find(f"{{{_NS['xbrli']}}}measure", _NS)
        if measure is not None and measure.text:
            units[unit_id] = measure.text

    # ── Parse facts ──────────────────────────────────────────────────────
    # Group facts by (context_id, unit_type)
    facts_by_context: dict[str, dict[str, Decimal | None]] = {}

    for fact in root.iter():
        tag = fact.tag
        ctx_ref = fact.get("contextRef")
        unit_ref = fact.get("unitRef")
        if not ctx_ref or ctx_ref not in contexts:
            continue

        local_name = tag.split("}")[-1] if "}" in tag else tag
        value_str = fact.text

        # Skip pure / non-monetary facts for now
        unit_type = units.get(unit_ref, "") if unit_ref else ""
        is_monetary = "INR" in unit_type if unit_type else False
        is_pure = "pure" in unit_type if unit_type else False

        if not is_monetary and not is_pure:
            continue

        # Parse value
        value = None
        if value_str:
            try:
                value = Decimal(value_str)
            except (InvalidOperation, ValueError):
                pass

        if ctx_ref not in facts_by_context:
            facts_by_context[ctx_ref] = {}

        # Map concept → Item
        mapped_items = _CONCEPT_MAP.get(local_name, [])
        for item in mapped_items:
            # First mapping wins
            if item not in facts_by_context[ctx_ref]:
                facts_by_context[ctx_ref][item] = value

    # ── Build PeriodStatements per context ───────────────────────────────
    results: list[PeriodStatements] = []

    for ctx_id, facts in facts_by_context.items():
        ctx_info = contexts.get(ctx_id, {})
        period_end = ctx_info.get("period_end")
        if not period_end:
            continue

        from agent.aoc4.fiscal import months_between, is_standard_period

        months = months_between(ctx_info.get("period_start"), period_end)
        if not is_standard_period(ctx_info.get("period_start"), period_end):
            months = 0  # flag for exclusion

        stmt = PeriodStatements(
            period_start=ctx_info.get("period_start"),
            period_end=period_end,
            months=months if months else 12,
            source=Source.XBRL,
            items={item: val for item, val in facts.items()},
            provenance={},
        )

        # Set provenance
        for item, val in facts.items():
            stmt.provenance[item] = Provenance(
                doc_id=str(instance_path),
                label_as_found=item.value,
                raw_value=str(val) if val is not None else None,
                source=Source.XBRL,
            )

        results.append(stmt)

    return results


def _parse_date(text: str) -> date | None:
    """Parse ISO date string."""
    try:
        parts = text.strip().split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


# ── Concept map (placeholder — populate from real samples) ──────────────────
# Maps XBRL concept local names → Item enum values.
# MUST be populated by scripts/dump_xbrl_concepts.py on real filings.

_CONCEPT_MAP: dict[str, list[Item]] = {
    # Ind AS / Indian GAAP revenue
    "RevenueFromOperations": [Item.REVENUE_FROM_OPERATIONS],
    "TotalRevenue": [Item.REVENUE_FROM_OPERATIONS],
    "RevenueFromOperationsNet": [Item.REVENUE_FROM_OPERATIONS],

    # Total assets
    "TotalAssets": [Item.TOTAL_ASSETS],

    # Total equity and liabilities
    "TotalEquityAndLiabilities": [Item.TOTAL_EQUITY_AND_LIABILITIES],
    "TotalLiabilities": [Item.TOTAL_EQUITY_AND_LIABILITIES],

    # Equity
    "TotalEquity": [Item.TOTAL_EQUITY],
    "TotalShareholdersFunds": [Item.TOTAL_EQUITY],
    "ShareholdersFunds": [Item.TOTAL_EQUITY],

    # Share capital
    "EquityShareCapital": [Item.EQUITY_SHARE_CAPITAL],
    "ShareCapital": [Item.EQUITY_SHARE_CAPITAL],

    # Borrowings
    "BorrowingsNonCurrent": [Item.BORROWINGS_NON_CURRENT],
    "LongTermBorrowings": [Item.BORROWINGS_NON_CURRENT],
    "BorrowingsCurrent": [Item.BORROWINGS_CURRENT],
    "ShortTermBorrowings": [Item.BORROWINGS_CURRENT],

    # Cash
    "CashAndCashEquivalents": [Item.CASH_AND_EQUIVALENTS],
    "CashAndBankBalances": [Item.CASH_AND_EQUIVALENTS],

    # P&L
    "OtherIncome": [Item.OTHER_INCOME],
    "TotalIncome": [Item.TOTAL_INCOME],
    "TotalExpenses": [Item.TOTAL_EXPENSES],
    "FinanceCost": [Item.FINANCE_COSTS],
    "DepreciationAndAmortisationExpense": [Item.DEPRECIATION_AMORTISATION],
    "ExceptionalItems": [Item.EXCEPTIONAL_ITEMS],
    "ProfitBeforeTax": [Item.PROFIT_BEFORE_TAX],
    "ProfitLossBeforeTax": [Item.PROFIT_BEFORE_TAX],
    "CurrentTaxExpense": [Item.CURRENT_TAX],
    "DeferredTaxExpense": [Item.DEFERRED_TAX],
    "TotalTaxExpense": [Item.TAX_EXPENSE],
    "ProfitLossAfterTax": [Item.PROFIT_AFTER_TAX],
    "ProfitForTheYear": [Item.PROFIT_AFTER_TAX],

    # Cash flow
    "NetCashGeneratedFromOperatingActivities": [Item.CASH_FROM_OPERATIONS],
    "CashAndCashEquivalentsAtTheEndOfTheYear": [Item.CLOSING_CASH_PER_CFS],
    "DividendPaid": [Item.DIVIDENDS_PAID],

    # Receivables / payables
    "TradeReceivables": [Item.TRADE_RECEIVABLES],
    "TradePayables": [Item.TRADE_PAYABLES],
    "Inventories": [Item.INVENTORIES],
}
