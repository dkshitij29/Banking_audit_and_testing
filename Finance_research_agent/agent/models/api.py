from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class UploadFilingRequest(BaseModel):
    ticker: str
    filing_type: Optional[str] = None  # 10-K, 10-Q, 8-K, DEF 14A


class UploadFilingResponse(BaseModel):
    filing_id: str
    sections_extracted: int
    status: str


class ResearchRequest(BaseModel):
    ticker: str
    filing_ids: list[str] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    report: str
    report_id: str


class DCFRequest(BaseModel):
    ticker: str
    growth_rate: float = 0.08
    wacc: Optional[float] = None
    terminal_growth: float = 0.03
    projection_years: int = 10


class CompsRequest(BaseModel):
    ticker: str
    peers: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    providers: dict


class FilingSummary(BaseModel):
    id: str
    type: str
    date: Optional[date] = None
    sections: int
