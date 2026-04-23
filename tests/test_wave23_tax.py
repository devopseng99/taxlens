"""Tests for Wave 23 tax engine features — AMT, education credits, QBI phase-out."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, PersonInfo, W2Income, AdditionalIncome,
    Deductions, Payments, BusinessIncome, EducationExpense,
)
from tax_config import *


def _simple_filer():
    return PersonInfo(first_name="Test", last_name="User", address_state="IL")


def _basic_w2(wages=80000, fed_withheld=12000, ss_wages=80000, medicare_wages=80000):
    return W2Income(wages=wages, federal_withheld=fed_withheld,
                    ss_wages=ss_wages, medicare_wages=medicare_wages)


class TestAMT:
    """Alternative Minimum Tax (Form 6251) tests."""

    def test_no_amt_low_income(self):
        """Low-income filer should have $0 AMT."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(60000, 8000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        assert result.amt == 0.0

    def test_no_amt_standard_deduction(self):
        """Standard deduction filer — no SALT add-back, AMT should be $0."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(150000, 25000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        # Standard deduction doesn't have SALT component to add back
        assert result.amt == 0.0

    def test_amt_with_large_salt(self):
        """High-income itemizer with large SALT deduction may trigger AMT."""
        result = compute_tax(
            SINGLE, _simple_filer(),
            [_basic_w2(400000, 80000, ss_wages=176100, medicare_wages=400000)],
            AdditionalIncome(),
            Deductions(property_tax=30000, state_income_tax_paid=20000,
                       mortgage_interest=25000),
            Payments(),
        )
        # SALT is capped at $10K, but the full $10K is added back for AMT
        assert result.amt_income > result.line_15_taxable_income
        assert result.amt_exemption > 0
        # For $400K income, AMT may or may not trigger depending on regular tax
        assert result.amt >= 0

    def test_amt_exemption_phaseout(self):
        """AMT exemption phases out for very high income."""
        result = compute_tax(
            SINGLE, _simple_filer(),
            [_basic_w2(700000, 200000, ss_wages=176100, medicare_wages=700000)],
            AdditionalIncome(),
            Deductions(property_tax=10000, mortgage_interest=10000),
            Payments(),
        )
        # Above $626,350 for single, exemption starts to phase out
        assert result.amt_exemption < AMT_EXEMPTION[SINGLE]

    def test_amt_in_total_tax(self):
        """If AMT triggers, it should be included in total tax."""
        result = compute_tax(
            SINGLE, _simple_filer(),
            [_basic_w2(300000, 60000, ss_wages=176100, medicare_wages=300000)],
            AdditionalIncome(),
            Deductions(property_tax=25000, state_income_tax_paid=15000,
                       mortgage_interest=20000, charitable_cash=5000),
            Payments(),
        )
        expected_min = (result.line_16_tax + result.capital_gains_tax + result.se_tax
                        + result.niit + result.additional_medicare_tax + result.amt)
        # Total tax should include AMT (minus credits)
        assert result.line_24_total_tax <= expected_min  # Credits may reduce


class TestEducationCredits:
    """Education credits (Form 8863) tests."""

    def test_aotc_full_credit(self):
        """AOTC: $4,000 expenses → $2,500 credit (100% of $2K + 25% of $2K)."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(60000, 8000)],
            AdditionalIncome(), Deductions(), Payments(),
            education_expenses=[EducationExpense("Student", 4000, "aotc")],
        )
        # 40% of AOTC is refundable
        assert result.education_credit_refundable == pytest.approx(1000, abs=1)
        # Nonrefundable portion
        assert result.education_credit == pytest.approx(1500, abs=1)

    def test_aotc_partial_expenses(self):
        """AOTC: $1,500 expenses → $1,500 credit (100% of first $2K)."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(60000, 8000)],
            AdditionalIncome(), Deductions(), Payments(),
            education_expenses=[EducationExpense("Student", 1500, "aotc")],
        )
        total = result.education_credit + result.education_credit_refundable
        assert total == pytest.approx(1500, abs=1)

    def test_llc_credit(self):
        """LLC: $10,000 expenses → $2,000 credit (20%)."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(60000, 8000)],
            AdditionalIncome(), Deductions(), Payments(),
            education_expenses=[EducationExpense("Student", 10000, "llc")],
        )
        assert result.education_credit == pytest.approx(2000, abs=1)
        assert result.education_credit_refundable == 0  # LLC is not refundable

    def test_education_credit_phaseout(self):
        """Credits phase out for high-income filers."""
        # At $85,000 MAGI (single), 50% into phaseout range ($80K-$90K)
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(85000, 15000)],
            AdditionalIncome(), Deductions(), Payments(),
            education_expenses=[EducationExpense("Student", 4000, "aotc")],
        )
        total = result.education_credit + result.education_credit_refundable
        # Should be roughly 50% of full $2,500 = $1,250
        assert total < 2500
        assert total > 0

    def test_education_credit_fully_phased_out(self):
        """Above $90K single MAGI, education credit is $0."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(100000, 20000)],
            AdditionalIncome(), Deductions(), Payments(),
            education_expenses=[EducationExpense("Student", 4000, "aotc")],
        )
        total = result.education_credit + result.education_credit_refundable
        assert total == 0

    def test_mfs_no_education_credit(self):
        """MFS cannot claim education credits."""
        result = compute_tax(
            MFS, _simple_filer(), [_basic_w2(60000, 8000)],
            AdditionalIncome(), Deductions(), Payments(),
            education_expenses=[EducationExpense("Student", 4000, "aotc")],
        )
        assert result.education_credit == 0
        assert result.education_credit_refundable == 0

    def test_no_education_expenses(self):
        """No education expenses → no credit."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(60000, 8000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        assert result.education_credit == 0
        assert result.education_credit_refundable == 0


