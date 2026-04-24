"""Wave 49 — Student loan interest phaseout + foreign tax credit + gambling income."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, W2Income, AdditionalIncome, Deductions, Payments, PersonInfo,
    GamblingIncome, ForeignTaxCredit,
)


class TestStudentLoanPhaseout(unittest.TestCase):
    """Test student loan interest MAGI phaseout per IRC §221(b)(2)."""

    def _base_args(self, wages=50000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=5000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(student_loan_interest=2500),
            payments=Payments(),
        )

    def test_full_deduction_below_phaseout(self):
        """Single filer below $80K gets full $2,500 deduction."""
        args = self._base_args(wages=70000)
        result = compute_tax(**args)
        self.assertEqual(result.student_loan_deduction, 2500)
        self.assertFalse(result.student_loan_phaseout_applied)

    def test_partial_phaseout_single(self):
        """Single filer in $80K-$95K range gets partial deduction."""
        args = self._base_args(wages=87500)  # Midpoint
        result = compute_tax(**args)
        self.assertTrue(result.student_loan_phaseout_applied)
        self.assertGreater(result.student_loan_deduction, 0)
        self.assertLess(result.student_loan_deduction, 2500)

    def test_zero_deduction_above_phaseout(self):
        """Single filer above $95K gets $0 deduction."""
        args = self._base_args(wages=100000)
        result = compute_tax(**args)
        self.assertTrue(result.student_loan_phaseout_applied)
        self.assertEqual(result.student_loan_deduction, 0)

    def test_mfj_phaseout_range(self):
        """MFJ: $165K-$195K phaseout range."""
        args = self._base_args(wages=180000, filing_status="mfj")
        result = compute_tax(**args)
        self.assertTrue(result.student_loan_phaseout_applied)
        self.assertGreater(result.student_loan_deduction, 0)
        self.assertLess(result.student_loan_deduction, 2500)

    def test_mfs_no_deduction(self):
        """MFS: no student loan deduction allowed."""
        args = self._base_args(wages=30000, filing_status="mfs")
        result = compute_tax(**args)
        self.assertTrue(result.student_loan_phaseout_applied)
        self.assertEqual(result.student_loan_deduction, 0)

    def test_hoh_same_as_single(self):
        """HoH uses same phaseout range as single ($80K-$95K)."""
        args = self._base_args(wages=87500, filing_status="hoh")
        result = compute_tax(**args)
        self.assertTrue(result.student_loan_phaseout_applied)
        self.assertGreater(result.student_loan_deduction, 0)

    def test_capped_at_2500(self):
        """Student loan interest capped at $2,500 before phaseout."""
        args = self._base_args(wages=50000)
        args["deductions"] = Deductions(student_loan_interest=5000)
        result = compute_tax(**args)
        self.assertEqual(result.student_loan_deduction, 2500)

    def test_before_phaseout_tracks_original(self):
        """student_loan_deduction_before_phaseout preserves pre-phaseout amount."""
        args = self._base_args(wages=100000)
        result = compute_tax(**args)
        self.assertEqual(result.student_loan_deduction_before_phaseout, 2500)
        self.assertEqual(result.student_loan_deduction, 0)

    def test_phaseout_reduces_agi(self):
        """Less student loan deduction → higher AGI."""
        args_low = self._base_args(wages=70000)
        result_low = compute_tax(**args_low)
        args_high = self._base_args(wages=100000)
        result_high = compute_tax(**args_high)
        # At $70K, full deduction reduces AGI by $2,500
        # At $100K, no deduction — AGI is higher
        self.assertGreater(result_high.line_11_agi - result_low.line_11_agi, 30000 - 100)

    def test_no_interest_no_deduction(self):
        """No student loan interest = no deduction, no phaseout."""
        args = self._base_args(wages=50000)
        args["deductions"] = Deductions(student_loan_interest=0)
        result = compute_tax(**args)
        self.assertEqual(result.student_loan_deduction, 0)
        self.assertFalse(result.student_loan_phaseout_applied)


class TestGamblingIncome(unittest.TestCase):
    """Test Form W-2G gambling income and §165(d) loss limitation."""

    def _base_args(self, wages=50000):
        return dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=5000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_gambling_winnings_taxable(self):
        """Gambling winnings included in total income."""
        args = self._base_args()
        args["gambling_income"] = [GamblingIncome(winnings=5000)]
        result = compute_tax(**args)
        self.assertEqual(result.gambling_winnings, 5000)
        self.assertEqual(result.line_9_total_income, 55000)

    def test_losses_capped_at_winnings(self):
        """Gambling losses cannot exceed winnings (§165(d))."""
        args = self._base_args()
        args["gambling_income"] = [GamblingIncome(winnings=5000)]
        args["gambling_losses"] = 10000
        result = compute_tax(**args)
        self.assertEqual(result.gambling_losses, 5000)  # Capped at winnings

    def test_losses_reduce_net_income(self):
        """Gambling losses offset winnings in other income."""
        args = self._base_args()
        args["gambling_income"] = [GamblingIncome(winnings=5000)]
        args["gambling_losses"] = 3000
        result = compute_tax(**args)
        self.assertEqual(result.gambling_losses, 3000)
        # Net gambling = 5000 - 3000 = 2000 added to other income
        self.assertEqual(result.line_9_total_income, 52000)

    def test_full_offset_zero_net(self):
        """Losses equal to winnings = $0 net gambling income."""
        args = self._base_args()
        args["gambling_income"] = [GamblingIncome(winnings=5000)]
        args["gambling_losses"] = 5000
        result = compute_tax(**args)
        self.assertEqual(result.line_9_total_income, 50000)

    def test_withholding_flows_to_line_25(self):
        """W-2G withholding included in federal withholding."""
        args = self._base_args()
        args["gambling_income"] = [GamblingIncome(winnings=10000, federal_withheld=2400)]
        result = compute_tax(**args)
        self.assertEqual(result.gambling_federal_withheld, 2400)
        self.assertEqual(result.line_25_federal_withheld, 5000 + 2400)

    def test_multiple_w2g(self):
        """Multiple W-2G forms aggregate correctly."""
        args = self._base_args()
        args["gambling_income"] = [
            GamblingIncome(winnings=3000, federal_withheld=720),
            GamblingIncome(winnings=7000, federal_withheld=1680),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.gambling_winnings, 10000)
        self.assertEqual(result.gambling_federal_withheld, 2400)

    def test_no_gambling_no_effect(self):
        """No gambling income = no effect on anything."""
        args = self._base_args()
        result = compute_tax(**args)
        self.assertEqual(result.gambling_winnings, 0)
        self.assertEqual(result.gambling_losses, 0)


class TestForeignTaxCredit(unittest.TestCase):
    """Test simplified foreign tax credit (Form 1116)."""

    def _base_args(self, wages=100000):
        return dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=15000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_basic_foreign_tax_credit(self):
        """Foreign tax credit reduces total tax."""
        args = self._base_args()
        args["foreign_tax_credits"] = [
            ForeignTaxCredit(country="UK", foreign_source_income=10000, foreign_tax_paid=2000),
        ]
        result = compute_tax(**args)
        self.assertGreater(result.foreign_tax_credit, 0)
        self.assertEqual(result.foreign_source_income, 10000)
        self.assertEqual(result.foreign_tax_paid, 2000)

    def test_credit_limited_by_income_ratio(self):
        """Credit limited by foreign income / total taxable income ratio."""
        args = self._base_args()
        args["foreign_tax_credits"] = [
            ForeignTaxCredit(country="UK", foreign_source_income=10000, foreign_tax_paid=50000),
        ]
        result = compute_tax(**args)
        # Credit can't exceed tax * (10K / taxable income)
        max_ratio = result.line_16_tax * (10000 / result.line_15_taxable_income) if result.line_15_taxable_income > 0 else 0
        self.assertAlmostEqual(result.foreign_tax_credit, min(50000, max_ratio), places=0)

    def test_credit_limited_by_tax_liability(self):
        """Credit can't exceed total tax liability."""
        args = self._base_args(wages=20000)
        args["foreign_tax_credits"] = [
            ForeignTaxCredit(country="DE", foreign_source_income=20000, foreign_tax_paid=10000),
        ]
        result = compute_tax(**args)
        self.assertLessEqual(result.foreign_tax_credit, result.line_16_tax)

    def test_multiple_countries(self):
        """Multiple foreign tax credits from different countries aggregate."""
        args = self._base_args()
        args["foreign_tax_credits"] = [
            ForeignTaxCredit(country="UK", foreign_source_income=5000, foreign_tax_paid=1000),
            ForeignTaxCredit(country="DE", foreign_source_income=5000, foreign_tax_paid=1500),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.foreign_source_income, 10000)
        self.assertEqual(result.foreign_tax_paid, 2500)
        self.assertGreater(result.foreign_tax_credit, 0)

    def test_no_foreign_income_no_credit(self):
        """No foreign tax credits = no effect."""
        args = self._base_args()
        result = compute_tax(**args)
        self.assertEqual(result.foreign_tax_credit, 0)

    def test_reduces_total_tax(self):
        """Foreign tax credit reduces line_24_total_tax."""
        args_no = self._base_args()
        result_no = compute_tax(**args_no)

        args_ftc = self._base_args()
        args_ftc["foreign_tax_credits"] = [
            ForeignTaxCredit(country="UK", foreign_source_income=20000, foreign_tax_paid=3000),
        ]
        result_ftc = compute_tax(**args_ftc)
        self.assertLess(result_ftc.line_24_total_tax, result_no.line_24_total_tax)


class TestBackwardCompat(unittest.TestCase):
    """Backward compatibility — new params default to no effect."""

    def test_no_gambling_no_foreign_no_change(self):
        """Without new params, result is unchanged."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="T", last_name="U"),
            w2s=[W2Income(wages=50000, federal_withheld=5000, ss_wages=50000, medicare_wages=50000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        self.assertEqual(result.gambling_winnings, 0)
        self.assertEqual(result.foreign_tax_credit, 0)
        self.assertEqual(result.student_loan_deduction, 0)


if __name__ == "__main__":
    unittest.main()
