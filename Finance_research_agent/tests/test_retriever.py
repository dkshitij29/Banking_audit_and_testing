"""Tests for BM25 retriever."""

import pytest
from agent.models.filing import FilingSection
from agent.sec.retriever import BM25Retriever


class TestBM25Retriever:
    def _make_sections(self) -> list[FilingSection]:
        return [
            FilingSection(
                section_id="s1",
                filing_id="f1",
                heading="BUSINESS",
                text="Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide. The Company also sells various related services.",
            ),
            FilingSection(
                section_id="s2",
                filing_id="f1",
                heading="RISK FACTORS",
                text="Our business and results of operations could be harmed by events beyond our control, including natural disasters, pandemic outbreaks, acts of terrorism, political unrest, and cyber security incidents.",
            ),
            FilingSection(
                section_id="s3",
                filing_id="f1",
                heading="MANAGEMENT DISCUSSION",
                text="Net sales increased 2% to $394.3 billion. Products revenue increased $11.0 billion or 2%. Services revenue increased $11.0 billion or 8%. Gross margin was 45.9%.",
            ),
        ]

    def test_build_index(self):
        sections = self._make_sections()
        retriever = BM25Retriever.build_index(sections)
        assert retriever._bm25 is not None

    def test_search_business(self):
        sections = self._make_sections()
        retriever = BM25Retriever.build_index(sections)

        results = retriever.search("smartphones computers tablets")
        assert len(results) > 0

    def test_search_risk(self):
        sections = self._make_sections()
        retriever = BM25Retriever.build_index(sections)

        results = retriever.search("cyber security natural disasters pandemic")
        assert len(results) > 0

    def test_relevant_heading(self):
        sections = self._make_sections()
        retriever = BM25Retriever.build_index(sections)

        results = retriever.search("revenue gross margin net sales")
        assert len(results) > 0

    def test_empty_sections(self):
        retriever = BM25Retriever.build_index([])
        results = retriever.search("test query")
        assert results == []

    def test_top_k_limit(self):
        sections = self._make_sections()
        retriever = BM25Retriever.build_index(sections)

        results = retriever.search("business", top_k=2)
        assert len(results) <= 2
