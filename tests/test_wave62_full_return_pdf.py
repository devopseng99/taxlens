"""Wave 62 tests — Full Return PDF Package with cover page + bookmarks."""

import sys, os, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Cover Page Generation
# =========================================================================
class TestCoverPage:
    def _make_result(self):
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        filer = PersonInfo(
            first_name="Jane", last_name="Doe", ssn="123-45-6789",
            address_street="100 Main St", address_city="Chicago",
            address_state="IL", address_zip="60601",
        )
        return compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=80000, federal_withheld=12000)],
            deductions=Deductions(), additional=AdditionalIncome(),
            payments=Payments(),
        )

    def test_cover_page_renders(self):
        from pdf_generator import _generate_cover_page
        result = self._make_result()
        form_list = [("Form 1040", 2), ("Schedule A", 4)]
        buf = _generate_cover_page(result, form_list)
        data = buf.read()
        assert data[:4] == b"%PDF"
        assert len(data) > 200

    def test_cover_page_without_filer(self):
        from pdf_generator import _generate_cover_page
        from tax_engine import TaxResult
        result = TaxResult()
        buf = _generate_cover_page(result, [])
        assert buf.read()[:4] == b"%PDF"


# =========================================================================
# Full Return Merge
# =========================================================================
class TestFullReturnPDF:
    def _generate_forms(self):
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        from pdf_generator import generate_all_pdfs
        filer = PersonInfo(first_name="Test", last_name="User")
        result = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=100000, federal_withheld=15000)],
            deductions=Deductions(), additional=AdditionalIncome(),
            payments=Payments(),
        )
        td = tempfile.mkdtemp()
        paths = generate_all_pdfs(result, td)
        return result, td, paths

    def test_full_return_pdf_renders(self):
        from pdf_generator import generate_full_return_pdf
        result, td, paths = self._generate_forms()
        buf = generate_full_return_pdf(result, td)
        data = buf.read()
        assert data[:4] == b"%PDF"
        assert len(data) > 1000

    def test_full_return_has_more_pages_than_individual(self):
        import pypdf
        from pdf_generator import generate_full_return_pdf
        result, td, paths = self._generate_forms()
        buf = generate_full_return_pdf(result, td)
        reader = pypdf.PdfReader(buf)
        # Should have cover page + at least 1040 + summary = 3+ pages
        assert len(reader.pages) >= 3

    def test_full_return_has_bookmarks(self):
        import pypdf
        from pdf_generator import generate_full_return_pdf
        result, td, paths = self._generate_forms()
        buf = generate_full_return_pdf(result, td)
        reader = pypdf.PdfReader(buf)
        outlines = reader.outline
        assert len(outlines) >= 2  # At least summary + 1040

    def test_full_return_empty_dir(self):
        from pdf_generator import generate_full_return_pdf
        from tax_engine import TaxResult
        result = TaxResult()
        td = tempfile.mkdtemp()
        buf = generate_full_return_pdf(result, td)
        data = buf.read()
        # Should still produce a valid PDF (just cover page)
        assert data[:4] == b"%PDF"


# =========================================================================
# Form Order
# =========================================================================
class TestFormOrder:
    def test_form_order_exists(self):
        from pdf_generator import _FORM_ORDER
        assert len(_FORM_ORDER) > 20

    def test_1040_before_schedules(self):
        from pdf_generator import _FORM_ORDER
        keys = [k for k, _ in _FORM_ORDER]
        assert keys.index("1040") < keys.index("schedule_a")
        assert keys.index("1040") < keys.index("schedule_b")

    def test_summary_first(self):
        from pdf_generator import _FORM_ORDER
        assert _FORM_ORDER[0][0] == "summary"


# =========================================================================
# Endpoint Integration
# =========================================================================
class TestEndpointIntegration:
    def test_full_return_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "full_return" in src
        assert "generate_full_return_pdf" in src

    def test_full_return_route_path(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "pdf/full_return" in src

    def test_pdf_generator_has_full_return(self):
        from pdf_generator import generate_full_return_pdf
        assert callable(generate_full_return_pdf)
