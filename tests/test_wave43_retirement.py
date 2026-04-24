"""Wave 43 — Retirement Income (Form 1099-R + IRA Contributions) tests."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    RetirementDistribution, IRAContribution, compute_tax,
    W2Income, AdditionalIncome, Deductions, Payments, PersonInfo,
)


class TestRetirementDistribution(unittest.TestCase):
    """Test RetirementDistribution dataclass and properties."""

    def test_normal_distribution_taxable(self):
        """Normal distribution (code 7) — full taxable amount."""
        d = RetirementDistribution(
            payer_name="Fidelity", gross_distribution=50000,
            taxable_amount=50000, distribution_code="7",
        )
        self.assertEqual(d.taxable, 50000)
        self.assertEqual(d.early_withdrawal_penalty, 0)

    def test_early_distribution_penalty(self):
        """Early distribution (code 1, is_early=True) — 10% penalty."""
        d = RetirementDistribution(
            payer_name="Vanguard", gross_distribution=20000,
            taxable_amount=20000, distribution_code="1", is_early=True,
        )
        self.assertEqual(d.taxable, 20000)
        self.assertEqual(d.early_withdrawal_penalty, 2000)

    def test_early_flag_without_code1_no_penalty(self):
        """is_early=True but code != '1' — no penalty."""
        d = RetirementDistribution(
            gross_distribution=10000, taxable_amount=10000,
            distribution_code="7", is_early=True,
        )
        self.assertEqual(d.early_withdrawal_penalty, 0)

    def test_rollover_not_taxable(self):
        """Rollover (code G) — not taxable."""
        d = RetirementDistribution(
            gross_distribution=100000, taxable_amount=100000,
            distribution_code="G",
        )
        self.assertEqual(d.taxable, 0)
        self.assertEqual(d.early_withdrawal_penalty, 0)

    def test_roth_not_taxable(self):
        """Roth distribution — not taxable."""
        d = RetirementDistribution(
            gross_distribution=30000, taxable_amount=30000,
            is_roth=True,
        )
        self.assertEqual(d.taxable, 0)

    def test_taxable_amount_not_determined(self):
        """taxable_amount_not_determined — uses gross_distribution."""
        d = RetirementDistribution(
            gross_distribution=40000, taxable_amount=0,
            taxable_amount_not_determined=True, distribution_code="7",
        )
        self.assertEqual(d.taxable, 40000)

    def test_partial_taxable(self):
        """Partial taxable — e.g. after-tax contributions."""
        d = RetirementDistribution(
            gross_distribution=50000, taxable_amount=35000,
            distribution_code="7",
        )
        self.assertEqual(d.taxable, 35000)

    def test_code_h_rollover_not_taxable(self):
        """Roth rollover (code H) — not taxable."""
        d = RetirementDistribution(
            gross_distribution=25000, taxable_amount=25000,
            distribution_code="H",
        )
        self.assertEqual(d.taxable, 0)

    def test_zero_distribution(self):
        """Zero distribution — no tax, no penalty."""
        d = RetirementDistribution()
        self.assertEqual(d.taxable, 0)
        self.assertEqual(d.early_withdrawal_penalty, 0)


class TestIRAContribution(unittest.TestCase):
    """Test IRAContribution dataclass."""

    def test_basic_contribution(self):
        d = IRAContribution(contributor="filer", contribution_amount=5000)
        self.assertEqual(d.contribution_amount, 5000)
        self.assertFalse(d.age_50_plus)

    def test_catchup_contribution(self):
        d = IRAContribution(contributor="filer", contribution_amount=8000, age_50_plus=True)
        self.assertTrue(d.age_50_plus)


class TestRetirementEngine(unittest.TestCase):
    """Test retirement income integration in compute_tax."""

    def _base_args(self):
        return dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=60000, federal_withheld=8000, ss_wages=60000, medicare_wages=60000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_retirement_adds_to_income(self):
        """1099-R taxable amount adds to other income (line 8)."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(
                payer_name="Fidelity", gross_distribution=30000,
                taxable_amount=30000, distribution_code="7",
            )
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_taxable_amount, 30000)
        self.assertEqual(result.retirement_distributions_count, 1)
        # Total income should include W-2 wages + retirement
        self.assertGreaterEqual(result.line_9_total_income, 90000)

    def test_retirement_withholding(self):
        """Federal withheld from 1099-R reduces tax owed."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(
                gross_distribution=20000, taxable_amount=20000,
                federal_withheld=3000, distribution_code="7",
            )
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_federal_withheld, 3000)
        # Withheld should be included in total withholding
        self.assertGreaterEqual(result.line_25_federal_withheld, 11000)  # 8000 W-2 + 3000 1099-R

    def test_early_withdrawal_penalty_in_tax(self):
        """Early withdrawal penalty adds to total tax."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(
                gross_distribution=10000, taxable_amount=10000,
                distribution_code="1", is_early=True,
            )
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_early_penalty, 1000)

    def test_rollover_no_tax_impact(self):
        """Rollover distributions don't increase taxable income."""
        args = self._base_args()
        base_result = compute_tax(**args)
        args["retirement_distributions"] = [
            RetirementDistribution(
                gross_distribution=100000, distribution_code="G",
            )
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_taxable_amount, 0)
        # Tax should be approximately the same (only W-2)
        self.assertAlmostEqual(result.line_16_tax, base_result.line_16_tax, places=0)

    def test_roth_no_tax_impact(self):
        """Roth distributions don't increase taxable income."""
        args = self._base_args()
        base_result = compute_tax(**args)
        args["retirement_distributions"] = [
            RetirementDistribution(
                gross_distribution=50000, taxable_amount=50000, is_roth=True,
            )
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_taxable_amount, 0)

    def test_multiple_distributions(self):
        """Multiple 1099-R forms aggregate correctly."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(
                payer_name="Fidelity", gross_distribution=20000,
                taxable_amount=20000, federal_withheld=2000,
                distribution_code="7",
            ),
            RetirementDistribution(
                payer_name="Schwab", gross_distribution=15000,
                taxable_amount=10000, federal_withheld=1500,
                distribution_code="7",
            ),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_distributions_count, 2)
        self.assertEqual(result.retirement_gross_distributions, 35000)
        self.assertEqual(result.retirement_taxable_amount, 30000)
        self.assertEqual(result.retirement_federal_withheld, 3500)

    def test_ira_deduction(self):
        """Traditional IRA contribution creates above-the-line deduction."""
        args = self._base_args()
        base_result = compute_tax(**args)
        args["ira_contributions"] = [
            IRAContribution(contributor="filer", contribution_amount=7000),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 7000)
        # AGI should be lower by IRA deduction
        self.assertAlmostEqual(result.line_11_agi, base_result.line_11_agi - 7000, places=0)

    def test_ira_deduction_capped_at_limit(self):
        """IRA contribution over $7,000 is capped."""
        args = self._base_args()
        args["ira_contributions"] = [
            IRAContribution(contributor="filer", contribution_amount=15000),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 7000)

    def test_ira_catchup_50_plus(self):
        """IRA contribution with age 50+ gets $1,000 catchup ($8,000 total)."""
        args = self._base_args()
        args["ira_contributions"] = [
            IRAContribution(contributor="filer", contribution_amount=8000, age_50_plus=True),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 8000)

    def test_ira_catchup_capped(self):
        """IRA contribution over catchup limit is capped at $8,000."""
        args = self._base_args()
        args["ira_contributions"] = [
            IRAContribution(contributor="filer", contribution_amount=12000, age_50_plus=True),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 8000)

    def test_combined_retirement_and_ira(self):
        """1099-R distribution + IRA deduction together."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(
                gross_distribution=25000, taxable_amount=25000,
                federal_withheld=2500, distribution_code="7",
            ),
        ]
        args["ira_contributions"] = [
            IRAContribution(contributor="filer", contribution_amount=7000),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.retirement_taxable_amount, 25000)
        self.assertEqual(result.ira_deduction, 7000)
        # Net income increase from retirement: 25000 - 7000 = 18000

    def test_forms_generated_includes_1099r(self):
        """forms_generated includes '1099-R Summary' when distributions present."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(
                gross_distribution=10000, taxable_amount=10000,
                distribution_code="7",
            ),
        ]
        result = compute_tax(**args)
        self.assertIn("1099-R Summary", result.forms_generated)

    def test_summary_includes_retirement(self):
        """to_summary() includes retirement section."""
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(
                gross_distribution=20000, taxable_amount=20000,
                federal_withheld=2000, distribution_code="7",
            ),
        ]
        result = compute_tax(**args)
        summary = result.to_summary()
        self.assertIn("retirement", summary)
        self.assertEqual(summary["retirement"]["distributions_count"], 1)
        self.assertEqual(summary["retirement"]["taxable_amount"], 20000)

    def test_backward_compat_no_retirement(self):
        """No retirement params — backward compatible, zero defaults."""
        args = self._base_args()
        result = compute_tax(**args)
        self.assertEqual(result.retirement_distributions_count, 0)
        self.assertEqual(result.retirement_taxable_amount, 0)
        self.assertEqual(result.ira_deduction, 0)

    def test_2024_ira_limit(self):
        """2024 tax year uses same $7,000 IRA limit."""
        args = self._base_args()
        args["tax_year"] = 2024
        args["ira_contributions"] = [
            IRAContribution(contributor="filer", contribution_amount=7000),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 7000)

    def test_mfj_two_ira_contributions(self):
        """MFJ — both spouses can contribute to IRA."""
        args = self._base_args()
        args["filing_status"] = "mfj"
        args["ira_contributions"] = [
            IRAContribution(contributor="filer", contribution_amount=7000),
            IRAContribution(contributor="spouse", contribution_amount=7000),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ira_deduction, 14000)


if __name__ == "__main__":
    unittest.main()
