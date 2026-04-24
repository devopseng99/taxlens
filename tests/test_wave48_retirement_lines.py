"""Wave 48 — Retirement line reclassification (4a/4b/5a/5b) + IRA phaseout."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, W2Income, AdditionalIncome, Deductions, Payments, PersonInfo,
    RetirementDistribution, IRAContribution,
)


class TestRetirementLineClassification(unittest.TestCase):
    """Test that IRA distributions go to lines 4a/4b, pensions to 5a/5b."""

    def _base_args(self, wages=50000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=5000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_ira_distribution_lines_4a_4b(self):
        """IRA distribution routes to lines 4a/4b."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=20000, taxable_amount=20000, is_ira=True),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.line_4a_ira_distributions, 20000)
        self.assertEqual(result.line_4b_ira_taxable, 20000)
        self.assertEqual(result.line_5a_pensions, 0)
        self.assertEqual(result.line_5b_pensions_taxable, 0)

    def test_pension_distribution_lines_5a_5b(self):
        """Pension distribution routes to lines 5a/5b."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=30000, taxable_amount=25000, is_ira=False),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.line_4a_ira_distributions, 0)
        self.assertEqual(result.line_4b_ira_taxable, 0)
        self.assertEqual(result.line_5a_pensions, 30000)
        self.assertEqual(result.line_5b_pensions_taxable, 25000)

    def test_mixed_ira_and_pension(self):
        """Mixed IRA + pension split correctly across both line pairs."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=15000, taxable_amount=15000, is_ira=True),
            RetirementDistribution(gross_distribution=25000, taxable_amount=20000, is_ira=False),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.line_4a_ira_distributions, 15000)
        self.assertEqual(result.line_4b_ira_taxable, 15000)
        self.assertEqual(result.line_5a_pensions, 25000)
        self.assertEqual(result.line_5b_pensions_taxable, 20000)
        # Totals still aggregate
        self.assertEqual(result.retirement_gross_distributions, 40000)
        self.assertEqual(result.retirement_taxable_amount, 35000)

    def test_roth_ira_zero_taxable(self):
        """Roth IRA: gross shows on 4a, taxable 4b = 0."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=10000, is_ira=True, is_roth=True),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.line_4a_ira_distributions, 10000)
        self.assertEqual(result.line_4b_ira_taxable, 0)

    def test_rollover_pension_zero_taxable(self):
        """Rollover (code G) pension: gross on 5a, taxable 5b = 0."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=50000, distribution_code="G", is_ira=False),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.line_5a_pensions, 50000)
        self.assertEqual(result.line_5b_pensions_taxable, 0)

    def test_default_is_pension(self):
        """Default is_ira=False routes to pension lines (backward compat)."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=20000, taxable_amount=20000),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.line_4a_ira_distributions, 0)
        self.assertEqual(result.line_5a_pensions, 20000)

    def test_retirement_in_total_income(self):
        """Lines 4b + 5b included in total income (not line_8_other_income)."""
        args = self._base_args(wages=50000)
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=10000, taxable_amount=10000, is_ira=True),
            RetirementDistribution(gross_distribution=15000, taxable_amount=12000, is_ira=False),
        ]
        result = compute_tax(**args)
        # Total income = wages(50K) + IRA taxable(10K) + pension taxable(12K) = 72K
        self.assertEqual(result.line_9_total_income, 72000)

    def test_early_withdrawal_penalty_both_types(self):
        """Early withdrawal penalty works for both IRA and pension."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=10000, taxable_amount=10000,
                                   is_ira=True, is_early=True, distribution_code="1"),
            RetirementDistribution(gross_distribution=20000, taxable_amount=20000,
                                   is_ira=False, is_early=True, distribution_code="1"),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_early_penalty, 3000)  # 10% of 30K


