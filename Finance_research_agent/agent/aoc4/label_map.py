"""Schedule III label synonyms → Item mapping.

Used by ``pdf_statements.py`` to map extracted row labels to canonical Item codes.
"""

from __future__ import annotations

from agent.aoc4.models import Item


# ── Normalised label → Item ──────────────────────────────────────────────────
# Keys are lowercase, stripped of punctuation and note references.
# Build from real filings; these are seeds.

_LABEL_MAP: dict[str, Item] = {}

_SEEDS: list[tuple[Item, list[str]]] = [
    (Item.TOTAL_ASSETS, ["total assets", "total (assets side)", "assets total"]),
    (Item.TOTAL_EQUITY_AND_LIABILITIES, ["total equity and liabilities", "total (equity and liabilities)", "liabilities and equity total"]),
    (Item.TOTAL_EQUITY, ["total equity", "total shareholders funds", "shareholders funds", "total shareholders' funds"]),
    (Item.EQUITY_SHARE_CAPITAL, ["equity share capital", "share capital", "paid up capital"]),
    (Item.PREFERENCE_SHARE_CAPITAL, ["preference share capital", "preference shares"]),
    (Item.OTHER_EQUITY, ["other equity", "reserves and surplus", "accumulated losses"]),
    (Item.BORROWINGS_NON_CURRENT, ["borrowings (non current)", "long term borrowings", "non current borrowings", "term loans (long term)"]),
    (Item.BORROWINGS_CURRENT, ["borrowings (current)", "short term borrowings", "current borrowings", "term loans (current)", "current maturities of long term borrowings"]),
    (Item.CURRENT_MATURITIES_LTD, ["current maturities of long term borrowings", "current maturities of long term debt"]),
    (Item.LEASE_LIABILITIES_NON_CURRENT, ["lease liabilities (non current)", "non current lease liabilities"]),
    (Item.LEASE_LIABILITIES_CURRENT, ["lease liabilities (current)", "current lease liabilities"]),
    (Item.CASH_AND_EQUIVALENTS, ["cash and cash equivalents", "cash and bank balances"]),
    (Item.OTHER_BANK_BALANCES, ["bank balances other than cash and cash equivalents"]),
    (Item.CURRENT_INVESTMENTS, ["current investments", "investments (current)"]),
    (Item.TRADE_RECEIVABLES, ["trade receivables", "debtors", "trade debtors"]),
    (Item.INVENTORIES, ["inventories", "stock in trade"]),
    (Item.TRADE_PAYABLES, ["trade payables", "creditors"]),
    (Item.TOTAL_CURRENT_ASSETS, ["total current assets"]),
    (Item.TOTAL_CURRENT_LIABILITIES, ["total current liabilities"]),
    # P&L
    (Item.REVENUE_FROM_OPERATIONS, ["revenue from operations", "net revenue", "sales", "net sales", "turnover"]),
    (Item.OTHER_INCOME, ["other income"]),
    (Item.TOTAL_INCOME, ["total income", "total revenue"]),
    (Item.TOTAL_EXPENSES, ["total expenses"]),
    (Item.FINANCE_COSTS, ["finance costs", "interest expense", "interest on borrowings"]),
    (Item.DEPRECIATION_AMORTISATION, ["depreciation and amortisation expense", "depreciation and amortisation"]),
    (Item.EXCEPTIONAL_ITEMS, ["exceptional items"]),
    (Item.PROFIT_BEFORE_TAX, ["profit before tax", "loss before tax", "profit (loss) before tax"]),
    (Item.CURRENT_TAX, ["current tax expense", "current tax", "tax charge (credit) - current"]),
    (Item.DEFERRED_TAX, ["deferred tax expense", "deferred tax", "tax charge (credit) - deferred"]),
    (Item.TAX_EXPENSE, ["total tax expense", "tax expense"]),
    (Item.PROFIT_AFTER_TAX, ["profit for the year", "loss for the year", "profit (loss) for the year", "profit after tax", "net profit after tax", "net profit"]),
    # Cash flow
    (Item.CASH_FROM_OPERATIONS, ["net cash generated from operating activities", "net cash used in operating activities", "cash flow from operating activities", "net cash flow from operating activities"]),
    (Item.CAPEX, ["purchase of property plant and equipment", "purchase of fixed assets", "capital expenditure", "purchase of property, plant and equipment"]),
    (Item.CLOSING_CASH_PER_CFS, ["cash and cash equivalents at the end of the year", "closing balance of cash and cash equivalents"]),
    (Item.DIVIDENDS_PAID, ["dividend paid", "dividends paid"]),
]


def _build():
    for item, labels in _SEEDS:
        for label in labels:
            # Normalise: lowercase, strip punctuation, collapse whitespace
            import re
            norm = re.sub(r"[^\w\s]", "", label.lower()).strip()
            norm = " ".join(norm.split())
            _LABEL_MAP[norm] = item


_build()


def match_label(text: str, *, threshold: float = 0.92) -> Item | None:
    """Match a row label to an Item.

    1. Exact normalised match.
    2. Fuzzy match (rapidfuzz) ≥ threshold.
    Returns ``None`` if no match.
    """
    import re
    from rapidfuzz import fuzz

    # Normalise
    norm = re.sub(r"[^\w\s]", "", text.lower()).strip()
    norm = " ".join(norm.split())

    # 1. Exact
    if norm in _LABEL_MAP:
        return _LABEL_MAP[norm]

    # 2. Fuzzy
    best_score = 0
    best_item: Item | None = None
    for label, item in _LABEL_MAP.items():
        score = fuzz.partial_ratio(norm, label)
        if score > best_score:
            best_score = score
            best_item = item

    if best_score >= threshold * 100:
        return best_item
    return None
