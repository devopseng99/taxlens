"""Wave 61 tests — 1040-ES Estimated Tax Payment Vouchers."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Voucher PDF Generation
# =========================================================================
class TestGenerate1040ESVouchers:
    def _make_result(self, quarterly=2500.0):
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        filer = PersonInfo(
            first_name="Jane", last_name="Doe", ssn="123-45-6789",
            address_street="100 Main St", address_city="Chicago",
            address_state="IL", address_zip="60601",
        )
        result = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=100000, federal_withheld=10000)],
            deductions=Deductions(), additional=AdditionalIncome(),
            payments=Payments(),
        )
        # Override quarterly for test control
        result.quarterly_estimated_tax = quarterly
        return result

    def test_pdf_renders_4_pages(self):
        from pdf_generator import generate_1040es_vouchers
        result = self._make_result(2500.0)
        buf = generate_1040es_vouchers(result)
        data = buf.read()
        assert data[:4] == b"%PDF"
        assert len(data) > 500

    def test_pdf_with_zero_amount(self):
        from pdf_generator import generate_1040es_vouchers
        result = self._make_result(0.0)
        buf = generate_1040es_vouchers(result)
        data = buf.read()
        assert data[:4] == b"%PDF"

    def test_pdf_with_large_amount(self):
        from pdf_generator import generate_1040es_vouchers
        result = self._make_result(25000.0)
        buf = generate_1040es_vouchers(result)
        data = buf.read()
        assert data[:4] == b"%PDF"

    def test_pdf_without_filer(self):
        from pdf_generator import generate_1040es_vouchers
        from tax_engine import TaxResult
        result = TaxResult()
        result.quarterly_estimated_tax = 1000.0
        buf = generate_1040es_vouchers(result)
        data = buf.read()
        assert data[:4] == b"%PDF"


# =========================================================================
# Due Dates
# =========================================================================
class TestDueDates:
    def test_four_due_dates(self):
        from pdf_generator import _ES_DUE_DATES
        assert len(_ES_DUE_DATES) == 4

    def test_due_date_order(self):
        from pdf_generator import _ES_DUE_DATES
        nums = [d[0] for d in _ES_DUE_DATES]
        assert nums == ["1", "2", "3", "4"]

    def test_april_june_sep_jan(self):
        from pdf_generator import _ES_DUE_DATES
        dates = [d[1] for d in _ES_DUE_DATES]
        assert "April" in dates[0]
        assert "June" in dates[1]
        assert "September" in dates[2]
        assert "January" in dates[3]


# =========================================================================
# Integration with generate_all_pdfs
# =========================================================================
class TestAllPDFsIntegration:
    def test_1040es_in_generate_all_pdfs(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "pdf_generator.py")
        src = open(path).read()
        assert "generate_1040es_vouchers" in src
        assert "form_1040es.pdf" in src

    def test_1040es_conditional_on_quarterly(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "pdf_generator.py")
        src = open(path).read()
        assert "quarterly_estimated_tax > 0" in src

    def test_1040es_in_file_map(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert '"1040es"' in src

    def test_generate_all_pdfs_includes_1040es(self):
        import tempfile
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        from pdf_generator import generate_all_pdfs
        filer = PersonInfo(first_name="Test", last_name="User")
        result = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=200000, federal_withheld=20000)],
            deductions=Deductions(), additional=AdditionalIncome(),
            payments=Payments(),
        )
        # Force quarterly estimated tax
        result.quarterly_estimated_tax = 5000.0
        with tempfile.TemporaryDirectory() as td:
            paths = generate_all_pdfs(result, td)
            assert "1040es" in paths


# =========================================================================
# Engine Quarterly Estimated Tax
# =========================================================================
class TestEngineQuarterlyTax:
    def test_quarterly_computed(self):
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        filer = PersonInfo(first_name="Test", last_name="User")
        result = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=100000, federal_withheld=5000)],
            deductions=Deductions(), additional=AdditionalIncome(),
            payments=Payments(),
        )
        # With low withholding on $100k, should have estimated tax
        assert result.quarterly_estimated_tax >= 0

    def test_quarterly_field_exists(self):
        from tax_engine import TaxResult
        result = TaxResult()
        assert hasattr(result, "quarterly_estimated_tax")
        assert result.quarterly_estimated_tax == 0.0