class TestIRADeductionPhaseout(unittest.TestCase):
    """Test IRA deduction income-based phaseout for active plan participants."""

    def _base_args(self, wages=50000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=5000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_no_phaseout_not_active(self):
        """No phaseout when not an active plan participant."""
        args = self._base_args(wages=150000)
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 7000)
        self.assertFalse(result.ira_phaseout_applied)

    def test_full_deduction_below_phaseout(self):
        """Active participant below phaseout range gets full deduction."""
        args = self._base_args(wages=70000)
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["filer_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 7000)
        self.assertFalse(result.ira_phaseout_applied)

    def test_partial_phaseout_single(self):
        """Single active participant in phaseout range gets partial deduction (2025: $79K-$89K)."""
        args = self._base_args(wages=84000)  # Midpoint of $79K-$89K
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["filer_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertTrue(result.ira_phaseout_applied)
        self.assertGreater(result.ira_deduction, 0)
        self.assertLess(result.ira_deduction, 7000)

    def test_zero_deduction_above_phaseout(self):
        """Single active participant above phaseout range gets $0 deduction (2025: >$89K)."""
        args = self._base_args(wages=95000)
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["filer_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertTrue(result.ira_phaseout_applied)
        self.assertEqual(result.ira_deduction, 0)

    def test_mfj_filer_active(self):
        """MFJ filer active: phaseout $126K-$146K (2025)."""
        args = self._base_args(wages=136000, filing_status="mfj")  # Midpoint
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["filer_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertTrue(result.ira_phaseout_applied)
        self.assertGreater(result.ira_deduction, 0)
        self.assertLess(result.ira_deduction, 7000)

    def test_mfj_spouse_active_filer_not(self):
        """MFJ: filer NOT active, spouse IS active — higher phaseout $236K-$246K (2025)."""
        args = self._base_args(wages=241000, filing_status="mfj")  # Midpoint
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["spouse_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertTrue(result.ira_phaseout_applied)
        self.assertGreater(result.ira_deduction, 0)
        self.assertLess(result.ira_deduction, 7000)

    def test_mfj_spouse_active_below_phaseout(self):
        """MFJ: spouse active, income below $236K — full deduction."""
        args = self._base_args(wages=200000, filing_status="mfj")
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["spouse_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 7000)
        self.assertFalse(result.ira_phaseout_applied)

    def test_mfs_tiny_phaseout_range(self):
        """MFS active participant: $0-$10K phaseout — almost always fully phased out."""
        args = self._base_args(wages=12000, filing_status="mfs")
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["filer_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertTrue(result.ira_phaseout_applied)
        self.assertEqual(result.ira_deduction, 0)  # $12K > $10K end

    def test_2024_phaseout_different(self):
        """2024 uses different phaseout ranges ($77K-$87K single)."""
        args = self._base_args(wages=82000)  # Midpoint of 2024 range
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["filer_active_plan_participant"] = True
        args["tax_year"] = 2024
        result = compute_tax(**args)
        self.assertTrue(result.ira_phaseout_applied)
        self.assertGreater(result.ira_deduction, 0)
        self.assertLess(result.ira_deduction, 7000)

    def test_before_phaseout_tracks_original(self):
        """ira_deduction_before_phaseout preserves the pre-phaseout amount."""
        args = self._base_args(wages=95000)
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["filer_active_plan_participant"] = True
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction_before_phaseout, 7000)
        self.assertEqual(result.ira_deduction, 0)

    def test_phaseout_reduces_agi(self):
        """Less IRA deduction → higher AGI compared to no phaseout."""
        args_no_phaseout = self._base_args(wages=85000)
        args_no_phaseout["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        result_no = compute_tax(**args_no_phaseout)

        args_phaseout = self._base_args(wages=85000)
        args_phaseout["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args_phaseout["filer_active_plan_participant"] = True
        result_yes = compute_tax(**args_phaseout)

        # With phaseout, less deduction → higher AGI
        self.assertGreater(result_yes.line_11_agi, result_no.line_11_agi)

    def test_spouse_flags_ignored_single(self):
        """Spouse active plan flag has no effect on single filers."""
        args = self._base_args(wages=250000)
        args["ira_contributions"] = [IRAContribution(contribution_amount=7000)]
        args["spouse_active_plan_participant"] = True
        result = compute_tax(**args)
        # Single filer: spouse_active_plan_participant doesn't trigger phaseout
        self.assertEqual(result.ira_deduction, 7000)
        self.assertFalse(result.ira_phaseout_applied)


class TestBackwardCompat(unittest.TestCase):
    """Backward compatibility — existing retirement tests still pass."""

    def test_no_is_ira_defaults_pension(self):
        """RetirementDistribution without is_ira defaults to pension (lines 5a/5b)."""
        d = RetirementDistribution(gross_distribution=20000, taxable_amount=20000)
        self.assertFalse(d.is_ira)

    def test_no_active_plan_no_phaseout(self):
        """Without active plan flags, IRA deduction is not phased out."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="T", last_name="U"),
            w2s=[W2Income(wages=200000, federal_withheld=30000, ss_wages=200000, medicare_wages=200000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            ira_contributions=[IRAContribution(contribution_amount=7000)],
        )
        self.assertEqual(result.ira_deduction, 7000)
        self.assertFalse(result.ira_phaseout_applied)


if __name__ == "__main__":
    unittest.main()
