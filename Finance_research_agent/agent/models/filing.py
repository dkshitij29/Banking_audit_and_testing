from pydantic import BaseModel, Field
from datetime import date
from typing import Optional


class FilingMetadata(BaseModel):
    filing_id: str
    ticker: str
    filing_type: str  # 10-K, 10-Q, 8-K, DEF 14A
    filing_date: date
    period_of_report_date: Optional[date] = None
    source_url: Optional[str] = None
    uploaded_at: Optional[date] = None


class FilingSection(BaseModel):
    section_id: str
    filing_id: str
    heading: str
    sub_heading: Optional[str] = None
    text: str
    page_number: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
