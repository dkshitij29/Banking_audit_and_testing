"""Dependency container for the research pipeline."""

from dataclasses import dataclass, field
from agent.config import Settings
from agent.data.market_data import MarketDataProvider
from agent.sec.retriever import BM25Retriever
from agent.models.filing import FilingSection
from typing import Optional


@dataclass
class ResearchDeps:
    """Dependency container injected into every agent via RunContext."""
    settings: Settings
    market_data: MarketDataProvider
    filing_section_retriever: Optional[BM25Retriever] = None
    filing_sections: list[FilingSection] = field(default_factory=list)
    company_name: str = ""
