"""Wave 67 tests — Amended Return / Form 1040-X."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Amended Return Computation
# =========================================================================
class TestAmendedComputation:
    def _make_results(self):
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        filer = PersonInfo(first_name="Test", last_name="User")
        # Original: forgot a W-2
        original = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=80000, federal_withheld=12000)],
            deductions=Deductions(), additional=AdditionalIncome(),
            payments=Payments(),
        )
        # Amended: added missing W-2 income
        amended = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=80000, federal_withheld=12000),
                 W2Income(wages=15000, federal_withheld=2000)],
            deductions=Deductions(), additional=AdditionalIncome(),
            payments=Payments(),
        )
        return original, amended

    def test_basic_amended(self):
        from amended_return import compute_amended_return
        orig, amend = self._make_results()
        result = compute_amended_return(orig, amend)
        assert len(result.lines) > 10
        assert result.tax_year == 2025

    def test_tax_increase_with_added_w2(self):
        from amended_return import compute_amended_return
        orig, amend = self._make_results()
        result = compute_amended_return(orig, amend)
        # Adding missing W-2 increases tax
        assert result.total_tax_change > 0

    def test_columns_abc(self):
        from amended_return import compute_amended_return
        orig, amend = self._make_results()
        result = compute_amended_return(orig, amend)
        for line in result.lines:
            # C should equal A + B
            assert abs(line.column_c - (line.column_a + line.column_b)) < 0.02

    def test_auto_explanation(self):
        from amended_return import compute_amended_return
        orig, amend = self._make_results()
        result = compute_amended_return(orig, amend)
        assert len(result.explanation) > 0

    def test_custom_explanation(self):
        from amended_return import compute_amended_return
        orig, amend = self._make_results()
        result = compute_amended_return(orig, amend, explanation="Found missing W-2")
        assert result.explanation == "Found missing W-2"

    def test_no_change(self):
        from amended_return import compute_amended_return
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        filer = PersonInfo(first_name="Test", last_name="User")
        r = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=50000, federal_withheld=7000)],
            deductions=Deductions(), additional=AdditionalIncome(), payments=Payments(),
        )
        result = compute_amended_return(r, r)
        assert result.total_tax_change == 0
        assert result.refund_change == 0

    def test_draft_ids_preserved(self):
        from amended_return import compute_amended_return
        orig, amend = self._make_results()
        result = compute_amended_return(
            orig, amend,
            original_draft_id="draft-001",
            amended_draft_id="draft-002",
        )
        assert result.original_draft_id == "draft-001"
        assert result.amended_draft_id == "draft-002"


# =========================================================================
# 1040-X PDF Generation
# =========================================================================
class TestPdfGeneration:
    def test_pdf_renders(self):
        from amended_return import compute_amended_return
        from pdf_generator import generate_1040x
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        filer = PersonInfo(first_name="Test", last_name="User")
        orig = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=80000, federal_withheld=12000)],
            deductions=Deductions(), additional=AdditionalIncome(), payments=Payments(),
        )
        amend = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=85000, federal_withheld=12000)],
            deductions=Deductions(), additional=AdditionalIncome(), payments=Payments(),
        )
        amended = compute_amended_return(orig, amend)
        buf = generate_1040x(amended)
        data = buf.read()
        assert data[:4] == b"%PDF"
        assert len(data) > 500


# =========================================================================
# Endpoint Integration
# =========================================================================
class TestEndpoint:
    def test_amend_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "amend/" in src
        assert "async def create_amended_return" in src

    def test_1040x_in_file_map(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert '"1040x"' in src

    def test_amended_return_module(self):
        from amended_return import compute_amended_return, AmendedReturn
        assert callable(compute_amended_return)

    def test_pdf_generator_has_1040x(self):
        from pdf_generator import generate_1040x
        assert callable(generate_1040x)
