"""Tests for Wave 24 — Earned Income Tax Credit (EITC / Schedule EIC)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, PersonInfo, W2Income, AdditionalIncome,
    Deductions, Payments, BusinessIncome, CapitalTransaction,
)
from tax_config import *


def _simple_filer():
    return PersonInfo(first_name="Test", last_name="User", address_state="IL")


def _basic_w2(wages=20000, fed_withheld=1500, ss_wages=None, medicare_wages=None):
    ss_wages = ss_wages or wages
    medicare_wages = medicare_wages or wages
    return W2Income(wages=wages, federal_withheld=fed_withheld,
                    ss_wages=ss_wages, medicare_wages=medicare_wages)


class TestEITCNoChildren:
    """EITC with 0 qualifying children."""

    def test_eitc_phase_in(self):
        """Low income in phase-in range: credit grows with earned income."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(5000, 300)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        # $5,000 * 7.65% = $382.50
        assert result.eitc == pytest.approx(382.50, abs=1)

    def test_eitc_max_no_children(self):
        """At earned income amount ($8,490): max credit $649."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(9000, 500)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        # $9,000 * 7.65% = $688.50, capped at $649
        # Phase-out hasn't started (starts at $10,620 for single)
        assert result.eitc == pytest.approx(649, abs=1)

    def test_eitc_phaseout_no_children(self):
        """In phase-out range: credit reduces."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(14000, 800)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        # Phase-out: ($14,000 - $10,620) * 7.65% = $258.57 reduction
        # $649 - $258.57 = $390.43
        assert result.eitc == pytest.approx(390.43, abs=2)
        assert result.eitc > 0

    def test_eitc_zero_high_income(self):
        """High income: $0 EITC."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(50000, 6000)],
            AdditionalIncome(), Deductions(), Payments(),
        )
        assert result.eitc == 0


class TestEITCWithChildren:
    """EITC with qualifying children."""

    def test_eitc_one_child_max(self):
        """1 child at plateau: max credit $4,328."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(15000, 1000)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=1,
        )
        # $15,000 * 34% = $5,100 > $4,328, so capped at max
        # AGI $15,000 < phase-out start $22,080, so no reduction
        assert result.eitc == pytest.approx(4328, abs=1)

    def test_eitc_two_children_max(self):
        """2 children at plateau: max credit $7,152."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(20000, 1500)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=2,
        )
        # $20,000 * 40% = $8,000 > $7,152, capped at max
        # AGI $20,000 < $22,080 phase-out start
        assert result.eitc == pytest.approx(7152, abs=1)

    def test_eitc_three_children_max(self):
        """3+ children at plateau: max credit $8,046."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(20000, 1500)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=4,  # 4 children → capped at 3 for EITC
        )
        # $20,000 * 45% = $9,000 > $8,046, capped
        assert result.eitc == pytest.approx(8046, abs=1)

    def test_eitc_one_child_phaseout(self):
        """1 child in phase-out range."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(30000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=1,
        )
        # Phase-out: ($30,000 - $22,080) * 15.98% = $1,265.22
        # $4,328 - $1,265.22 = $3,062.78
        assert result.eitc == pytest.approx(3062.78, abs=5)

    def test_eitc_two_children_phaseout_gone(self):
        """2 children: above phase-out range → $0."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(60000, 8000)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=2,
        )
        # Phase-out: ($60,000 - $22,080) * 21.06% = $7,989 > $7,152
        assert result.eitc == 0

    def test_eitc_phase_in_one_child(self):
        """1 child, very low income in phase-in."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(5000, 200)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=1,
        )
        # $5,000 * 34% = $1,700
        assert result.eitc == pytest.approx(1700, abs=1)


class TestEITCMFJ:
    """EITC for MFJ filers (higher phase-out threshold)."""

    def test_eitc_mfj_higher_phaseout(self):
        """MFJ: phase-out starts at $29,200 (1 child) vs $22,080 single."""
        result = compute_tax(
            MFJ, _simple_filer(), [_basic_w2(25000, 2000)],
            AdditionalIncome(), Deductions(), Payments(),
            spouse=PersonInfo(first_name="Spouse", last_name="User"),
            num_dependents=1,
        )
        # $25,000 < MFJ phase-out start $29,200 → full credit
        assert result.eitc == pytest.approx(4328, abs=1)

    def test_eitc_mfj_in_phaseout(self):
        """MFJ: in phase-out range."""
        result = compute_tax(
            MFJ, _simple_filer(), [_basic_w2(35000, 3000)],
            AdditionalIncome(), Deductions(), Payments(),
            spouse=PersonInfo(first_name="Spouse", last_name="User"),
            num_dependents=1,
        )
        # Phase-out: ($35,000 - $29,200) * 15.98% = $926.84
        # $4,328 - $926.84 = $3,401.16
        assert result.eitc == pytest.approx(3401.16, abs=5)


class TestEITCDisqualification:
    """Scenarios where EITC is disqualified."""

    def test_mfs_no_eitc(self):
        """MFS filers cannot claim EITC."""
        result = compute_tax(
            MFS, _simple_filer(), [_basic_w2(15000, 1000)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=1,
        )
        assert result.eitc == 0

    def test_investment_income_disqualifies(self):
        """Investment income > $11,600 disqualifies EITC."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(15000, 1000)],
            AdditionalIncome(other_interest=12000),
            Deductions(), Payments(),
            num_dependents=1,
        )
        assert result.eitc == 0

    def test_investment_income_just_under(self):
        """Investment income at $11,600 still qualifies."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(15000, 1000)],
            AdditionalIncome(other_interest=11600),
            Deductions(), Payments(),
            num_dependents=1,
        )
        # Qualifies but AGI is now $15K + $11.6K = $26.6K → in phaseout
        assert result.eitc > 0

    def test_capital_gains_count_as_investment(self):
        """Capital gains count toward investment income limit."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(15000, 1000)],
            AdditionalIncome(capital_transactions=[
                CapitalTransaction(proceeds=20000, cost_basis=5000, is_long_term=True),
            ]),
            Deductions(), Payments(),
            num_dependents=1,
        )
        # $15,000 capital gain > $11,600 limit
        assert result.eitc == 0


