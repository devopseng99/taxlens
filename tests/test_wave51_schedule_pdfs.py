"""Wave 51 tests — Schedule 1/3/E PDF generation."""

import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    BusinessIncome, RentalProperty, EducationExpense, ForeignTaxCredit,
    HSAContribution, EnergyImprovement, GamblingIncome, IRAContribution,
    compute_tax,
)
from pdf_generator import (
    generate_schedule_1, generate_schedule_3, generate_schedule_e,
    generate_all_pdfs,
)

FILER = PersonInfo(first_name="Test", last_name="User")


def _basic_result(**kwargs):
    defaults = dict(
        filing_status="single", filer=FILER,
        w2s=[W2Income(wages=80_000, federal_withheld=12_000)],
        additional=AdditionalIncome(), deductions=Deductions(),
        payments=Payments(),
    )
    defaults.update(kwargs)
    return compute_tax(**defaults)


# =========================================================================
# Schedule 1 — Additional Income and Adjustments
# =========================================================================
class TestSchedule1:
    def test_generated_when_business_income(self):
        r = _basic_result(businesses=[BusinessIncome(gross_receipts=50_000)])
        assert "Schedule 1" in r.forms_generated

    def test_generated_when_hsa_deduction(self):
        r = _basic_result(hsa_contributions=[HSAContribution(contribution_amount=3000, coverage_type="self")])
        assert "Schedule 1" in r.forms_generated

    def test_generated_when_student_loan(self):
        r = _basic_result(deductions=Deductions(student_loan_interest=2500))
        assert "Schedule 1" in r.forms_generated

    def test_generated_when_gambling(self):
        r = _basic_result(gambling_income=[GamblingIncome(winnings=5000)])
        assert "Schedule 1" in r.forms_generated

    def test_not_generated_for_simple_w2(self):
        r = _basic_result()
        assert "Schedule 1" not in r.forms_generated

    def test_pdf_renders(self):
        r = _basic_result(
            businesses=[BusinessIncome(gross_receipts=50_000)],
            hsa_contributions=[HSAContribution(contribution_amount=3000, coverage_type="self")],
        )
        buf = generate_schedule_1(r)
        data = buf.read()
        assert len(data) > 100
        assert data[:4] == b"%PDF"

    def test_in_generate_all_pdfs(self):
        r = _basic_result(businesses=[BusinessIncome(gross_receipts=50_000)])
        with tempfile.TemporaryDirectory() as td:
            paths = generate_all_pdfs(r, td)
            assert "schedule_1" in paths
            assert os.path.exists(paths["schedule_1"])


# =========================================================================
# Schedule 3 — Additional Credits and Payments
# =========================================================================
class TestSchedule3:
    def test_generated_when_education_credit(self):
        r = _basic_result(education_expenses=[
            EducationExpense(student_name="Kid", qualified_expenses=4000, credit_type="aotc")
        ])
        assert "Schedule 3" in r.forms_generated

    def test_generated_when_foreign_tax_credit(self):
        r = _basic_result(foreign_tax_credits=[
            ForeignTaxCredit(country="UK", foreign_source_income=10000, foreign_tax_paid=1500)
        ])
        assert "Schedule 3" in r.forms_generated

    def test_generated_when_energy_credit(self):
        r = _basic_result(energy_improvements=[
            EnergyImprovement(solar_electric=20000)
        ])
        assert "Schedule 3" in r.forms_generated

    def test_not_generated_when_no_credits(self):
        r = _basic_result()
        assert "Schedule 3" not in r.forms_generated

    def test_pdf_renders(self):
        r = _basic_result(education_expenses=[
            EducationExpense(student_name="Kid", qualified_expenses=4000, credit_type="aotc")
        ])
        buf = generate_schedule_3(r)
        data = buf.read()
        assert len(data) > 100
        assert data[:4] == b"%PDF"

    def test_in_generate_all_pdfs(self):
        r = _basic_result(foreign_tax_credits=[
            ForeignTaxCredit(country="UK", foreign_source_income=10000, foreign_tax_paid=1500)
        ])
        with tempfile.TemporaryDirectory() as td:
            paths = generate_all_pdfs(r, td)
            assert "schedule_3" in paths


# =========================================================================
# Schedule E — Rental Real Estate
# =========================================================================
class TestScheduleE:
    def test_generated_when_rental_property(self):
        r = _basic_result(rental_properties=[
            RentalProperty(property_address="Apt 1A", gross_rents=24000,
                           mortgage_interest=6000, taxes=3000, insurance=1200)
        ])
        assert "Schedule E" in r.forms_generated

    def test_not_generated_without_rental(self):
        r = _basic_result()
        assert "Schedule E" not in r.forms_generated

    def test_pdf_renders(self):
        r = _basic_result(rental_properties=[
            RentalProperty(property_address="Apt 1A", gross_rents=24000,
                           mortgage_interest=6000, taxes=3000)
        ])
        buf = generate_schedule_e(r)
        data = buf.read()
        assert len(data) > 100
        assert data[:4] == b"%PDF"

    def test_in_generate_all_pdfs(self):
        r = _basic_result(rental_properties=[
            RentalProperty(property_address="Apt 1A", gross_rents=24000,
                           mortgage_interest=6000, taxes=3000)
        ])
        with tempfile.TemporaryDirectory() as td:
            paths = generate_all_pdfs(r, td)
            assert "schedule_e" in paths
            assert os.path.exists(paths["schedule_e"])

    def test_multiple_properties(self):
        r = _basic_result(rental_properties=[
            RentalProperty(property_address="Apt 1A", gross_rents=24000, mortgage_interest=6000),
            RentalProperty(property_address="House B", gross_rents=36000, insurance=2400),
        ])
        buf = generate_schedule_e(r)
        data = buf.read()
        assert len(data) > 100


# =========================================================================
# Backward Compatibility
# =========================================================================
class TestBackwardCompat:
    def test_simple_w2_no_new_schedules(self):
        """Simple W-2 return should not generate Schedule 1, 3, or E."""
        r = _basic_result()
        assert "Schedule 1" not in r.forms_generated
        assert "Schedule 3" not in r.forms_generated
        assert "Schedule E" not in r.forms_generated

    def test_existing_forms_still_generated(self):
        """Business income still generates Schedule C, SE, and now also Schedule 1."""
        r = _basic_result(businesses=[BusinessIncome(gross_receipts=50_000)])
        assert "Schedule C" in r.forms_generated
        assert "Schedule SE" in r.forms_generated
        assert "Schedule 1" in r.forms_generated
