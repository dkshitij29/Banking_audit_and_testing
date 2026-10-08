"""India section detection — FilingSection[] for RAG.

Detects section headings in AOC-4 documents and maps them to section types
compatible with the existing BM25Retriever.
"""

from __future__ import annotations

from agent.models.filing import FilingSection
from agent.aoc4.models import DocType


_INDIA_SECTION_HEADINGS: list[tuple[str, list[str]]] = [
    ("AUDITOR_REPORT", ["independent auditor's report", "auditors' report", "report on the audit"]),
    ("CARO_ANNEXURE", ["annexure to the independent auditor's report", "companies (auditor's report) order"]),
    ("BOARD_REPORT", ["board's report", "directors' report"]),
    ("SIGNIFICANT_ACCOUNTING_POLICIES", ["significant accounting policies", "notes 1", "note 1 significant accounting policies"]),
    ("NOTES_TO_ACCOUNTS", ["notes to the financial statements", "notes forming part of the financial statements"]),
    ("RELATED_PARTY_NOTE", ["related party disclosures", "related party transactions"]),
    ("CONTINGENT_LIABILITIES_NOTE", ["contingent liabilities", "note contingent liabilities"]),
    ("BORROWINGS_NOTE", ["borrowings", "details of borrowings"]),
    ("BALANCE_SHEET", ["balance sheet as at", "balance sheet"]),
    ("PROFIT_AND_LOSS", ["statement of profit and loss", "profit and loss account"]),
    ("CASH_FLOW", ["cash flow statement"]),
    ("ANNEXURE_AOC2", ["form no. aoc-2", "form aoc-2"]),
]


def detect_sections(text: str, doc_id: str = "d01", filing_id: str = "aoc4") -> list[FilingSection]:
    """Split document text into ``FilingSection[]`` by heading detection.

    Each section carries ``heading``, ``text``, and ``page_number``.
    """
    sections: list[FilingSection] = []
    lines = text.split("\n")

    current_section_type: str | None = None
    current_heading: str = ""
    current_text: list[str] = []
    page_number = 1

    for i, line in enumerate(lines):
        # Simple page break detection
        if "page " in line.lower() and "-" in line and len(line.strip()) < 30:
            page_number += 1
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # Check if this line is a section heading
        matched_type: str | None = None
        for section_type, patterns in _INDIA_SECTION_HEADINGS:
            for pattern in patterns:
                if pattern.lower() in stripped.lower():
                    matched_type = section_type
                    break
            if matched_type:
                break

        if matched_type:
            # Flush previous section
            if current_section_type and current_text:
                sections.append(FilingSection(
                    section_id=f"{filing_id}_{current_section_type}_{len(sections)}",
                    filing_id=filing_id,
                    heading=current_heading,
                    text="\n".join(current_text)[:4000],  # cap section size
                    page_number=page_number,
                ))

            current_section_type = matched_type
            current_heading = stripped
            current_text = []
        else:
            current_text.append(stripped)

    # Flush last section
    if current_section_type and current_text:
        sections.append(FilingSection(
            section_id=f"{filing_id}_{current_section_type}_{len(sections)}",
            filing_id=filing_id,
            heading=current_heading,
            text="\n".join(current_text)[:4000],
            page_number=page_number,
        ))

    return sections
