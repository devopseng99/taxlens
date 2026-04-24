"""Wave 52 tests — Form 8606 Nondeductible IRA Basis Tracking."""

import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    IRAContribution, RetirementDistribution,
    compute_tax,
)
from pdf_generator import generate_form_8606, generate_all_pdfs

FILER = PersonInfo(first_name="Test", last_name="User")


def _compute(**kwargs):
    defaults = dict(
        filing_status="single", filer=FILER,
        w2s=[W2Income(wages=120_000, federal_withheld=20_000)],
        additional=AdditionalIncome(), deductions=Deductions(),
        payments=Payments(),
    )
    defaults.update(kwargs)
    return compute_tax(**defaults)


# =========================================================================
# Part I — Nondeductible contributions (phaseout creates nondeductible)
# =========================================================================
class TestNondeductibleContributions:
    def test_full_deduction_no_8606(self):
        """No active plan → full IRA deduction, no Form 8606 needed."""
        r = _compute(
            ira_contributions=[IRAContribution(contribution_amount=7000)],
        )
        assert r.form_8606_nondeductible_contribution == 0
        assert "Form 8606" not in r.forms_generated

    def test_phaseout_creates_nondeductible(self):
        """Active plan + high income → partial deduction → nondeductible remainder."""
        r = _compute(
            w2s=[W2Income(wages=85_000, federal_withheld=15_000)],
            ira_contributions=[IRAContribution(contribution_amount=7000)],
            filer_active_plan_participant=True,
        )
        assert r.ira_phaseout_applied
        assert r.form_8606_nondeductible_contribution > 0
        assert r.form_8606_nondeductible_contribution == 7000 - r.ira_deduction
        assert "Form 8606" in r.forms_generated

    def test_full_phaseout_all_nondeductible(self):
        """Income above phaseout → $0 deduction → entire contribution is nondeductible."""
        r = _compute(
            w2s=[W2Income(wages=150_000, federal_withheld=25_000)],
            ira_contributions=[IRAContribution(contribution_amount=7000)],
            filer_active_plan_participant=True,
        )
        assert r.ira_deduction == 0
        assert r.form_8606_nondeductible_contribution == 7000

    def test_no_contribution_but_prior_basis(self):
        """No new contribution but prior-year basis → Form 8606 still generated."""
        r = _compute(prior_year_ira_basis=15_000)
        assert r.form_8606_prior_year_basis == 15_000
        assert r.form_8606_total_basis == 15_000
        assert "Form 8606" in r.forms_generated


# =========================================================================
# Pro-rata rule — taxable portion of distributions
# =========================================================================
class TestProRataRule:
    def test_pro_rata_with_distributions(self):
        """Basis reduces taxable portion of distributions via pro-rata rule."""
        r = _compute(
            w2s=[W2Income(wages=150_000, federal_withheld=25_000)],
            ira_contributions=[IRAContribution(contribution_amount=7000)],
            filer_active_plan_participant=True,
            retirement_distributions=[
                RetirementDistribution(gross_distribution=10_000, taxable_amount=10_000, is_ira=True)
            ],
            prior_year_ira_basis=20_000,
            total_ira_value_year_end=200_000,
        )
        # Basis = 7000 (nondeductible) + 20000 (prior) = 27000
        # Total value = 200000 (year-end) + 10000 (distributions) = 210000
        # Nontaxable % = 27000 / 210000 ≈ 12.86%
        assert r.form_8606_total_basis == 27_000
        assert 0.10 < r.form_8606_nontaxable_pct < 0.15
        assert r.form_8606_nontaxable_amount > 0
        # Taxable should be less than gross distribution
        assert r.line_4b_ira_taxable < 10_000

    def test_no_distributions_basis_carries_forward(self):
        """Without distributions, entire basis carries forward."""
        r = _compute(
            w2s=[W2Income(wages=150_000, federal_withheld=25_000)],
            ira_contributions=[IRAContribution(contribution_amount=7000)],
            filer_active_plan_participant=True,
            prior_year_ira_basis=20_000,
        )
        assert r.form_8606_remaining_basis == 27_000  # 7000 + 20000

    def test_pro_rata_100pct_basis(self):
        """If basis equals total IRA value, distributions are fully nontaxable."""
        r = _compute(
            prior_year_ira_basis=50_000,
            retirement_distributions=[
                RetirementDistribution(gross_distribution=10_000, taxable_amount=10_000, is_ira=True)
            ],
            total_ira_value_year_end=40_000,
        )
        # Total value = 40000 + 10000 = 50000, basis = 50000 → 100%
        assert r.form_8606_nontaxable_pct == 1.0
        assert r.line_4b_ira_taxable == 0

    def test_remaining_basis_after_distribution(self):
        """Basis is reduced by nontaxable portion of distributions."""
        r = _compute(
            prior_year_ira_basis=50_000,
            retirement_distributions=[
                RetirementDistribution(gross_distribution=20_000, taxable_amount=20_000, is_ira=True)
            ],
            total_ira_value_year_end=80_000,
        )
        # Total value = 80000 + 20000 = 100000, basis = 50000 → 50%
        # Nontaxable = 20000 × 50% = 10000
        # Remaining basis = 50000 - 10000 = 40000
        assert r.form_8606_nontaxable_pct == 0.5
        assert r.form_8606_nontaxable_amount == 10_000
        assert r.line_4b_ira_taxable == 10_000
        assert r.form_8606_remaining_basis == 40_000


