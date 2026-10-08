"""Phase 1: AOC-4 bundle, classifier, numbers, validation tests."""

import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock, PropertyMock
import tempfile
import zipfile
import os


class TestIndianNumberParser:
    def test_indian_grouping(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("1,23,456.78")
        assert r.value == Decimal("123456.78")

    def test_indian_grouping_large(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("12,34,56,789")
        assert r.value == Decimal("123456789")

    def test_parentheses_negative(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("(1,234.50)")
        assert r.value == Decimal("-1234.50")

    def test_double_negative(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("(-1,234)")
        assert r.value == Decimal("1234")

    def test_dash_zero(self):
        from agent.aoc4.numbers import parse_indian_number
        for val in ["—", "–", "-", "Nil", "NIL"]:
            r = parse_indian_number(val)
            assert r.value == Decimal("0"), f"Failed for {val!r}"
            assert r.dash_as_zero is True

    def test_currency_prefix(self):
        from agent.aoc4.numbers import parse_indian_number
        for prefix in ["₹ 1,234", "Rs. 1,234", "INR 1,234"]:
            r = parse_indian_number(prefix)
            assert r.value == Decimal("1234"), f"Failed for {prefix!r}"

    def test_footnote_markers(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("1,234*")
        assert r.value == Decimal("1234")

    def test_percentage_rejected(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("12.5%")
        assert r.value is None

    def test_note_reference_rejected(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("3.1.2")
        assert r.value is None

    def test_format_inr_crore(self):
        from agent.aoc4.numbers import format_inr
        result = format_inr(12345678.90, unit="crore")
        assert "1.23" in result
        assert "Cr" in result

    def test_format_inr_grouping(self):
        from agent.aoc4.numbers import format_inr
        result = format_inr(1234567890.0, unit="crore")
        assert "123" in result  # 123.46 Cr
        assert "Cr" in result

    def test_nbsp_separated(self):
        from agent.aoc4.numbers import parse_indian_number
        r = parse_indian_number("1 23 456")
        assert r.value == Decimal("123456")


class TestUnits:
    def test_detect_lakhs(self):
        from agent.aoc4.units import detect_unit
        assert detect_unit("(₹ in Lakhs)") == "lakh"
        assert detect_unit("(Rs. in Lacs)") == "lakh"

    def test_detect_crore(self):
        from agent.aoc4.units import detect_unit
        assert detect_unit("(Rs. in crore)") == "crore"
        assert detect_unit("Amount in ₹ 'Cr") == "crore"

    def test_detect_million(self):
        from agent.aoc4.units import detect_unit
        assert detect_unit("(INR in Millions)") == "million"

    def test_detect_thousand(self):
        from agent.aoc4.units import detect_unit
        assert detect_unit("(Amount in ₹ '000)") == "thousand"

    def test_detect_actual(self):
        from agent.aoc4.units import detect_unit
        assert detect_unit("Amount in Rupees") == "actual"

    def test_scale_to_absolute(self):
        from agent.aoc4.units import scale_to_absolute
        assert scale_to_absolute(Decimal("100"), "lakh") == Decimal("10000000")
        assert scale_to_absolute(Decimal("100"), "crore") == Decimal("1000000000")

    def test_scale_round_trip(self):
        from agent.aoc4.units import scale_to_absolute, scale_from_absolute
        for unit in ["lakh", "crore", "thousand", "million"]:
            original = Decimal("1234.56")
            absolute = scale_to_absolute(original, unit)
            back = scale_from_absolute(absolute, unit)
            assert back == original, f"Round-trip failed for {unit}"


class TestFiscal:
    def test_parse_date_indian(self):
        from agent.aoc4.fiscal import parse_date
        d = parse_date("31 March 2025")
        assert d == date(2025, 3, 31)

    def test_parse_date_us_format(self):
        from agent.aoc4.fiscal import parse_date
        d = parse_date("March 31, 2025")
        assert d == date(2025, 3, 31)

    def test_parse_date_dotted(self):
        from agent.aoc4.fiscal import parse_date
        d = parse_date("31.03.2025")
        assert d == date(2025, 3, 31)

    def test_parse_date_slash(self):
        from agent.aoc4.fiscal import parse_date
        d = parse_date("31/03/2025")
        assert d == date(2025, 3, 31)

    def test_period_label_fy(self):
        from agent.aoc4.fiscal import period_label
        assert period_label(date(2025, 3, 31)) == "FY25"

    def test_period_label_non_march(self):
        from agent.aoc4.fiscal import period_label
        assert period_label(date(2024, 12, 31)) == "YE Dec-2024"

    def test_is_standard_period(self):
        from agent.aoc4.fiscal import is_standard_period
        assert is_standard_period(date(2024, 4, 1), date(2025, 3, 31)) is True
        assert is_standard_period(date(2024, 1, 1), date(2024, 12, 31)) is True

    def test_months_between(self):
        from agent.aoc4.fiscal import months_between
        assert months_between(date(2024, 4, 1), date(2025, 3, 31)) == 12


class TestBundle:
    def test_safe_unzip_simple(self, tmp_path):
        from agent.aoc4.bundle import safe_unzip, cleanup_bundle
        from fastapi import UploadFile
        from io import BytesIO

        # Create a fake upload
        content = b"test pdf content"
        upload = UploadFile(
            filename="test.pdf",
            file=BytesIO(content),
        )

        bundle = safe_unzip([upload], tmp_path)
        assert len(bundle.documents) == 1
        assert bundle.documents[0].filename == "test.pdf"

        # Verify file was written
        file_path = bundle.files_dir / "test.pdf"
        assert file_path.exists()
        assert file_path.read_bytes() == content

        cleanup_bundle(bundle)

    def test_zip_slip_protection(self, tmp_path):
        from agent.aoc4.bundle import safe_unzip, BundleError
        from fastapi import UploadFile
        from io import BytesIO

        # Create a malicious zip
        zip_data = BytesIO()
        with zipfile.ZipFile(zip_data, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0")

        zip_data.seek(0)
        upload = UploadFile(
            filename="evil.zip",
            file=zip_data,
        )

        with pytest.raises(BundleError, match="UNSAFE_ZIP_ENTRY"):
            safe_unzip([upload], tmp_path)

    def test_size_limit(self, tmp_path):
        from agent.aoc4.bundle import safe_unzip, BundleError
        from fastapi import UploadFile
        from io import BytesIO

        # Create a large-ish upload (over 1MB limit)
        content = b"x" * (2 * 1024 * 1024)
        upload = UploadFile(
            filename="large.pdf",
            file=BytesIO(content),
        )

        with pytest.raises(BundleError, match="BUNDLE_TOO_LARGE"):
            safe_unzip([upload], tmp_path, max_total_mb=1)

    def test_nested_zip_rejected(self, tmp_path):
        from agent.aoc4.bundle import safe_unzip, BundleError
        from fastapi import UploadFile
        from io import BytesIO

        zip_data = BytesIO()
        with zipfile.ZipFile(zip_data, "w") as zf:
            zf.writestr("a/b/c/d/e/deep.txt", "too deep")

        zip_data.seek(0)
        upload = UploadFile(
            filename="deep.zip",
            file=zip_data,
        )

        with pytest.raises(BundleError, match="ZIP_TOO_DEEP"):
            safe_unzip([upload], tmp_path, max_zip_depth=1)


class TestClassifier:
    def test_xbrl_by_extension(self):
        from agent.aoc4.classifier import classify_document
        from agent.aoc4.models import DocumentInfo, DocType

        doc = DocumentInfo(doc_id="d01", filename="financials.xbrl", doc_type=DocType.OTHER, confidence=0)
        doc = classify_document(doc)
        assert doc.doc_type == DocType.XBRL
        assert doc.confidence >= 0.9

    def test_auditor_report_by_heading(self):
        from agent.aoc4.classifier import classify_document
        from agent.aoc4.models import DocumentInfo, DocType

        doc = DocumentInfo(doc_id="d02", filename="report.pdf", doc_type=DocType.OTHER, confidence=0)
        doc = classify_document(doc, "Independent Auditor's Report\nReport on the Audit of the Financial Statements")
        assert doc.doc_type == DocType.AUDITOR_REPORT

    def test_financial_statements_by_heading(self):
        from agent.aoc4.classifier import classify_document
        from agent.aoc4.models import DocumentInfo, DocType

        doc = DocumentInfo(doc_id="d03", filename="statements.pdf", doc_type=DocType.OTHER, confidence=0)
        doc = classify_document(doc, "Balance Sheet as at 31 March 2025\nStatement of Profit and Loss")
        assert doc.doc_type == DocType.FINANCIAL_STATEMENTS

    def test_basis_consolidated(self):
        from agent.aoc4.classifier import classify_document
        from agent.aoc4.models import DocumentInfo, DocType, Basis

        doc = DocumentInfo(doc_id="d01", filename="consolidated.pdf", doc_type=DocType.OTHER, confidence=0)
        doc = classify_document(doc, "Consolidated Financial Statements\nConsolidated Balance Sheet")
        assert doc.basis == Basis.CONSOLIDATED

    def test_unknown_document(self):
        from agent.aoc4.classifier import classify_document
        from agent.aoc4.models import DocumentInfo, DocType

        doc = DocumentInfo(doc_id="d01", filename="random.pdf", doc_type=DocType.OTHER, confidence=0)
        doc = classify_document(doc, "This is just random text with no headings")
        assert doc.doc_type == DocType.OTHER


class TestValidation:
    def test_v1_balance_check_pass(self):
        from agent.aoc4.validation import _v1_balance_check
        from agent.aoc4.models import PeriodStatements, Item

        period = PeriodStatements(
            period_end=date(2025, 3, 31),
            items={
                Item.TOTAL_ASSETS: Decimal("1000"),
                Item.TOTAL_EQUITY_AND_LIABILITIES: Decimal("1000"),
            },
        )
        issues = _v1_balance_check(period)
        assert len(issues) == 0

    def test_v1_balance_check_fail(self):
        from agent.aoc4.validation import _v1_balance_check
        from agent.aoc4.models import PeriodStatements, Item, IssueSeverity

        period = PeriodStatements(
            period_end=date(2025, 3, 31),
            items={
                Item.TOTAL_ASSETS: Decimal("1000"),
                Item.TOTAL_EQUITY_AND_LIABILITIES: Decimal("500"),
            },
        )
        issues = _v1_balance_check(period)
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.ERROR

    def test_v4_mixed_basis(self):
        from agent.aoc4.validation import run_validation
        from agent.aoc4.models import PeriodStatements, Basis, IssueSeverity

        periods = [
            PeriodStatements(period_end=date(2024, 3, 31), basis=Basis.STANDALONE),
            PeriodStatements(period_end=date(2025, 3, 31), basis=Basis.CONSOLIDATED),
        ]
        issues = run_validation(periods)
        v4 = [i for i in issues if i.code.startswith("V4")]
        assert len(v4) == 1
        assert v4[0].severity == IssueSeverity.ERROR

    def test_v8_insufficient_history(self):
        from agent.aoc4.validation import run_validation
        from agent.aoc4.models import PeriodStatements

        periods = [
            PeriodStatements(period_end=date(2025, 3, 31)),
        ]
        issues = run_validation(periods)
        v8 = [i for i in issues if i.code.startswith("V8")]
        assert len(v8) == 1

    def test_v8_sufficient_history(self):
        from agent.aoc4.validation import run_validation
        from agent.aoc4.models import PeriodStatements

        periods = [
            PeriodStatements(period_end=date(2023, 3, 31)),
            PeriodStatements(period_end=date(2024, 3, 31)),
            PeriodStatements(period_end=date(2025, 3, 31)),
        ]
        issues = run_validation(periods)
        v8 = [i for i in issues if i.code.startswith("V8")]
        assert len(v8) == 0

    def test_v11_stale(self):
        from agent.aoc4.validation import run_validation
        from agent.aoc4.models import PeriodStatements

        period = PeriodStatements(period_end=date(2022, 3, 31))
        issues = run_validation([period])
        v11 = [i for i in issues if i.code.startswith("V11")]
        # Should be stale if more than 456 days ago
        from datetime import date as today_date
        days = (today_date.today() - date(2022, 3, 31)).days
        if days > 456:
            assert len(v11) == 1

    def test_empty_periods(self):
        from agent.aoc4.validation import run_validation
        issues = run_validation([])
        assert issues == []


class TestLabelMap:
    def test_exact_match(self):
        from agent.aoc4.label_map import match_label, Item
        result = match_label("Revenue from operations")
        assert result == Item.REVENUE_FROM_OPERATIONS

    def test_fuzzy_match(self):
        from agent.aoc4.label_map import match_label, Item
        result = match_label("Equity Share Capital")
        assert result == Item.EQUITY_SHARE_CAPITAL

    def test_unknown_label(self):
        from agent.aoc4.label_map import match_label
        result = match_label("Some completely unknown line item xyz")
        assert result is None


class TestXBRLReader:
    def test_concept_map_populated(self):
        from agent.aoc4.xbrl_reader import _CONCEPT_MAP
        assert len(_CONCEPT_MAP) > 0
        # Check key concepts exist
        assert "RevenueFromOperations" in _CONCEPT_MAP
        assert "TotalAssets" in _CONCEPT_MAP
        assert "ProfitBeforeTax" in _CONCEPT_MAP
