"""India-specific verdict derivation and confidence gating.

Extends the existing ±15% rule with mode-aware rules for unlisted,
distressed, and sector-unsupported scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.aoc4.models import (
    ValuationMode, RedFlag, ValidationIssue, IssueSeverity,
)


@dataclass
class VerdictResult:
    verdict: str       # "UNDERVALUED" | "OVERVALUED" | "FAIRLY_VALUED" | "INCONCLUSIVE" | "NOT_APPLICABLE"
    rating: str        # "BUY" | "HOLD" | "SELL" | "N/A"
    confidence: str    # "High" | "Medium" | "Low"
    reason: str = ""


def derive_verdict_in(
    dcf_mid: float | None,
    comps_mid: float | None,
    current_price: float | None,
    reference_price: float | None,
    mode: ValuationMode,
    flags: list[RedFlag],
    issues: list[ValidationIssue],
    max_divergence: float = 0.50,
) -> VerdictResult:
    """Derive verdict for India scenarios.

    Rules (applied in order):
    1. UNSUPPORTED_SECTOR / DISTRESSED / EXTRACTION_ONLY → INCONCLUSIVE
    2. INTRINSIC_RANGE (unlisted, no price) → NOT_APPLICABLE
    3. DCF/comps material divergence → INCONCLUSIVE
    4. Otherwise: ±15% rule vs current/reference price
    """
    # ── Mode gate ────────────────────────────────────────────────────────
    if mode in (ValuationMode.UNSUPPORTED_SECTOR, ValuationMode.EXTRACTION_ONLY):
        return VerdictResult(
            "INCONCLUSIVE", "N/A", "Low",
            reason="Valuation not applicable for this entity type.",
        )

    if mode == ValuationMode.DISTRESSED:
        return VerdictResult(
            "INCONCLUSIVE", "N/A", "Low",
            reason="Going-concern doubt or adverse auditor opinion prevents meaningful valuation.",
        )

    if mode == ValuationMode.INTRINSIC_RANGE:
        return VerdictResult(
            "NOT_APPLICABLE", "N/A", "Medium",
            reason="No market price for an unlisted company — equity value range provided instead.",
        )

    # ── Method divergence ────────────────────────────────────────────────
    if dcf_mid and comps_mid and dcf_mid > 0 and comps_mid > 0:
        divergence = abs(dcf_mid - comps_mid) / ((dcf_mid + comps_mid) / 2)
        if divergence > max_divergence:
            return VerdictResult(
                "INCONCLUSIVE", "N/A", "Low",
                reason=f"DCF ({dcf_mid:.0f}) and comps ({comps_mid:.0f}) disagree by {divergence:.0%}.",
            )

    # ── Price comparison ─────────────────────────────────────────────────
    price = current_price or reference_price
    if not price or price <= 0:
        return VerdictResult("NOT_APPLICABLE", "N/A", "Low", reason="No price for comparison.")

    mid = dcf_mid or comps_mid
    if not mid or mid <= 0:
        return VerdictResult("INCONCLUSIVE", "N/A", "Low", reason="No fair value computed.")

    upside = (mid - price) / price

    # ── Confidence ───────────────────────────────────────────────────────
    confidence = _compute_confidence_in(mode, flags, issues, dcf_mid, comps_mid)

    # ── Verdict ──────────────────────────────────────────────────────────
    if upside > 0.15:
        return VerdictResult("UNDERVALUED", "BUY", confidence,
                             reason=f"Fair value {mid:.0f} is {upside:.0%} above price {price:.0f}.")
    elif upside < -0.15:
        return VerdictResult("OVERVALUED", "SELL", confidence,
                             reason=f"Fair value {mid:.0f} is {abs(upside):.0%} below price {price:.0f}.")
    else:
        return VerdictResult("FAIRLY_VALUED", "HOLD", confidence,
                             reason=f"Fair value {mid:.0f} is within ±15% of price {price:.0f}.")


def _compute_confidence_in(
    mode: ValuationMode,
    flags: list[RedFlag],
    issues: list[ValidationIssue],
    dcf_mid: float | None,
    comps_mid: float | None,
) -> str:
    """Compute confidence for India scenarios (lowest that applies)."""
    # Start at Medium
    confidence = "Medium"

    # Unlisted → never above Medium
    if mode in (ValuationMode.INTRINSIC_RANGE, ValuationMode.INTRINSIC_VS_REFERENCE):
        confidence = "Medium"

    # Any high red flag → Low
    high_flags = [f for f in flags if f.severity == "high"]
    if high_flags:
        confidence = "Low"

    # Any ERROR validation issue → blocked (handled earlier)

    # DCF and comps agreement → Medium (High only for listed + clean source)
    if dcf_mid and comps_mid and dcf_mid > 0 and comps_mid > 0:
        divergence = abs(dcf_mid - comps_mid) / ((dcf_mid + comps_mid) / 2)
        if divergence < 0.25:
            # Could be High for listed, but cap at Medium for now
            confidence = max(confidence, "Medium")

    # Only one method available → Low
    if bool(dcf_mid) != bool(comps_mid):
        confidence = "Low"

    # No WARN issues → can go higher
    warn_issues = [i for i in issues if i.severity == IssueSeverity.WARN]
    if warn_issues and confidence == "High":
        confidence = "Medium"

    return confidence
