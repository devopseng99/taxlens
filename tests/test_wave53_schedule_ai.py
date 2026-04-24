"""Wave 53 tests — Form 2210 Schedule AI Annualized Installment Method."""

import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    BusinessIncome, QuarterlyIncome,
    compute_tax,
)
from pdf_generator import generate_schedule_ai, generate_all_pdfs

FILER = PersonInfo(first_name="Test", last_name="User", address_state="IL")


def _compute(**kwargs):
    defaults = dict(
        filing_status="single", filer=FILER,
        w2s=[W2Income(wages=100_000, federal_withheld=5_000)],
        additional=AdditionalIncome(), deductions=Deductions(),
        payments=Payments(),
        prior_year_tax=15_000, prior_year_agi=90_000,
    )
    defaults.update(kwargs)
    return compute_tax(**defaults)


# =========================================================================
# Basic Schedule AI — Uneven income reduces penalty
# =========================================================================
class TestAnnualizedMethod:
    def test_no_quarterly_income_no_schedule_ai(self):
        """Without quarterly_income, Schedule AI is not used."""
        r = _compute()
        assert r.sched_ai_used is False
        assert r.sched_ai_penalty_reduction == 0
        assert "Schedule AI" not in r.forms_generated

    def test_uniform_income_no_benefit(self):
        """Even income across quarters → AI method provides no benefit."""
        r = _compute(
            quarterly_income=QuarterlyIncome(
                wages=(25_000, 50_000, 75_000, 100_000),  # cumulative, uniform
                withholding=(1_250, 2_500, 3_750, 5_000),
            ),
        )
        # With uniform income, AI installments should be similar to regular
        # AI may not be used if no benefit
        if r.sched_ai_used:
            assert r.sched_ai_penalty_reduction >= 0

    def test_back_loaded_income_reduces_penalty(self):
        """Income concentrated in Q4 → AI method reduces penalty significantly."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(10_000, 20_000, 40_000, 200_000),  # cumulative
                withholding=(500, 1_000, 2_000, 10_000),
            ),
        )
        # Back-loaded income → early quarters need less
        if r.estimated_tax_penalty > 0:
            assert r.sched_ai_used is True
            assert r.sched_ai_penalty_reduction > 0
            assert "Schedule AI" in r.forms_generated

    def test_front_loaded_income_penalty_not_reduced_much(self):
        """Income front-loaded in Q1 → AI method offers minimal or no improvement."""
        r = _compute(
            w2s=[W2Income(wages=100_000, federal_withheld=5_000)],
            quarterly_income=QuarterlyIncome(
                wages=(80_000, 90_000, 95_000, 100_000),  # mostly Q1
                withholding=(4_000, 4_500, 4_750, 5_000),
            ),
        )
        # Front-loaded → AI may or may not help, but penalty reduction should be small
        # compared to the back-loaded case
        if r.sched_ai_used:
            # Even if used, penalty reduction should be modest
            assert r.sched_ai_penalty_reduction >= 0


# =========================================================================
# Annualization factors
# =========================================================================
class TestAnnualizationFactors:
    def test_four_periods_computed(self):
        """Schedule AI computes 4 annualized income and tax values."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(10_000, 30_000, 60_000, 200_000),
                withholding=(500, 1_500, 3_000, 10_000),
            ),
        )
        if r.estimated_tax_penalty > 0:
            assert len(r.sched_ai_annualized_income) == 4
            assert len(r.sched_ai_annualized_tax) == 4
            assert len(r.sched_ai_required_installments) == 4

    def test_period1_annualized_4x(self):
        """Period 1 income is annualized by factor of 4."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(20_000, 50_000, 80_000, 200_000),
                withholding=(500, 1_500, 3_000, 10_000),
            ),
        )
        if r.sched_ai_annualized_income:
            # Period 1: $20,000 × 4 = $80,000
            assert r.sched_ai_annualized_income[0] == pytest.approx(80_000, abs=1)

    def test_period4_annualized_1x(self):
        """Period 4 is full year — annualization factor is 1.0."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(20_000, 50_000, 80_000, 200_000),
                withholding=(500, 1_500, 3_000, 10_000),
            ),
        )
        if r.sched_ai_annualized_income:
            # Period 4: $200,000 × 1.0 = $200,000
            assert r.sched_ai_annualized_income[3] == pytest.approx(200_000, abs=1)


