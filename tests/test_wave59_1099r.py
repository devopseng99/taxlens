"""Wave 59 tests — 1099-R OCR Parser + PDF Generation."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# 1099-R OCR Parser
# =========================================================================
class TestParse1099R:
    def test_basic_distribution(self):
        from tax_engine import parse_1099r_from_ocr
        fields = {
            "Payer": {"value": {"Name": {"value": "Fidelity Investments"}}},
            "Box1": {"value": "50000.00"},
            "Box2a": {"value": "50000.00"},
            "Box4": {"value": "10000.00"},
            "Box7": {"value": "7"},
        }
        dist = parse_1099r_from_ocr(fields)
        assert dist.payer_name == "Fidelity Investments"
        assert dist.gross_distribution == 50000.0
        assert dist.taxable_amount == 50000.0
        assert dist.federal_withheld == 10000.0
        assert dist.distribution_code == "7"
        assert dist.is_early is False
        assert dist.is_roth is False

    def test_early_distribution(self):
        from tax_engine import parse_1099r_from_ocr
        fields = {
            "Payer": {"value": "My 401k"},
            "Box1": {"value": "25000"},
            "Box2a": {"value": "25000"},
            "Box4": {"value": "5000"},
            "Box7": {"value": "1"},
        }
        dist = parse_1099r_from_ocr(fields)
        assert dist.distribution_code == "1"
        assert dist.is_early is True

    def test_rollover(self):
        from tax_engine import parse_1099r_from_ocr
        fields = {
            "Payer": {"value": "Vanguard"},
            "Box1": {"value": "100000"},
            "Box2a": {"value": "0"},
            "Box7": {"value": "G"},
        }
        dist = parse_1099r_from_ocr(fields)
        assert dist.distribution_code == "G"
        assert dist.taxable == 0.0

    def test_roth_distribution(self):
        from tax_engine import parse_1099r_from_ocr
        fields = {
            "Payer": {"value": "Schwab"},
            "Box1": {"value": "30000"},
            "Box2a": {"value": "0"},
            "Box7": {"value": "Q"},
            "Roth": {"value": "true"},
        }
        dist = parse_1099r_from_ocr(fields)
        assert dist.is_roth is True
        assert dist.taxable == 0.0

    def test_ira_flag(self):
        from tax_engine import parse_1099r_from_ocr
        fields = {
            "Box1": {"value": "10000"},
            "Box7": {"value": "7"},
            "IRAOrSEPOrSIMPLE": {"value": "X"},
        }
        dist = parse_1099r_from_ocr(fields)
        assert dist.is_ira is True

    def test_taxable_not_determined(self):
        from tax_engine import parse_1099r_from_ocr
        fields = {
            "Box1": {"value": "20000"},
            "Box2a": {"value": "0"},
            "Box2b": {"value": "true"},
            "Box7": {"value": "7"},
        }
        dist = parse_1099r_from_ocr(fields)
        assert dist.taxable_amount_not_determined is True
        # When not determined, taxable == gross
        assert dist.taxable == 20000.0

    def test_empty_fields_defaults(self):
        from tax_engine import parse_1099r_from_ocr
        dist = parse_1099r_from_ocr({})
        assert dist.gross_distribution == 0.0
        assert dist.distribution_code == "7"
        assert dist.payer_name == "1099-R Distribution"

    def test_payer_string_format(self):
        from tax_engine import parse_1099r_from_ocr
        fields = {"Payer": {"value": "Simple Payer LLC"}}
        dist = parse_1099r_from_ocr(fields)
        assert dist.payer_name == "Simple Payer LLC"


# =========================================================================
# 1099-R PDF Generation
# =========================================================================
class TestGenerate1099R:
    def test_pdf_renders(self):
        from tax_engine import RetirementDistribution
        from pdf_generator import generate_1099r
        dist = RetirementDistribution(
            payer_name="Fidelity",
            gross_distribution=50000,
            taxable_amount=50000,
            federal_withheld=10000,
            distribution_code="7",
        )
        buf = generate_1099r(dist)
        data = buf.read()
        assert len(data) > 100
        assert data[:4] == b"%PDF"

    def test_pdf_with_roth(self):
        from tax_engine import RetirementDistribution
        from pdf_generator import generate_1099r
        dist = RetirementDistribution(
            payer_name="Vanguard",
            gross_distribution=30000,
            is_roth=True,
            distribution_code="Q",
        )
        buf = generate_1099r(dist)
        data = buf.read()
        assert data[:4] == b"%PDF"

    def test_pdf_with_early_distribution(self):
        from tax_engine import RetirementDistribution
        from pdf_generator import generate_1099r
        dist = RetirementDistribution(
            payer_name="401k Provider",
            gross_distribution=25000,
            taxable_amount=25000,
            is_early=True,
            distribution_code="1",
        )
        buf = generate_1099r(dist)
        assert buf.read()[:4] == b"%PDF"


# =========================================================================
# Tax Routes Integration
# =========================================================================
class TestTaxRoutesIntegration:
    def test_1099r_proc_ids_field_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "retirement_1099r_proc_ids" in src

    def test_parse_1099r_imported(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "parse_1099r_from_ocr" in src

    def test_1099r_in_file_map(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert '"1099r"' in src

    def test_engine_imports_include_1099r_parser(self):
        from tax_engine import parse_1099r_from_ocr
        assert callable(parse_1099r_from_ocr)

    def test_pdf_generator_has_1099r(self):
        from pdf_generator import generate_1099r
        assert callable(generate_1099r)


# =========================================================================
# Full Engine Integration
# =========================================================================
class TestEngineIntegration:
    def test_1099r_through_engine(self):
        from tax_engine import (
            PersonInfo, W2Income, Deductions, AdditionalIncome,
            Payments, RetirementDistribution, compute_tax,
        )
        filer = PersonInfo(first_name="Test", last_name="User")
        result = compute_tax(
            filing_status="single", filer=filer,
            w2s=[W2Income(wages=50000, federal_withheld=5000)],
            deductions=Deductions(),
            additional=AdditionalIncome(),
            payments=Payments(),
            retirement_distributions=[
                RetirementDistribution(
                    payer_name="Fidelity",
                    gross_distribution=30000,
                    taxable_amount=30000,
                    federal_withheld=6000,
                    distribution_code="7",
                    is_ira=True,
                ),
            ],
        )
        # Retirement income should be in the computation
        assert result.retirement_distributions_count == 1
        # Total income should include the distribution
        assert result.line_9_total_income > 50000