class TestEITCSelfEmployed:
    """EITC with self-employment income."""

    def test_se_income_counts_as_earned(self):
        """Net SE income counts as earned income for EITC."""
        result = compute_tax(
            SINGLE, _simple_filer(), [],
            AdditionalIncome(), Deductions(), Payments(),
            businesses=[BusinessIncome(gross_receipts=15000)],
            num_dependents=1,
        )
        # SE taxable = $15,000 * 0.9235 = $13,852.50
        # Earned income = $0 W-2 + $13,852.50 SE = $13,852.50
        # $13,852.50 * 34% = $4,709.85 → capped at $4,328
        # AGI = $15,000 - SE deduction ≈ $13,852 → below $22,080 phaseout
        assert result.eitc == pytest.approx(4328, abs=5)

    def test_no_earned_income_no_eitc(self):
        """No earned income (only investment) → $0 EITC."""
        result = compute_tax(
            SINGLE, _simple_filer(), [],
            AdditionalIncome(other_interest=5000),
            Deductions(), Payments(),
            num_dependents=1,
        )
        # Earned income = $0 → credit from phase-in = $0
        assert result.eitc == 0


class TestEITCRefundable:
    """EITC as a refundable credit increases refund."""

    def test_eitc_increases_refund(self):
        """EITC should increase total payments and refund."""
        # Without EITC scenario (high income)
        result_high = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(80000, 12000)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=1,
        )
        # With EITC scenario (low income)
        result_low = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(15000, 1000)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=1,
        )
        assert result_high.eitc == 0
        assert result_low.eitc > 0
        # EITC is in total_payments
        assert result_low.eitc <= result_low.line_33_total_payments

    def test_eitc_in_forms_list(self):
        """Schedule EIC appears in forms list when EITC claimed."""
        result = compute_tax(
            SINGLE, _simple_filer(), [_basic_w2(15000, 1000)],
            AdditionalIncome(), Deductions(), Payments(),
            num_dependents=1,
        )
        assert "Schedule EIC" in result.forms_generated
