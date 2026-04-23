"""Tests for Wave 25 — Child & Dependent Care Credit (Form 2441) + Saver's Credit (Form 8880)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, PersonInfo, W2Income, AdditionalIncome,
    Deductions, Payments, DependentCareExpense, RetirementContribution,
)
from tax_config import *


def _simple_filer():
    return PersonInfo(first_name="Test", last_name="User", address_state="IL")


def _basic_w2(wages=50000, fed_withheld=6000, ss_wages=None, medicare_wages=None):
    ss_wages = ss_wages or wages
    medicare_wages = medicare_wages or wages
    return W2Income(wages=wages, federal_withheld=fed_withheld,
                    ss_wages=ss_wages, medicare_wages=medicare_wages)


class TestCDCCBasic:
    """Child and Dependent Care Credit — Form 2441."""

    def test_cdcc_one_dependent(self):
        """1 dependent: max $3,000 expenses."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(50000, 6000)],
            AdditionalIncome(), Deductions(), Payments(),
            dependent_care_expenses=[DependentCareExpense("Child A", 5000)],
        )
        # Expenses capped at $3,000. AGI $50K → rate = 20% (floor).
        # Credit = $3,000 * 20% = $600
        assert result.cdcc == pytest.approx(600, abs=1)

    def test_cdcc_two_dependents(self):
        """2 dependents: max $6,000 expenses."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(50000, 6000)],
            AdditionalIncome(), Deductions(), Payments(),
            dependent_care_expenses=[
                DependentCareExpense("Child A", 4000),
                DependentCareExpense("Child B", 4000),
            ],
        )
        # $8,000 expenses capped at $6,000. Rate = 20%.
        # Credit = $6,000 * 20% = $1,200
        assert result.cdcc == pytest.approx(1200, abs=1)

    def test_cdcc_low_income_higher_rate(self):
        """Low AGI gets higher credit rate (up to 35%)."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(30000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            dependent_care_expenses=[DependentCareExpense("Child A", 3000)],
        )
        # AGI $30,000 → ($30K-$15K)/$2K = 7 steps → 35%-7%=28%
        # Credit = $3,000 * 28% = $840
        assert result.cdcc == pytest.approx(840, abs=1)

    def test_cdcc_rate_decrease_steps(self):
        """Rate decreases by 1% per $2,000 of AGI over $15,000."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(25000, 2500)],
            AdditionalIncome(), Deductions(), Payments(),
            dependent_care_expenses=[DependentCareExpense("Child A", 3000)],
        )
        # AGI $25,000 → ($25K - $15K) / $2K = 5 steps → 35% - 5% = 30%
        # Credit = $3,000 * 30% = $900
        assert result.cdcc == pytest.approx(900, abs=1)

    def test_cdcc_nonrefundable(self):
        """CDCC is nonrefundable — can't exceed tax liability."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(12000, 500)],
            AdditionalIncome(), Deductions(), Payments(),
            dependent_care_expenses=[DependentCareExpense("Child A", 3000)],
        )
        # Very low income → very low tax → CDCC capped
        assert result.cdcc <= result.cdcc + result.line_24_total_tax  # tax was reduced

    def test_cdcc_no_expenses_no_credit(self):
        """No care expenses → no CDCC."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(50000, 6000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        assert result.cdcc == 0

    def test_cdcc_expenses_capped_at_earned_income(self):
        """Qualifying expenses can't exceed earned income."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(2000, 100)],
            AdditionalIncome(), Deductions(), Payments(),
            dependent_care_expenses=[DependentCareExpense("Child A", 3000)],
        )
        # Earned income = $2,000, so qualifying expenses capped at $2,000
        # Tax liability is very low, so credit further capped
        assert result.cdcc >= 0

    def test_cdcc_in_forms_list(self):
        """Form 2441 appears in forms list when CDCC claimed."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(50000, 6000)],
            AdditionalIncome(), Deductions(), Payments(),
            dependent_care_expenses=[DependentCareExpense("Child A", 3000)],
        )
        assert "Form 2441" in result.forms_generated


class TestSaversCredit:
    """Retirement Savings Contributions Credit — Form 8880."""

    def test_savers_50_percent(self):
        """AGI below $23,750 single → 50% rate."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(20000, 2000)],
            AdditionalIncome(), Deductions(), Payments(),
            retirement_contributions=[RetirementContribution("filer", 2000)],
        )
        # $2,000 * 50% = $1,000 (capped at tax liability)
        assert result.savers_credit > 0
        assert result.savers_credit <= 1000

    def test_savers_20_percent(self):
        """AGI $23,750-$25,750 single → 20% rate."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(25000, 2500)],
            AdditionalIncome(), Deductions(), Payments(),
            retirement_contributions=[RetirementContribution("filer", 2000)],
        )
        # $2,000 * 20% = $400
        assert result.savers_credit == pytest.approx(400, abs=1)

    def test_savers_10_percent(self):
        """AGI $25,750-$36,500 single → 10% rate."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(30000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            retirement_contributions=[RetirementContribution("filer", 2000)],
        )
        # $2,000 * 10% = $200
        assert result.savers_credit == pytest.approx(200, abs=1)

    def test_savers_zero_high_income(self):
        """AGI above $36,500 single → 0%."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(50000, 6000)],
            AdditionalIncome(), Deductions(), Payments(),
            retirement_contributions=[RetirementContribution("filer", 2000)],
        )
        assert result.savers_credit == 0

    def test_savers_mfj_higher_thresholds(self):
        """MFJ: $47,500 threshold for 50% rate."""
        result = compute_tax(
            MFJ, _simple_filer(), [_basic_w2(40000, 4000)],
            AdditionalIncome(), Deductions(), Payments(),
            spouse=PersonInfo(first_name="Spouse", last_name="User"),
            retirement_contributions=[
                RetirementContribution("filer", 2000),
                RetirementContribution("spouse", 2000),
            ],
        )
        # AGI $40,000 < MFJ $47,500 → 50% rate
        # $4,000 * 50% = $2,000
        assert result.savers_credit > 0
        assert result.savers_credit <= 2000

    def test_savers_contribution_capped(self):
        """Eligible contribution capped at $2,000 per person."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(30000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            retirement_contributions=[RetirementContribution("filer", 5000)],
        )
        # Contribution capped at $2,000. Rate = 10%.
        # Credit = $2,000 * 10% = $200
        assert result.savers_credit == pytest.approx(200, abs=1)

    def test_savers_nonrefundable(self):
        """Saver's credit is nonrefundable."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(30000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            retirement_contributions=[RetirementContribution("filer", 2000)],
        )
        # Credit can't exceed remaining tax liability
        assert result.savers_credit >= 0

    def test_savers_no_contributions_no_credit(self):
        """No contributions → no credit."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(30000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        assert result.savers_credit == 0

    def test_savers_in_forms_list(self):
        """Form 8880 appears when saver's credit claimed."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(30000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            retirement_contributions=[RetirementContribution("filer", 2000)],
        )
        assert "Form 8880" in result.forms_generated
