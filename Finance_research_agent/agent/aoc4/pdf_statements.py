"""PDF financial statements extraction — Schedule III table parsing.

Extracts Balance Sheet, P&L, Cash Flow tables from PDF pages classified
as ``financial_statements``.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pdfplumber

from agent.aoc4.models import (
    Item, PeriodStatements, Source, Provenance, Basis, Framework,
)
from agent.aoc4.numbers import parse_indian_number
from agent.aoc4.units import detect_unit, scale_to_absolute, UNIT_FACTORS
from agent.aoc4.fiscal import parse_date, months_between
from agent.aoc4.label_map import match_label


def extract_statements(
    file_path: str,
    doc_id: str,
    *,
    unit_override: str | None = None,
) -> list[PeriodStatements]:
    """Extract financial statements from a PDF.

    Returns ``PeriodStatements`` for each period (column) detected.
    """
    statements: list[PeriodStatements] = []

    try:
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            detected_unit = unit_override
            detected_dates: dict[int, date] = {}  # column_index → date
            basis = Basis.STANDALONE
            framework = Framework.UNKNOWN

            # ── First pass: detect unit, basis, framework ──────────────
            for i, page in enumerate(pdf.pages[:5]):
                text = page.extract_text() or ""

                if detected_unit is None:
                    for line in text.split("\n")[:15]:
                        u = detect_unit(line)
                        if u:
                            detected_unit = u
                            break

                if "consolidated" in text.lower():
                    basis = Basis.CONSOLIDATED
                if "ind as" in text.lower() or "indian accounting standards" in text.lower():
                    framework = Framework.IND_AS
                elif "accounting standards" in text.lower():
                    framework = Framework.INDIAN_GAAP

            if detected_unit is None:
                detected_unit = "crore"  # default assumption

            # ── Second pass: extract tables ────────────────────────────
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if not tables:
                    continue

                for table in tables:
                    periods = _parse_table(table, page_num, detected_unit, doc_id, basis, framework)
                    statements.extend(periods)

    except Exception:
        pass

    return statements


def _parse_table(
    table: list[list[str | None]],
    page_num: int,
    unit: str,
    doc_id: str,
    basis: Basis,
    framework: Framework,
) -> list[PeriodStatements]:
    """Parse a single table → one PeriodStatements per value column."""
    if not table or len(table) < 3:
        return []

    # ── Find header row with dates ──────────────────────────────────────
    header_row = None
    date_cols: list[tuple[int, date]] = []  # (col_index, date)

    for row_idx, row in enumerate(table[:5]):
        for col_idx, cell in enumerate(row):
            if cell:
                d = parse_date(str(cell))
                if d:
                    date_cols.append((col_idx, d))
                    if header_row is None:
                        header_row = row_idx

    if not date_cols:
        return []  # No date columns = not a financial statement

    # ── Identify note column (skip it) ──────────────────────────────────
    note_col = _find_note_column(table)

    # ── Build periods ──────────────────────────────────────────────────
    results: list[PeriodStatements] = []

    for col_idx, period_end in date_cols:
        items: dict[Item, Decimal | None] = {}
        provenance: dict[Item, Provenance] = {}

        for row in table:
            if not row or col_idx >= len(row):
                continue

            # Get label (first non-note column with text)
            label = None
            for lc in range(len(row)):
                if lc != note_col and lc < len(row) and row[lc] and str(row[lc]).strip():
                    label = str(row[lc]).strip()
                    break

            if not label:
                continue

            # Get value
            raw = str(row[col_idx]).strip() if col_idx < len(row) and row[col_idx] else ""

            # Skip if this cell looks like a label, not a number
            if any(c.isalpha() for c in raw[:3]):
                continue

            parsed = parse_indian_number(raw)
            if parsed.value is None:
                continue

            # Map label → Item
            item = match_label(label)
            if item is None:
                continue

            # Scale to absolute
            absolute = scale_to_absolute(parsed.value, unit)

            items[item] = absolute
            provenance[item] = Provenance(
                doc_id=doc_id,
                page=page_num + 1,
                label_as_found=label,
                raw_value=raw,
                dash_as_zero=parsed.dash_as_zero,
                source=Source.PDF_TEXT,
            )

        if not items:
            continue

        stmt = PeriodStatements(
            period_end=period_end,
            months=12,
            basis=basis,
            framework=framework,
            source=Source.PDF_TEXT,
            scale_detected=unit,
            scale_origin="statement_header" if unit != "crore" else "assumed",
            items=items,
            provenance=provenance,
            filing_doc_ids=[doc_id],
        )
        results.append(stmt)

    return results


def _find_note_column(table: list[list[str | None]]) -> int | None:
    """Find the 'Note' / 'Notes' column to exclude from value parsing."""
    if not table:
        return None

    first_row = table[0]
    for col_idx, cell in enumerate(first_row):
        if cell and re.match(r"^\s*(note|notes?|note\s*no\.?)\s*$", str(cell), re.IGNORECASE):
            return col_idx

    # Check second row too
    if len(table) > 1:
        for col_idx, cell in enumerate(table[1]):
            if cell and re.match(r"^\s*(note|notes?|note\s*no\.?)\s*$", str(cell), re.IGNORECASE):
                return col_idx

    return None