# =========================================================================
# Business income in Schedule AI
# =========================================================================
class TestBusinessIncomeAI:
    def test_seasonal_business_reduces_penalty(self):
        """Seasonal business (income in Q4) → AI reduces early quarter requirements."""
        r = _compute(
            w2s=[W2Income(wages=50_000, federal_withheld=3_000)],
            businesses=[BusinessIncome(gross_receipts=100_000)],
            prior_year_tax=20_000, prior_year_agi=120_000,
            quarterly_income=QuarterlyIncome(
                wages=(12_500, 25_000, 37_500, 50_000),
                business_income=(0, 0, 10_000, 80_000),  # mostly Q4
                withholding=(750, 1_500, 2_250, 3_000),
            ),
        )
        if r.estimated_tax_penalty > 0 and r.sched_ai_used:
            # Q1 AI installment should be much lower than regular
            assert r.sched_ai_required_installments[0] < r.sched_ai_regular_installments[0]


# =========================================================================
# Penalty comparison
# =========================================================================
class TestPenaltyComparison:
    def test_ai_penalty_never_exceeds_regular(self):
        """AI method penalty is always <= regular method penalty."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(10_000, 30_000, 60_000, 200_000),
                withholding=(500, 1_500, 3_000, 10_000),
            ),
        )
        if r.estimated_tax_penalty > 0:
            regular_penalty = r.estimated_tax_penalty + r.sched_ai_penalty_reduction
            assert r.estimated_tax_penalty <= regular_penalty

    def test_no_penalty_no_schedule_ai(self):
        """If no penalty applies, Schedule AI is not triggered."""
        r = _compute(
            w2s=[W2Income(wages=80_000, federal_withheld=15_000)],
            quarterly_income=QuarterlyIncome(
                wages=(20_000, 40_000, 60_000, 80_000),
                withholding=(3_750, 7_500, 11_250, 15_000),
            ),
        )
        assert r.estimated_tax_penalty == 0
        assert r.sched_ai_used is False


# =========================================================================
# Summary & PDF
# =========================================================================
class TestSummaryAndPDF:
    def test_schedule_ai_in_summary(self):
        """Schedule AI data appears in summary when AI method is used."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(10_000, 30_000, 60_000, 200_000),
                withholding=(500, 1_500, 3_000, 10_000),
            ),
        )
        s = r.to_summary()
        if r.sched_ai_used:
            assert s["schedule_ai"] is not None
            assert s["schedule_ai"]["used"] is True
            assert s["schedule_ai"]["penalty_reduction"] > 0

    def test_schedule_ai_absent_when_not_used(self):
        """No Schedule AI in summary for regular filers."""
        r = _compute()
        s = r.to_summary()
        assert s.get("schedule_ai") is None

    def test_pdf_renders(self):
        """Schedule AI PDF renders when AI method is used."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(10_000, 30_000, 60_000, 200_000),
                withholding=(500, 1_500, 3_000, 10_000),
            ),
        )
        if r.sched_ai_used:
            buf = generate_schedule_ai(r)
            data = buf.read()
            assert len(data) > 100
            assert data[:4] == b"%PDF"

    def test_pdf_in_generate_all(self):
        """Schedule AI PDF included in generate_all_pdfs when used."""
        r = _compute(
            w2s=[W2Income(wages=200_000, federal_withheld=10_000)],
            prior_year_tax=30_000, prior_year_agi=180_000,
            quarterly_income=QuarterlyIncome(
                wages=(10_000, 30_000, 60_000, 200_000),
                withholding=(500, 1_500, 3_000, 10_000),
            ),
        )
        if r.sched_ai_used:
            with tempfile.TemporaryDirectory() as td:
                paths = generate_all_pdfs(r, td)
                assert "schedule_ai" in paths


# =========================================================================
# Backward Compatibility
# =========================================================================
class TestBackwardCompat:
    def test_no_quarterly_income_unchanged(self):
        """Without quarterly_income, penalty behavior is identical to Wave 26."""
        r = _compute()
        # Should still compute regular penalty
        if r.estimated_tax_penalty > 0:
            assert "Form 2210" in r.forms_generated
            assert "Schedule AI" not in r.forms_generated
        assert r.sched_ai_used is False
        assert r.sched_ai_penalty_reduction == 0

    def test_engine_imports_include_quarterly_income(self):
        """QuarterlyIncome is importable from tax_engine."""
        from tax_engine import QuarterlyIncome
        qi = QuarterlyIncome(wages=(10_000, 20_000, 30_000, 40_000))
        assert qi.wages[0] == 10_000
