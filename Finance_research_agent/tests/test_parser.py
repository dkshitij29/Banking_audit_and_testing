"""Tests for SEC filing parser."""

import pytest
from pathlib import Path
from agent.sec.parser import parse_filing, _match_section_header, create_filing_metadata
from datetime import date


class TestMatchSectionHeader:
    def test_item_1(self):
        assert _match_section_header("ITEM 1. BUSINESS") == "BUSINESS"

    def test_item_1a(self):
        assert _match_section_header("Item 1A. Risk Factors") == "RISK FACTORS"

    def test_direct_name(self):
        assert _match_section_header("RISK FACTORS") == "RISK FACTORS"

    def test_no_match(self):
        assert _match_section_header("Random text here") is None

    def test_item_7(self):
        assert _match_section_header("Item 7. Management's Discussion and Analysis") == "MANAGEMENT'S DISCUSSION AND ANALYSIS"

    def test_item_8(self):
        result = _match_section_header("ITEM 8. FINANCIAL STATEMENTS")
        assert result in ("FINANCIAL STATEMENTS", "FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA")

    def test_financial_statements_heading(self):
        assert _match_section_header("FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA") == "FINANCIAL STATEMENTS"

    def test_controls_heading(self):
        assert _match_section_header("Controls and Procedures") == "CONTROLS AND PROCEDURES"


class TestCreateMetadata:
    def test_creates_metadata(self):
        meta = create_filing_metadata("AAPL", "10-K", "/path/to/filing.pdf", date(2024, 12, 31))
        assert meta.ticker == "AAPL"
        assert meta.filing_type == "10-K"
        assert meta.filing_date == date(2024, 12, 31)
        assert meta.filing_id


class TestParseText:
    def test_parse_text_file(self, tmp_path):
        content = """
        ITEM 1. BUSINESS

        Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables.

        ITEM 1A. RISK FACTORS

        The company's business, reputation, financial condition, operating results and stock price may be adversely affected.

        ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS

        The following discussion should be read in conjunction with the consolidated financial statements.
        """
        test_file = tmp_path / "test.txt"
        test_file.write_text(content)

        sections = parse_filing(str(test_file))
        assert len(sections) >= 3
        headings = [s.heading for s in sections]
        assert "BUSINESS" in headings
        assert "RISK FACTORS" in headings
