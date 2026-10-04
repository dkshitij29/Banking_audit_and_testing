import re
from pathlib import Path
from typing import Optional
import uuid
from datetime import date

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


from agent.models.filing import FilingMetadata, FilingSection


SECTION_HEADERS_10K = [
    "BUSINESS", "RISK FACTORS", "UNRESOLVED STAFF COMMENTS", "PROPERTIES",
    "LEGAL PROCEEDINGS", "MINE SAFETY DISCLOSURES",
    "DESCRIPTION OF REGISTERED SECURITIES", "SECURITY OWNERSHIP OF CERTAIN BENEFICIAL OWNERS",
    "DIRECTORS, EXECUTIVE OFFICERS AND CORPORATE GOVERNANCE", "EXECUTIVE COMPENSATION",
    "SECURITY OWNERSHIP OF CERTAIN BENEFICIAL OWNERS AND RELATED STOCKHOLDER MATTERS",
    "CERTAIN RELATIONSHIPS AND RELATED TRANSACTIONS", "PRINCIPAL ACCOUNTANT FEES AND SERVICES",
    "FINANCIAL STATEMENTS", "CHANGES AND DISAGREEMENTS WITH ACCOUNTANTS",
    "CONTROLS AND PROCEDURES", "OTHER INFORMATION", "EXHIBITS", "SIGNATURES",
]

SECTION_PATTERNS = {
    "item 1a": "RISK FACTORS",
    "item 1b": "UNRESOLVED STAFF COMMENTS",
    "item 1c": "MINE SAFETY DISCLOSURES",
    "item 2": "PROPERTIES",
    "item 3": "LEGAL PROCEEDINGS",
    "item 7a": "QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK",
    "item 7": "MANAGEMENT'S DISCUSSION AND ANALYSIS",
    "item 8": "FINANCIAL STATEMENTS",
    "item 9a": "CONTROLS AND PROCEDURES",
    "item 9b": "OTHER INFORMATION",
    "item 9": "CONTROLS AND PROCEDURES",
    "item 10": "DIRECTORS, EXECUTIVE OFFICERS AND CORPORATE GOVERNANCE",
    "item 11": "EXECUTIVE COMPENSATION",
    "item 12": "SECURITY OWNERSHIP",
    "item 13": "CERTAIN RELATIONSHIPS AND RELATED TRANSACTIONS",
    "item 14": "PRINCIPAL ACCOUNTANT FEES AND SERVICES",
    "item 15": "EXHIBITS AND FINANCIAL STATEMENT SCHEDULES",
    "item 1": "BUSINESS",
}


def parse_filing(file_path: str, filing_type: str = "10-K") -> list[FilingSection]:
    """Parse a PDF or HTML filing into FilingSection objects."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return _parse_pdf(path)
    elif path.suffix.lower() in (".html", ".htm"):
        return _parse_html(path)
    else:
        return _parse_text(path)


def _parse_pdf(path: Path) -> list[FilingSection]:
    if not pdfplumber:
        return _parse_fallback_text(path)

    sections: list[FilingSection] = []
    current_section_text: list[str] = []
    current_heading: str = "Introduction"
    page_num = 0

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_num += 1
            text = page.extract_text() or ""
            lines = text.strip().splitlines()

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue

                matched = _match_section_header(stripped)
                if matched:
                    if current_section_text:
                        sections.append(FilingSection(
                            section_id=str(uuid.uuid4()),
                            filing_id="",
                            heading=current_heading,
                            text="\n".join(current_section_text),
                            page_number=page_num,
                        ))
                        current_section_text = []
                    current_heading = matched

                current_section_text.append(stripped)

    if current_section_text:
        sections.append(FilingSection(
            section_id=str(uuid.uuid4()),
            filing_id="",
            heading=current_heading,
            text="\n".join(current_section_text),
            page_number=page_num,
        ))

    return sections


def _parse_html(path: Path) -> list[FilingSection]:
    if not BeautifulSoup:
        return _parse_fallback_text(path)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")

    sections: list[FilingSection] = []
    headings = soup.find_all(["h1", "h2", "h3", "h4"])

    for i, heading in enumerate(headings):
        text_parts: list[str] = []
        elem = heading.find_next_sibling()
        while elem:
            if elem.name in ("h1", "h2", "h3", "h4"):
                if i < len(headings) - 1 and elem == headings[i + 1]:
                    break
            text_parts.append(elem.get_text(strip=True))
            elem = elem.find_next_sibling()

        if text_parts:
            sections.append(FilingSection(
                section_id=str(uuid.uuid4()),
                filing_id="",
                heading=heading.get_text(strip=True),
                text="\n".join(text_parts),
            ))

    return sections


def _parse_text(path: Path) -> list[FilingSection]:
    return _parse_fallback_text(path)


def _parse_fallback_text(path: Path) -> list[FilingSection]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.strip().splitlines()

    sections: list[FilingSection] = []
    current_text: list[str] = []
    current_heading = "Full Document"

    for line in lines:
        stripped = line.strip()
        matched = _match_section_header(stripped)
        if matched:
            if current_text:
                sections.append(FilingSection(
                    section_id=str(uuid.uuid4()),
                    filing_id="",
                    heading=current_heading,
                    text="\n".join(current_text),
                ))
                current_text = []
            current_heading = matched
        current_text.append(stripped)

    if current_text:
        sections.append(FilingSection(
            section_id=str(uuid.uuid4()),
            filing_id="",
            heading=current_heading,
            text="\n".join(current_text),
        ))

    return sections


def _match_section_header(line: str) -> Optional[str]:
    lowered = line.lower().strip()

    for pattern, heading in SECTION_PATTERNS.items():
        if pattern in lowered:
            return heading

    for header in SECTION_HEADERS_10K:
        if header.lower() in lowered:
            return header

    if re.match(r"^ITEM\s+\d+", line, re.IGNORECASE):
        match = re.search(r"ITEM\s+(\d+)([a-zA-Z]?)", line, re.IGNORECASE)
        if match:
            item_key = f"item {match.group(1)}{match.group(2).lower()}"
            return SECTION_PATTERNS.get(item_key, line.strip())

    return None


def create_filing_metadata(
    ticker: str,
    filing_type: str,
    filing_path: str,
    filing_date: Optional[date] = None,
) -> FilingMetadata:
    return FilingMetadata(
        filing_id=str(uuid.uuid4()),
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date or date.today(),
        source_url=filing_path,
    )
