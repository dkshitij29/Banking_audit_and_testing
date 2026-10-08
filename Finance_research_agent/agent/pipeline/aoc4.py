"""AOC-4 analysis pipeline — stages 0–6.

Orchestrates bundle ingestion, classification, parsing, validation,
and produces the extraction response.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from agent.aoc4.models import (
    DocumentInfo, PeriodStatements, PeriodSummary,
    ValidationIssue, IssueSeverity, DataQuality, Source, ValuationMode,
    EntityInfo, EquityValueRange, Item,
)
from agent.aoc4.bundle import Bundle, safe_unzip, cleanup_bundle
from agent.aoc4.classifier import classify_document, get_text_sample
from agent.aoc4.xbrl_reader import extract_facts as xbrl_extract
from agent.aoc4.pdf_statements import extract_statements as pdf_extract
from agent.aoc4.validation import run_validation
from agent.aoc4.sections import detect_sections
from agent.aoc4.to_dcf import periods_to_dcf_inputs
from agent.aoc4.redflags import detect_red_flags
from agent.valuation.wacc import calculate_wacc
from agent.valuation.dcf import calculate_dcf
from agent.valuation.synthesis import combine_valuations
from agent.valuation.multiples import compute_comps
from agent.valuation.unlisted import apply_dlom
from agent.valuation.sector_router import is_financial_sector
from agent.valuation.verdict_in import derive_verdict_in
from agent.models.valuation import DCFInputs, CompsData
from agent.config import Settings
from agent.config.markets import get_market_config
from agent.models.api import StageResult
from agent.models.valuation import DCFInputs
from agent.data.market_data import MarketDataProvider
from fastapi import UploadFile


@dataclass
class AOC4Result:
    """Full pipeline output."""
    stages: list[StageResult] = field(default_factory=list)
    documents: list[DocumentInfo] = field(default_factory=list)
    periods: list[PeriodStatements] = field(default_factory=list)
    validation: list[ValidationIssue] = field(default_factory=list)
    data_quality: DataQuality = field(default_factory=DataQuality)
    entity: EntityInfo = field(default_factory=EntityInfo)
    valuation_mode: ValuationMode = ValuationMode.EXTRACTION_ONLY
    error_code: str | None = None
    # Valuation results (stages 4–6)
    equity_value: EquityValueRange | None = None
    fair_value_mid: float = 0.0
    fair_value_low: float = 0.0
    fair_value_high: float = 0.0
    current_price: float = 0.0
    upside_pct: float = 0.0
    verdict: str = "NOT_APPLICABLE"
    rating: str = "N/A"
    confidence: str = "Low"
    dcf_assumptions: dict = field(default_factory=dict)
    red_flags: list = field(default_factory=list)


class AOC4Pipeline:
    """Stages 0–3: Bundle → Ingest → Parse → Validate.

    Full analysis (stages 4–6: value, model, synthesize) comes in Phase 3.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(
        self,
        files: list[UploadFile],
        *,
        cin: str | None = None,
        ticker: str | None = None,
        entity_type: str = "auto",
        unit_override: str | None = None,
        doc_overrides: dict[str, str] | None = None,
    ) -> AOC4Result:
        result = AOC4Result()

        # ── Stage 0: BUNDLE ──────────────────────────────────────────────
        try:
            bundle = safe_unzip(
                files, self.settings.upload_dir,
                max_files=self.settings.max_upload_files,
                max_total_mb=self.settings.max_upload_mb,
            )
        except Exception as e:
            result.stages.append(StageResult(stage="0. BUNDLE", status="error", summary=str(e)))
            result.error_code = "BUNDLE_ERROR"
            return result

        try:
            result.stages.append(StageResult(
                stage="0. BUNDLE", status="complete",
                summary=f"{len(bundle.documents)} files, {bundle.total_size_bytes / 1024:.0f} KB",
            ))

            # ── Stage 1: INGEST (classify) ───────────────────────────────
            for doc in bundle.documents:
                file_path = bundle.files_dir / doc.filename
                text = get_text_sample(str(file_path))
                doc = classify_document(doc, text)
                result.documents.append(doc)

            # Apply user overrides
            if doc_overrides:
                for filename, override_type in doc_overrides.items():
                    for doc in result.documents:
                        if filename in doc.filename:
                            from agent.aoc4.models import DocType
                            try:
                                doc.doc_type = DocType(override_type)
                                doc.user_override = True
                                doc.confidence = 1.0
                            except ValueError:
                                pass

            result.stages.append(StageResult(
                stage="1. INGEST", status="complete",
                summary=f"Classified {len(result.documents)} documents",
            ))

            # ── Stage 2: PARSE (XBRL → PDF → statements) ────────────────
            all_periods: list[PeriodStatements] = []

            for doc in result.documents:
                file_path = bundle.files_dir / doc.filename

                if doc.doc_type.value == "xbrl":
                    try:
                        periods = xbrl_extract(str(file_path))
                        all_periods.extend(periods)
                    except Exception as e:
                        result.validation.append(ValidationIssue(
                            code="XBRL_PARSE_ERROR",
                            severity=IssueSeverity.WARN,
                            message=f"Failed to parse XBRL: {e}",
                            detail={"doc_id": doc.doc_id},
                        ))

                elif doc.doc_type.value == "financial_statements":
                    try:
                        periods = pdf_extract(str(file_path), doc.doc_id, unit_override=unit_override)
                        all_periods.extend(periods)
                    except Exception as e:
                        result.validation.append(ValidationIssue(
                            code="PDF_PARSE_ERROR",
                            severity=IssueSeverity.WARN,
                            message=f"Failed to parse PDF statements: {e}",
                            detail={"doc_id": doc.doc_id},
                        ))

            # Sort by period_end ascending
            all_periods.sort(key=lambda p: p.period_end)

            if not all_periods:
                result.stages.append(StageResult(
                    stage="2. PARSE", status="partial",
                    summary="No financial periods extracted",
                ))
                result.validation.append(ValidationIssue(
                    code="NO_FINANCIAL_STATEMENTS",
                    severity=IssueSeverity.ERROR,
                    message="No financial statements found in the bundle",
                ))
            else:
                result.periods = all_periods
                result.stages.append(StageResult(
                    stage="2. PARSE", status="complete",
                    summary=f"Extracted {len(all_periods)} period(s), "
                            f"source: {all_periods[0].source.value}",
                ))

            # ── Stage 3: VALIDATE ────────────────────────────────────────
            issues = run_validation(all_periods)
            result.validation = issues

            error_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
            warn_count = sum(1 for i in issues if i.severity == IssueSeverity.WARN)

            if error_count:
                result.stages.append(StageResult(
                    stage="3. VALIDATE", status="error",
                    summary=f"{error_count} error(s), {warn_count} warning(s)",
                ))
                result.error_code = issues[0].code if issues else "VALIDATION_FAILED"
            else:
                result.stages.append(StageResult(
                    stage="3. VALIDATE", status="complete",
                    summary=f"0 errors, {warn_count} warning(s)",
                ))

            # ── Data quality ─────────────────────────────────────────────
            if all_periods:
                latest = max(p.period_end for p in all_periods)
                result.data_quality = DataQuality(
                    score="high" if not issues else ("medium" if not error_count else "low"),
                    primary_source=all_periods[0].source,
                    periods_available=len(all_periods),
                    data_as_of=latest,
                    staleness_days=(date.today() - latest).days,
                    notes=[i.message for i in issues if i.severity == IssueSeverity.WARN],
                )

            # ── Entity ───────────────────────────────────────────────────
            listed_status = entity_type if entity_type != "auto" else "unknown"
            if ticker and not listed_status:
                listed_status = "listed"
            elif cin and not listed_status:
                # CIN hints: L = Limited (listed possible), U = Unlimited (usually unlisted)
                listed_status = "listed" if cin.startswith("L") else "unknown"

            result.entity = EntityInfo(
                cin=cin,
                ticker=ticker,
                listed=listed_status,
                framework=all_periods[0].framework if all_periods else None,
                basis=all_periods[0].basis if all_periods else None,
            )

            # ── Stage 4: ANALYSE (red flags) ─────────────────────────────
            all_sections_text: dict[str, str] = {}
            for doc in result.documents:
                file_path = bundle.files_dir / doc.filename
                text = get_text_sample(str(file_path), pages=50)
                if text:
                    sections = detect_sections(text, doc.doc_id)
                    for sec in sections:
                        all_sections_text[sec.heading[:50].upper()] = sec.text

            # Map standard section types
            sections_for_flags = {}
            for key, val in all_sections_text.items():
                for section_type in ["AUDITOR_REPORT", "CARO_ANNEXURE", "BOARD_REPORT"]:
                    if section_type[:10] in key:
                        sections_for_flags[section_type] = val

            red_flags = detect_red_flags(sections_for_flags, all_periods, doc.id if result.documents else "d01")
            result.red_flags = red_flags

            # Check for distressed (going concern / adverse opinion)
            high_flags = [f for f in red_flags if f.severity == "high"]
            distressed_codes = {"AUD_GOING_CONCERN", "AUD_ADVERSE_OPINION", "AUD_DISCLAIMER"}
            is_distressed = any(f.code in distressed_codes for f in red_flags)

            # Also check negative net worth + negative CFO
            if all_periods:
                latest = all_periods[-1]
                neg_equity = (latest.items.get(Item.TOTAL_EQUITY) or 0) < 0
                neg_cfo = (latest.items.get(Item.CASH_FROM_OPERATIONS) or 0) < 0
                if neg_equity and neg_cfo:
                    is_distressed = True

            result.stages.append(StageResult(
                stage="4. ANALYSE", status="complete",
                summary=f"{len(red_flags)} red flag(s) detected",
            ))

            # ── Stage 5: MODEL (valuation) ───────────────────────────────
            if not all_periods or error_count:
                result.valuation_mode = ValuationMode.EXTRACTION_ONLY
                result.stages.append(StageResult(
                    stage="5. MODEL", status="skipped",
                    summary="Skipped due to extraction errors or missing data",
                ))
            elif is_distressed:
                result.valuation_mode = ValuationMode.DISTRESSED
                result.stages.append(StageResult(
                    stage="5. MODEL", status="skipped",
                    summary="Skipped: entity in distress (going concern / adverse opinion)",
                ))
            elif is_financial_sector(
                sector=result.entity.sector,
                description=" ".join(sections_for_flags.get("BOARD_REPORT", "")),
            ):
                result.valuation_mode = ValuationMode.UNSUPPORTED_SECTOR
                result.stages.append(StageResult(
                    stage="5. MODEL", status="skipped",
                    summary="Skipped: financial sector — FCFF DCF not applicable",
                ))
            else:
                try:
                    # Get market config
                    cfg = get_market_config(
                        "IN" if self.settings.in_risk_free_rate else "US",
                        self.settings.in_risk_free_rate,
                        self.settings.in_equity_risk_premium,
                    )

                    if cfg.risk_free_rate is None or cfg.equity_risk_premium is None:
                        result.valuation_mode = ValuationMode.COMPS_ONLY
                        result.stages.append(StageResult(
                            stage="5. MODEL", status="partial",
                            summary="DCF skipped: IN_RISK_FREE_RATE / IN_EQUITY_RISK_PREMIUM not set",
                        ))
                    else:
                        # Build DCFInputs
                        dcf_inputs = periods_to_dcf_inputs(
                            all_periods,
                            ticker=ticker or "AOC4",
                            risk_free_rate=cfg.risk_free_rate,
                            equity_risk_premium=cfg.equity_risk_premium,
                            default_tax_rate=cfg.default_tax_rate,
                        )

                        # Compute beta for listed
                        if listed_status == "listed" and ticker:
                            try:
                                market_data = MarketDataProvider(self.settings, market="IN")
                                normalized = market_data.normalize_ticker(ticker)
                                beta = market_data.compute_beta(normalized, cfg.beta_index)
                                if beta:
                                    dcf_inputs.beta = beta
                            except Exception:
                                pass  # use default beta

                        # Run DCF
                        dcf_result = calculate_dcf(dcf_inputs)
                        result.dcf_assumptions = dcf_result.assumptions

                        # Fetch price for listed
                        current_price = None
                        if listed_status == "listed" and ticker:
                            try:
                                market_data = MarketDataProvider(self.settings, market="IN")
                                normalized = market_data.normalize_ticker(ticker)
                                price_data = market_data.fetch_price(normalized)
                                if price_data:
                                    current_price = price_data.get("current_price")
                            except Exception:
                                pass

                        if current_price:
                            result.valuation_mode = ValuationMode.MARKET_RELATIVE
                            result.current_price = current_price
                        elif listed_status == "listed":
                            result.valuation_mode = ValuationMode.INTRINSIC_RANGE
                        else:
                            result.valuation_mode = ValuationMode.INTRINSIC_RANGE

                        # Comps (if we have peer data)
                        comps_result = None
                        if ticker and listed_status == "listed":
                            try:
                                market_data = MarketDataProvider(self.settings, market="IN")
                                normalized = market_data.normalize_ticker(ticker)
                                peers = market_data.fetch_peers(normalized)
                                if peers:
                                    comps_result = compute_comps(normalized, peers, market_data)
                            except Exception:
                                pass

                        # Combine
                        combined = combine_valuations(dcf_result, comps_result or CompsData(ticker=ticker or "AOC4"))
                        result.fair_value_mid = combined["fair_value_mid"]
                        result.fair_value_low = combined["fair_value_low"]
                        result.fair_value_high = combined["fair_value_high"]

                        if current_price:
                            result.upside_pct = ((result.fair_value_mid - current_price) / current_price * 100) if current_price > 0 else 0

                        # Apply DLOM for unlisted
                        if result.valuation_mode == ValuationMode.INTRINSIC_RANGE:
                            dlom = self.settings.unlisted_dlom
                            result.equity_value = EquityValueRange(
                                low_inr=apply_dlom(result.fair_value_low, dlom),
                                mid_inr=apply_dlom(result.fair_value_mid, dlom),
                                high_inr=apply_dlom(result.fair_value_high, dlom),
                                dlom_applied=dlom,
                            )

                        result.stages.append(StageResult(
                            stage="5. MODEL", status="complete",
                            summary=f"DCF: {dcf_result.implied_price:.0f}, "
                                    f"Comps: {comps_result.implied_median_price:.0f if comps_result else 'N/A'}",
                        ))

                except Exception as e:
                    result.valuation_mode = ValuationMode.EXTRACTION_ONLY
                    result.stages.append(StageResult(
                        stage="5. MODEL", status="error",
                        summary=f"Valuation failed: {str(e)}",
                    ))

            # ── Stage 6: SYNTHESIZE (verdict) ────────────────────────────
            verdict = derive_verdict_in(
                dcf_mid=result.dcf_assumptions.get("implied_price") if result.dcf_assumptions else None,
                comps_mid=result.fair_value_mid if result.valuation_mode == ValuationMode.MARKET_RELATIVE else None,
                current_price=result.current_price,
                reference_price=None,
                mode=result.valuation_mode,
                flags=red_flags,
                issues=result.validation,
                max_divergence=self.settings.max_method_divergence,
            )
            result.verdict = verdict.verdict
            result.rating = verdict.rating
            result.confidence = verdict.confidence

            result.stages.append(StageResult(
                stage="6. SYNTHESIZE", status="complete",
                summary=f"Verdict: {result.verdict} ({result.confidence} confidence)",
            ))

        finally:
            cleanup_bundle(bundle)

        return result
