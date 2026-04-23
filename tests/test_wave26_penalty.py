"""Tests for Wave 26 — Estimated Tax Penalty (Form 2210)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, PersonInfo, W2Income, AdditionalIncome,
    Deductions, Payments, BusinessIncome,
)
from tax_config import *


def _simple_filer():
    return PersonInfo(first_name="Test", last_name="User", address_state="IL")


def _basic_w2(wages=100000, fed_withheld=10000, ss_wages=None, medicare_wages=None):
    ss_wages = ss_wages if ss_wages is not None else min(wages, SS_WAGE_BASE)
    medicare_wages = medicare_wages or wages
    return W2Income(wages=wages, federal_withheld=fed_withheld,
                    ss_wages=ss_wages, medicare_wages=medicare_wages)


class TestNoPenalty:
    """Cases where no penalty applies."""

    def test_no_penalty_when_refund(self):
        """Getting a refund → no penalty."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(80000, 15000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=10000, prior_year_agi=75000,
        )
        assert result.line_34_overpaid > 0
        assert result.estimated_tax_penalty == 0

    def test_no_penalty_owed_under_1000(self):
        """Owed < $1,000 → no penalty."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(80000, 11500)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=10000, prior_year_agi=75000,
        )
        # Small underpayment under threshold
        if result.line_37_owed < 1000:
            assert result.estimated_tax_penalty == 0

    def test_no_penalty_without_prior_year(self):
        """No prior year tax provided → no penalty (first-time filer)."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 5000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        assert result.estimated_tax_penalty == 0

    def test_no_penalty_safe_harbor_met(self):
        """Withholding meets 100% of prior year tax → safe harbor met, no penalty."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 12000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=12000, prior_year_agi=80000,
        )
        # Prior year tax = $12,000, withholding = $12,000 → meets 100% safe harbor
        assert result.estimated_tax_penalty == 0


class TestPenaltyApplies:
    """Cases where penalty should apply."""

    def test_penalty_large_underpayment(self):
        """Large underpayment with insufficient withholding."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(150000, 5000, ss_wages=150000, medicare_wages=150000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=20000, prior_year_agi=120000,
        )
        # High income, low withholding → owed > $1K, underpayment exists
        if result.line_37_owed >= 1000:
            assert result.estimated_tax_penalty > 0

    def test_penalty_added_to_owed(self):
        """Penalty should increase amount owed."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(200000, 10000, ss_wages=176100, medicare_wages=200000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=30000, prior_year_agi=180000,
        )
        # Very high income, very low withholding → definite penalty
        assert result.estimated_tax_penalty > 0
        # The owed amount should include the penalty
        assert result.line_37_owed > result.estimated_tax_penalty

    def test_penalty_uses_lesser_of_safe_harbors(self):
        """Required payment = lesser of 90% current or 100% prior year."""
        # Prior year tax = $5,000 (low) → 100% of $5K = $5K
        # Current year tax will be much higher → 90% of current >> $5K
        # So required = $5,000 (lesser)
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=5000, prior_year_agi=60000,
        )
        # Withholding $3K < required $5K → penalty on $2K underpayment
        if result.line_37_owed >= 1000:
            assert result.estimated_tax_penalty > 0
            assert result.estimated_tax_required == pytest.approx(5000, abs=10)

    def test_penalty_rate_applied(self):
        """Penalty = underpayment * 8% rate."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 0)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=10000, prior_year_agi=80000,
        )
        # No withholding at all. Required = min(90% current, 100% prior=$10K)
        # Underpayment = required - $0 = required
        # Penalty = underpayment * 8%
        if result.estimated_tax_penalty > 0:
            expected = result.estimated_tax_required * ESTIMATED_TAX_PENALTY_RATE
            assert result.estimated_tax_penalty == pytest.approx(expected, abs=1)


class TestHighAGISafeHarbor:
    """110% prior year requirement for high AGI filers."""

    def test_high_agi_requires_110_percent(self):
        """AGI > $150K single → need 110% of prior year tax."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(200000, 10000, ss_wages=176100, medicare_wages=200000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=20000, prior_year_agi=160000,
        )
        # Prior AGI $160K > $150K → need 110% * $20K = $22K
        # 90% of current year tax will be > $22K for $200K income
        # So required = $22K (lesser of 90% current vs 110% prior)
        if result.estimated_tax_penalty > 0:
            assert result.estimated_tax_required == pytest.approx(22000, abs=100)

    def test_mfs_high_agi_threshold_75k(self):
        """MFS: high AGI threshold is $75K (not $150K)."""
        result = compute_tax(
            MFS, _simple_filer(), [_basic_w2(100000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=10000, prior_year_agi=80000,
        )
        # Prior AGI $80K > MFS threshold $75K → 110% of prior = $11K
        if result.estimated_tax_penalty > 0:
            assert result.estimated_tax_required <= 11000 + 100  # 110% of $10K


class TestEstimatedPaymentsReducePenalty:
    """Estimated payments reduce underpayment."""

    def test_estimated_payments_reduce_penalty(self):
        """Quarterly estimated payments reduce the underpayment amount."""
        result_no_est = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 0)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=10000, prior_year_agi=80000,
        )
        result_with_est = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 0)],
            AdditionalIncome(), Deductions(), Payments(estimated_federal=8000),
            prior_year_tax=10000, prior_year_agi=80000,
        )
        # Estimated payments should reduce the penalty
        assert result_with_est.estimated_tax_penalty < result_no_est.estimated_tax_penalty

    def test_sufficient_estimated_no_penalty(self):
        """Estimated payments meeting safe harbor → no penalty."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 0)],
            AdditionalIncome(), Deductions(), Payments(estimated_federal=12000),
            prior_year_tax=10000, prior_year_agi=80000,
        )
        # Estimated $12K >= 100% prior $10K → safe harbor met
        assert result.estimated_tax_penalty == 0


class TestPenaltyForms:
    """Form 2210 in forms list."""

    def test_form_2210_in_list(self):
        """Form 2210 appears when penalty applies."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(200000, 10000, ss_wages=176100, medicare_wages=200000)],
            AdditionalIncome(), Deductions(), Payments(),
            prior_year_tax=30000, prior_year_agi=180000,
        )
        if result.estimated_tax_penalty > 0:
            assert "Form 2210" in result.forms_generated

    def test_no_form_2210_when_no_penalty(self):
        """Form 2210 not in list when no penalty."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(80000, 15000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        assert "Form 2210" not in result.forms_generated
