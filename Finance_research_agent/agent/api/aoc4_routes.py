"""FastAPI router for AOC-4 / India extension endpoints."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field

from agent.aoc4.models import (
    DocumentInfo, PeriodSummary, ValidationIssue,
    DataQuality, EntityInfo, ValuationMode, RedFlag,
    EquityValueRange,
)
from agent.aoc4.bundle import BundleError
from agent.models.api import StageResult, ValuationMetrics

router = APIRouter(prefix="/api/aoc4", tags=["aoc4"])


# ── Response schemas ─────────────────────────────────────────────────────────

class ExtractResponse(BaseModel):
    """Response for /api/aoc4/extract (Phase 1 deliverable)."""
    stages: list[StageResult] = Field(default_factory=list)
    documents: list[DocumentInfo] = Field(default_factory=list)
    periods: list[PeriodSummary] = Field(default_factory=list)
    validation: list[ValidationIssue] = Field(default_factory=list)
    data_quality: DataQuality | None = None
    entity: EntityInfo | None = None
    valuation_mode: ValuationMode = ValuationMode.EXTRACTION_ONLY


class AOC4ConfigResponse(BaseModel):
    india_config_ready: bool
    india_config_missing: list[str] = Field(default_factory=list)
    ocr_available: bool = False
    feature_flags: dict = Field(default_factory=dict)


class AOC4FullResponse(BaseModel):
    """Full analysis response for /api/aoc4/analyze."""
    verdict: str = "NOT_APPLICABLE"
    rating: str = "N/A"
    reasoning: str = ""
    stages: list[StageResult] = Field(default_factory=list)
    valuation: ValuationMetrics = Field(default_factory=ValuationMetrics)
    valuation_mode: ValuationMode = ValuationMode.EXTRACTION_ONLY
    documents: list[DocumentInfo] = Field(default_factory=list)
    periods: list[PeriodSummary] = Field(default_factory=list)
    validation: list[ValidationIssue] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)
    data_quality: DataQuality | None = None
    entity: EntityInfo | None = None
    equity_value: EquityValueRange | None = None
    dcf_assumptions: dict = Field(default_factory=dict)
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)


# ── CIN validation ───────────────────────────────────────────────────────────

import re

_CIN_PATTERN = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$")


def validate_cin(cin: str) -> bool:
    return bool(_CIN_PATTERN.match(cin))


# ── Endpoint: extract ────────────────────────────────────────────────────────

@router.post("/extract", response_model=ExtractResponse)
async def extract(
    files: list[UploadFile] = File(...),
    cin: Optional[str] = Form(None),
    ticker: Optional[str] = Form(None),
    entity_type: str = Form("auto"),
    basis: str = Form("auto"),
    unit_override: Optional[str] = Form(None),
    doc_overrides: Optional[str] = Form(None),  # JSON string
):
    """Extract financial statements from an AOC-4 bundle.

    No valuation — just classification, parsing, and validation.
    """
    # Resolve app state
    from agent.api.server import app
    settings = app.state.settings

    # Validate CIN if provided
    if cin and not validate_cin(cin):
        raise HTTPException(
            status_code=422,
            detail={"error_code": "CIN_INVALID", "detail": f"CIN {cin!r} does not match expected format"},
        )

    # Parse doc_overrides
    overrides: dict[str, str] | None = None
    if doc_overrides:
        try:
            overrides = json.loads(doc_overrides)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="doc_overrides must be valid JSON")

    # Run pipeline
    from agent.pipeline.aoc4 import AOC4Pipeline
    pipeline = AOC4Pipeline(settings)

    try:
        result = await pipeline.run(
            files,
            cin=cin,
            ticker=ticker,
            entity_type=entity_type,
            unit_override=unit_override,
            doc_overrides=overrides,
        )
    except BundleError as e:
        raise HTTPException(status_code=422, detail={"error_code": str(e), "detail": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

    # Convert PeriodStatements → PeriodSummary
    period_summaries = [
        PeriodSummary(
            label=p.label,
            period_end=p.period_end.isoformat(),
            source=p.source.value,
            basis=p.basis.value if p.basis.value != "unknown" else None,
            framework=p.framework.value if p.framework.value != "unknown" else None,
        )
        for p in result.periods
    ]

    return ExtractResponse(
        stages=result.stages,
        documents=result.documents,
        periods=period_summaries,
        validation=result.validation,
        data_quality=result.data_quality,
        entity=result.entity,
        valuation_mode=result.valuation_mode,
    )


# ── Endpoint: analyze (full pipeline — Phase 3) ──────────────────────────────

@router.post("/analyze", response_model=AOC4FullResponse)
async def analyze(
    files: list[UploadFile] = File(...),
    cin: Optional[str] = Form(None),
    ticker: Optional[str] = Form(None),
    entity_type: str = Form("auto"),
    basis: str = Form("auto"),
    unit_override: Optional[str] = Form(None),
    doc_overrides: Optional[str] = Form(None),
):
    """Full AOC-4 analysis pipeline with valuation."""
    from agent.api.server import app
    settings = app.state.settings

    if cin and not validate_cin(cin):
        raise HTTPException(
            status_code=422,
            detail={"error_code": "CIN_INVALID", "detail": f"CIN {cin!r} does not match expected format"},
        )

    overrides: dict[str, str] | None = None
    if doc_overrides:
        try:
            overrides = json.loads(doc_overrides)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="doc_overrides must be valid JSON")

    from agent.pipeline.aoc4 import AOC4Pipeline
    pipeline = AOC4Pipeline(settings)

    try:
        result = await pipeline.run(
            files,
            cin=cin,
            ticker=ticker,
            entity_type=entity_type,
            unit_override=unit_override,
            doc_overrides=overrides,
        )
    except BundleError as e:
        raise HTTPException(status_code=422, detail={"error_code": str(e), "detail": str(e)})

    period_summaries = [
        PeriodSummary(
            label=p.label,
            period_end=p.period_end.isoformat(),
            source=p.source.value,
            basis=p.basis.value if p.basis.value != "unknown" else None,
            framework=p.framework.value if p.framework.value != "unknown" else None,
        )
        for p in result.periods
    ]

    # Build reasoning
    reasoning_parts = [
        f"Valuation mode: {result.valuation_mode.value}",
        f"Verdict: {result.verdict}",
        f"Confidence: {result.confidence}",
        f"Periods analyzed: {len(result.periods)}",
    ]
    if result.current_price:
        reasoning_parts.append(f"Current price: ₹{result.current_price:.2f}")
    if result.fair_value_mid:
        reasoning_parts.append(f"Fair value midpoint: ₹{result.fair_value_mid:.2f}")
    if result.equity_value:
        ev = result.equity_value
        reasoning_parts.append(
            f"Equity value range: ₹{ev.low_inr:.0f} – ₹{ev.high_inr:.0f} (mid: ₹{ev.mid_inr:.0f})"
        )
        if ev.dlom_applied:
            reasoning_parts.append(f"DLOM applied: {ev.dlom_applied:.0%}")
    reasoning_parts.append(f"Red flags: {len(result.red_flags)}")
    for rf in result.red_flags:
        reasoning_parts.append(f"  - {rf.title} ({rf.severity})")

    return AOC4FullResponse(
        verdict=result.verdict,
        rating=result.rating,
        reasoning="\n".join(reasoning_parts),
        stages=result.stages,
        valuation=ValuationMetrics(
            fair_value_low=result.fair_value_low,
            fair_value_high=result.fair_value_high,
            fair_value_mid=result.fair_value_mid,
            current_price=result.current_price,
            upside_pct=result.upside_pct,
            confidence=result.confidence,
        ),
        valuation_mode=result.valuation_mode,
        documents=result.documents,
        periods=period_summaries,
        validation=result.validation,
        red_flags=result.red_flags,
        data_quality=result.data_quality,
        entity=result.entity,
        equity_value=result.equity_value,
        dcf_assumptions=result.dcf_assumptions,
    )


# ── Endpoint: config ─────────────────────────────────────────────────────────

@router.get("/config", response_model=AOC4ConfigResponse)
async def get_config():
    """Report India config readiness and feature flags."""
    from agent.api.server import app
    settings = app.state.settings

    from agent.config.markets import is_india_config_ready
    india = is_india_config_ready(
        settings.in_risk_free_rate,
        settings.in_equity_risk_premium,
    )

    # Check OCR availability
    import shutil
    ocr_available = settings.ocr_enabled and bool(shutil.which("tesseract"))

    return AOC4ConfigResponse(
        india_config_ready=india["ready"],
        india_config_missing=india["missing"],
        ocr_available=ocr_available,
        feature_flags={
            "allow_llm_classifier": settings.allow_llm_classifier,
            "allow_llm_extraction": settings.allow_llm_extraction,
            "ocr_enabled": settings.ocr_enabled,
            "verdict_gating": settings.verdict_gating_enabled,
        },
    )