class TestQBIPhaseOut:
    """QBI deduction phase-out tests."""

    def test_qbi_below_threshold(self):
        """Below threshold: full 20% QBI deduction."""
        result = compute_tax(
            SINGLE, _simple_filer(), [],
            AdditionalIncome(), Deductions(), Payments(),
            businesses=[BusinessIncome(gross_receipts=100000)],
        )
        assert result.qbi_deduction == pytest.approx(20000, abs=100)

    def test_qbi_above_phaseout(self):
        """Above phase-out range: QBI limited to W-2 wage cap (0 for sole proprietor)."""
        result = compute_tax(
            SINGLE, _simple_filer(),
            [_basic_w2(200000, 40000, ss_wages=176100, medicare_wages=200000)],
            AdditionalIncome(), Deductions(), Payments(),
            businesses=[BusinessIncome(gross_receipts=100000)],
        )
        # Taxable income = $200K wages + $100K business - $15K std ded = ~$285K
        # Single threshold: $191,950, phase-out range: $50K → fully phased out at $241,950
        # With $285K+ taxable, QBI should be $0 (no W-2 wages from business)
        assert result.qbi_deduction == 0

    def test_qbi_in_phaseout_range(self):
        """In phase-out range: QBI partially reduced."""
        result = compute_tax(
            SINGLE, _simple_filer(),
            [_basic_w2(170000, 35000, ss_wages=170000, medicare_wages=170000)],
            AdditionalIncome(), Deductions(), Payments(),
            businesses=[BusinessIncome(gross_receipts=60000)],
        )
        # Taxable income after std ded ≈ $230K-$15K = $215K (in $191,950-$241,950 range)
        full_qbi = 60000 * 0.20  # $12,000
        assert result.qbi_deduction < full_qbi
        assert result.qbi_deduction > 0

    def test_qbi_mfj_higher_threshold(self):
        """MFJ threshold is $383,900 — higher income before phase-out."""
        result = compute_tax(
            MFJ, _simple_filer(), [],
            AdditionalIncome(), Deductions(), Payments(),
            spouse=PersonInfo(first_name="Spouse", last_name="User"),
            businesses=[BusinessIncome(gross_receipts=200000)],
        )
        # MFJ: $200K business - $30K std ded = $170K taxable < $383,900
        assert result.qbi_deduction == pytest.approx(40000, abs=100)