# =========================================================================
# Part III — Roth conversions
# =========================================================================
class TestRothConversion:
    def test_roth_conversion_with_basis(self):
        """Roth conversion uses pro-rata rule — basis portion is nontaxable."""
        r = _compute(
            prior_year_ira_basis=30_000,
            total_ira_value_year_end=70_000,
            roth_conversion_amount=20_000,
        )
        # Total value = 70000 + 20000 = 90000, basis = 30000 → 33.33%
        # Roth nontaxable = 20000 × 33.33% ≈ 6667
        assert r.form_8606_roth_conversion == 20_000
        assert r.form_8606_roth_taxable > 0
        assert r.form_8606_roth_taxable < 20_000
        # Conversion adds to line 4a and taxable to 4b
        assert r.line_4a_ira_distributions >= 20_000

    def test_roth_conversion_no_basis(self):
        """Without basis, entire Roth conversion is taxable."""
        r = _compute(
            total_ira_value_year_end=100_000,
            roth_conversion_amount=20_000,
        )
        # No basis → no Form 8606 triggered (no nondeductible + no prior basis)
        assert r.form_8606_nondeductible_contribution == 0
        assert r.form_8606_prior_year_basis == 0

    def test_backdoor_roth_pattern(self):
        """Classic backdoor Roth: nondeductible contribution + immediate conversion."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=35_000)],
            ira_contributions=[IRAContribution(contribution_amount=7000)],
            filer_active_plan_participant=True,
            total_ira_value_year_end=0,  # Converted everything, IRA is now empty
            roth_conversion_amount=7000,
        )
        # Full phaseout → $7000 nondeductible, basis = $7000
        # Total value = 0 + 7000 (conversion) = 7000
        # Nontaxable % = 7000 / 7000 = 100%
        assert r.form_8606_nondeductible_contribution == 7000
        assert r.form_8606_nontaxable_pct == 1.0
        assert r.form_8606_roth_taxable == 0  # No tax on backdoor Roth!


# =========================================================================
# Summary & PDF
# =========================================================================
class TestSummaryAndPDF:
    def test_form_8606_in_summary(self):
        """Form 8606 data appears in summary when applicable."""
        r = _compute(prior_year_ira_basis=10_000)
        s = r.to_summary()
        assert s["form_8606"] is not None
        assert s["form_8606"]["prior_year_basis"] == 10_000

    def test_form_8606_absent_when_no_basis(self):
        """No Form 8606 in summary for simple returns."""
        r = _compute()
        s = r.to_summary()
        assert s.get("form_8606") is None

    def test_pdf_renders(self):
        r = _compute(
            prior_year_ira_basis=20_000,
            retirement_distributions=[
                RetirementDistribution(gross_distribution=10_000, taxable_amount=10_000, is_ira=True)
            ],
            total_ira_value_year_end=100_000,
        )
        buf = generate_form_8606(r)
        data = buf.read()
        assert len(data) > 100
        assert data[:4] == b"%PDF"

    def test_pdf_in_generate_all(self):
        r = _compute(prior_year_ira_basis=20_000)
        with tempfile.TemporaryDirectory() as td:
            paths = generate_all_pdfs(r, td)
            assert "form_8606" in paths


# =========================================================================
# Backward Compatibility
# =========================================================================
class TestBackwardCompat:
    def test_no_new_params_no_change(self):
        """Without new params, no Form 8606 generated."""
        r = _compute()
        assert r.form_8606_nondeductible_contribution == 0
        assert r.form_8606_remaining_basis == 0
        assert "Form 8606" not in r.forms_generated
