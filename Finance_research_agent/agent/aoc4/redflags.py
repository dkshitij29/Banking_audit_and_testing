"""India-specific red flag rules.

Two-step design:
1. Locate with deterministic, heading-anchored rules.
2. Classify polarity (adverse/non_adverse) to avoid boilerplate false positives.
"""

from __future__ import annotations

import re
from agent.aoc4.models import RedFlag, Item, PeriodStatements


def detect_red_flags(
    sections_text: dict[str, str],  # section_type → text
    periods: list[PeriodStatements],
    doc_id: str = "d01",
) -> list[RedFlag]:
    """Run all red flag rules and return findings."""
    flags: list[RedFlag] = []

    # ── Auditor report flags ──────────────────────────────────────────────
    auditor_text = sections_text.get("AUDITOR_REPORT", "")
    if auditor_text:
        flags.extend(_auditor_opinion_flags(auditor_text, doc_id))
        flags.extend(_fraud_143_flags(auditor_text, doc_id))

    # ── CARO flags ───────────────────────────────────────────────────────
    caro_text = sections_text.get("CARO_ANNEXURE", "")
    if caro_text:
        flags.extend(_caro_flags(caro_text, doc_id))

    # ── Computed flags (from financial data) ─────────────────────────────
    if periods:
        flags.extend(_computed_flags(periods, doc_id))

    return flags


def _auditor_opinion_flags(text: str, doc_id: str) -> list[RedFlag]:
    """Detect modified auditor opinions by heading."""
    flags: list[RedFlag] = []

    # Only look at section headings, not body text
    lines = text.split("\n")
    headings = "\n".join(l.strip() for l in lines if l.strip().isupper() or
                         (len(l.strip()) < 100 and not l.strip().endswith(",")))

    patterns = {
        "AUD_QUALIFIED_OPINION": (r"qualified\s*opinion", "high"),
        "AUD_ADVERSE_OPINION": (r"adverse\s*opinion", "high"),
        "AUD_DISCLAIMER": (r"disclaimer\s*of\s*opinion", "high"),
        "AUD_GOING_CONCERN": (r"material\s*uncertainty\s*related\s*to\s*going\s*concern", "high"),
        "AUD_EMPHASIS_OF_MATTER": (r"emphasis\s*of\s*matter", "medium"),
    }

    for code, (pattern, severity) in patterns.items():
        match = re.search(pattern, headings, re.IGNORECASE)
        if match:
            quote = match.group(0)[:200]
            flags.append(RedFlag(
                code=code, severity=severity, title=code.replace("AUD_", "Auditor: "),
                evidence_quote=quote, doc_id=doc_id, method="rule",
            ))

    return flags


def _fraud_143_flags(text: str, doc_id: str) -> list[RedFlag]:
    """Detect Section 143(12) fraud reporting."""
    if "143(12)" in text and ("fraud" in text.lower()):
        # Check if it's adverse (fraud was reported) or boilerplate (no fraud)
        if re.search(r"(has|have)\s+(not\s+)?(been\s+)?reported", text, re.IGNORECASE):
            # Check polarity: "has not been reported" = clean, "has been reported" = flag
            match = re.search(
                r"143\(12\).*?has\s+(not\s+)?been\s+reported",
                text, re.IGNORECASE | re.DOTALL,
            )
            if match and "not" not in match.group(0).lower():
                return [RedFlag(
                    code="AUD_FRAUD_143_12", severity="high",
                    title="Auditor reported fraud under Section 143(12)",
                    evidence_quote=text[:200], doc_id=doc_id, method="rule",
                )]
    return []


def _caro_flags(text: str, doc_id: str) -> list[RedFlag]:
    """Detect adverse CARO findings."""
    flags: list[RedFlag] = []

    caro_checks = {
        "CARO_DEFAULT_ON_BORROWINGS": (
            r"(default|defaults?|has\s+defaulted).*(borrow|loan)",
            "high",
        ),
        "CARO_FRAUD": (
            r"(fraud\s+(noticed|reported|detected))",
            "high",
        ),
        "CARO_CASH_LOSSES": (
            r"(cash\s+losses?|incurred\s+losses?)",
            "medium",
        ),
        "CARO_STATUTORY_DUES": (
            r"(undisputed\s+statutory\s+dues).*(outstanding|not\s+paid)",
            "medium",
        ),
    }

    for code, (pattern, severity) in caro_checks.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Check for negation nearby
            context = text[max(0, match.start() - 50):match.end() + 50]
            if not re.search(r"(has\s+not|no\s+such|not\s+applicable|nil)", context, re.IGNORECASE):
                flags.append(RedFlag(
                    code=code, severity=severity,
                    title=code.replace("CARO_", "CARO: "),
                    evidence_quote=match.group(0)[:200],
                    doc_id=doc_id, method="rule",
                ))

    return flags


def _computed_flags(periods: list[PeriodStatements], doc_id: str) -> list[RedFlag]:
    """Compute red flags from financial data."""
    flags: list[RedFlag] = []
    if not periods:
        return flags

    latest = periods[-1]

    # Negative net worth
    equity = latest.items.get(Item.TOTAL_EQUITY)
    if equity is not None and equity < 0:
        flags.append(RedFlag(
            code="NEGATIVE_NET_WORTH", severity="high",
            title="Negative net worth",
            evidence_quote=f"Total equity: {equity}",
            doc_id=doc_id, method="computed",
        ))

    # Loss making multi-year
    loss_years = sum(
        1 for p in periods[-2:]
        if (p.items.get(Item.PROFIT_AFTER_TAX) or 0) < 0
    )
    if loss_years >= 2:
        flags.append(RedFlag(
            code="LOSS_MAKING_MULTI_YEAR", severity="medium",
            title="Loss making for latest 2+ years",
            evidence_quote=f"{loss_years} consecutive loss years",
            doc_id=doc_id, method="computed",
        ))

    # Negative CFO multi-year
    negative_cfo = sum(
        1 for p in periods[-2:]
        if (p.items.get(Item.CASH_FROM_OPERATIONS) or 0) < 0
    )
    if negative_cfo >= 2:
        flags.append(RedFlag(
            code="NEGATIVE_CFO_MULTI_YEAR", severity="medium",
            title="Negative operating cash flow for 2+ years",
            evidence_quote=f"{negative_cfo} consecutive negative CFO years",
            doc_id=doc_id, method="computed",
        ))

    # Low interest coverage
    pbt = latest.items.get(Item.PROFIT_BEFORE_TAX) or 0
    finance_costs = latest.items.get(Item.FINANCE_COSTS) or 0
    if finance_costs > 0:
        coverage = (pbt + finance_costs) / finance_costs
        if coverage < 1.5:
            flags.append(RedFlag(
                code="LOW_INTEREST_COVERAGE", severity="medium",
                title=f"Low interest coverage ratio ({coverage:.1f}x)",
                evidence_quote=f"PBT={pbt}, Finance costs={finance_costs}",
                doc_id=doc_id, method="computed",
            ))

    return flags
