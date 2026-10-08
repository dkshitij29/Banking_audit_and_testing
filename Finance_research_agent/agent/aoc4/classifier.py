"""Deterministic document classifier for AOC-4 bundles.

Classifies each document (or page range) by reading headings + filename.
"""

from __future__ import annotations

import re
from agent.aoc4.models import DocumentInfo, DocType, Basis, Framework


# ── Classification rules ─────────────────────────────────────────────────────

_RULES: list[tuple[DocType, list[str], list[str]]] = [
    # (doc_type, filename_patterns, heading_patterns)
    (
        DocType.XBRL,
        [".xbrl", ".xml"],
        ["<xbrli:xs", "<xbrli:context", "<xbrli:fact"],
    ),
    (
        DocType.FORM,
        [],
        ["form no. aoc-4", "form aoc-4", "aoc-4 cfs", "section 137"],
    ),
    (
        DocType.AUDITOR_REPORT,
        [],
        ["independent auditor's report", "auditors' report", "report on the audit of the"],
    ),
    (
        DocType.BOARD_REPORT,
        [],
        ["board's report", "directors' report", "your directors have pleasure"],
    ),
    (
        DocType.FINANCIAL_STATEMENTS,
        [],
        [
            "balance sheet as at", "statement of profit and loss",
            "cash flow statement", "notes to the financial statements",
            "statement of changes in equity",
        ],
    ),
    (
        DocType.ANNEXURE,
        [],
        ["form no. aoc-2", "form aoc-1", "annual report on csr", "form no. mr-3"],
    ),
]


def classify_document(
    doc: DocumentInfo,
    text_sample: str = "",
    *,
    max_lines: int = 50,
) -> DocumentInfo:
    """Classify a single document from filename + text sample.

    Returns the updated ``DocumentInfo`` with ``doc_type``, ``confidence``,
    ``basis``, ``framework``, and ``period_end`` populated.
    """
    filename_lower = doc.filename.lower()
    text_lower = text_sample.lower()

    # ── Filename-based classification ────────────────────────────────────
    for doc_type, filename_patterns, _ in _RULES:
        for pat in filename_patterns:
            if filename_lower.endswith(pat):
                doc.doc_type = doc_type
                doc.confidence = 0.9
                doc.classification_evidence = [f"filename ends with {pat!r}"]
                break
        if doc.doc_type != DocType.OTHER:
            break

    # ── Heading-based classification (text sample) ───────────────────────
    if doc.doc_type in (DocType.OTHER, DocType.FORM) and text_lower:
        lines = text_lower.split("\n")[:max_lines]
        text_block = "\n".join(lines)

        for doc_type, _, heading_patterns in _RULES:
            for pat in heading_patterns:
                if pat in text_block:
                    doc.doc_type = doc_type
                    doc.confidence = max(doc.confidence, 0.8)
                    doc.classification_evidence.append(f"heading: {pat!r}")
                    break
            if doc.doc_type != DocType.OTHER and doc.doc_type != DocType.FORM:
                break

    # ── Basis detection ──────────────────────────────────────────────────
    if "consolidated financial statements" in text_lower or "consolidated balance sheet" in text_lower:
        doc.basis = Basis.CONSOLIDATED
        doc.classification_evidence.append("consolidated keyword found")
    elif "standalone" in text_lower:
        doc.basis = Basis.STANDALONE
    elif doc.basis == Basis.UNKNOWN and "consolidated" not in text_lower:
        doc.basis = Basis.STANDALONE  # default

    # ── Framework detection ──────────────────────────────────────────────
    # (stored in classification_evidence; full detection in FilingSection)
    if "ind as" in text_lower or "indian accounting standards" in text_lower:
        doc.classification_evidence.append("framework: ind_as")
    elif "accounting standards" in text_lower and "ind as" not in text_lower:
        doc.classification_evidence.append("framework: indian_gaap (tentative)")

    # ── Period end detection ─────────────────────────────────────────────
    if text_sample:
        from agent.aoc4.fiscal import parse_date
        for line in text_lower.split("\n")[:max_lines]:
            if "ended" in line or "as at" in line:
                d = parse_date(line)
                if d:
                    doc.period_end = d
                    doc.classification_evidence.append(f"period_end: {d.isoformat()}")
                    break

    # ── Low confidence → OTHER ───────────────────────────────────────────
    if doc.confidence < 0.6:
        doc.doc_type = DocType.OTHER

    return doc


def get_text_sample(file_path: str, pages: int = 3) -> str:
    """Extract text from the first *pages* of a PDF for classification.

    Returns empty string for non-PDF files.
    """
    try:
        import pdfplumber
    except ImportError:
        return ""

    text_parts = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages[:pages]):
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception:
        pass

    return "\n".join(text_parts)
