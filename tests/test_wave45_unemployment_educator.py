"""Wave 45 — Unemployment Compensation, Educator Expenses, Alimony tests."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    UnemploymentCompensation, compute_tax,
    W2Income, AdditionalIncome, Deductions, Payments, PersonInfo,
)


class TestUnemploymentCompensation(unittest.TestCase):
    """Test UnemploymentCompensation dataclass."""

    def test_basic(self):
        u = UnemploymentCompensation(state="IL", compensation=12000, federal_withheld=1200)
        self.assertEqual(u.compensation, 12000)
        self.assertEqual(u.federal_withheld, 1200)

    def test_defaults(self):
        u = UnemploymentCompensation()
        self.assertEqual(u.state, "")
        self.assertEqual(u.compensation, 0)


class TestUnemploymentEngine(unittest.TestCase):
    """Test unemployment compensation integration in compute_tax."""

    def _base_args(self, wages=0, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=0, ss_wages=wages, medicare_wages=wages)] if wages > 0 else [],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_unemployment_fully_taxable(self):
        """Unemployment compensation is fully taxable (added to other income)."""
        args = self._base_args(wages=40000)
        args["unemployment_benefits"] = [
            UnemploymentCompensation(state="IL", compensation=15000),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.unemployment_compensation, 15000)
        self.assertGreaterEqual(result.line_9_total_income, 55000)

    def test_unemployment_withholding(self):
        """Federal withholding from unemployment reduces tax owed."""
        args = self._base_args(wages=40000)
        args["w2s"][0].federal_withheld = 5000
        args["unemployment_benefits"] = [
            UnemploymentCompensation(compensation=15000, federal_withheld=1500),
        ]
        result = compute_tax(**args)
        self.assertGreaterEqual(result.line_25_federal_withheld, 6500)

    def test_multiple_unemployment(self):
        """Multiple 1099-G forms aggregate correctly."""
        args = self._base_args(wages=30000)
        args["unemployment_benefits"] = [
            UnemploymentCompensation(state="IL", compensation=8000, federal_withheld=800),
            UnemploymentCompensation(state="CA", compensation=5000, federal_withheld=500),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.unemployment_compensation, 13000)
        self.assertEqual(result.unemployment_federal_withheld, 1300)

    def test_forms_generated(self):
        args = self._base_args()
        args["unemployment_benefits"] = [UnemploymentCompensation(compensation=10000)]
        result = compute_tax(**args)
        self.assertIn("1099-G Summary", result.forms_generated)

    def test_summary_includes_unemployment(self):
        args = self._base_args()
        args["unemployment_benefits"] = [UnemploymentCompensation(compensation=10000)]
        result = compute_tax(**args)
        summary = result.to_summary()
        self.assertIn("unemployment", summary)
        self.assertEqual(summary["unemployment"]["compensation"], 10000)

    def test_backward_compat(self):
        """No unemployment params — backward compatible."""
        args = self._base_args(wages=50000)
        result = compute_tax(**args)
        self.assertEqual(result.unemployment_compensation, 0)


class TestEducatorExpenses(unittest.TestCase):
    """Test educator expense deduction."""

    def _base_args(self, wages=50000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=5000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_educator_deduction_basic(self):
        """Educator expense deduction reduces AGI."""
        args = self._base_args()
        base_result = compute_tax(**args)
        args["educator_expenses"] = 250.0
        result = compute_tax(**args)
        self.assertEqual(result.educator_expense_deduction, 250)
        self.assertAlmostEqual(result.line_11_agi, base_result.line_11_agi - 250, places=0)

    def test_educator_capped_at_300(self):
        """Educator expense is capped at $300 for single filer."""
        args = self._base_args()
        args["educator_expenses"] = 500.0
        result = compute_tax(**args)
        self.assertEqual(result.educator_expense_deduction, 300)

    def test_educator_mfj_600_cap(self):
        """MFJ: both spouses can be educators → $600 cap."""
        args = self._base_args(filing_status="mfj")
        args["educator_expenses"] = 550.0
        result = compute_tax(**args)
        self.assertEqual(result.educator_expense_deduction, 550)

    def test_educator_mfj_capped_at_600(self):
        """MFJ: total capped at $600."""
        args = self._base_args(filing_status="mfj")
        args["educator_expenses"] = 800.0
        result = compute_tax(**args)
        self.assertEqual(result.educator_expense_deduction, 600)

    def test_educator_zero(self):
        """Zero educator expenses → no deduction."""
        args = self._base_args()
        args["educator_expenses"] = 0
        result = compute_tax(**args)
        self.assertEqual(result.educator_expense_deduction, 0)

    def test_summary_includes_educator(self):
        args = self._base_args()
        args["educator_expenses"] = 300.0
        result = compute_tax(**args)
        summary = result.to_summary()
        self.assertEqual(summary["educator_expense_deduction"], 300)


class TestAlimony(unittest.TestCase):
    """Test alimony (pre-2019 divorce agreements)."""

    def _base_args(self, wages=60000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=8000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_alimony_paid_reduces_agi(self):
        """Alimony paid is an above-the-line deduction."""
        args = self._base_args()
        base_result = compute_tax(**args)
        args["alimony_paid"] = 12000.0
        result = compute_tax(**args)
        self.assertEqual(result.alimony_paid, 12000)
        self.assertAlmostEqual(result.line_11_agi, base_result.line_11_agi - 12000, places=0)

    def test_alimony_received_increases_income(self):
        """Alimony received is taxable income."""
        args = self._base_args()
        base_result = compute_tax(**args)
        args["alimony_received"] = 18000.0
        result = compute_tax(**args)
        self.assertEqual(result.alimony_received, 18000)
        self.assertGreater(result.line_9_total_income, base_result.line_9_total_income)

    def test_alimony_both_paid_and_received(self):
        """Can have both alimony paid and received (different divorce agreements)."""
        args = self._base_args()
        args["alimony_paid"] = 12000.0
        args["alimony_received"] = 8000.0
        result = compute_tax(**args)
        self.assertEqual(result.alimony_paid, 12000)
        self.assertEqual(result.alimony_received, 8000)

    def test_summary_includes_alimony(self):
        args = self._base_args()
        args["alimony_paid"] = 10000.0
        result = compute_tax(**args)
        summary = result.to_summary()
        self.assertEqual(summary["alimony_paid"], 10000)

    def test_backward_compat(self):
        """No alimony params — backward compatible."""
        args = self._base_args()
        result = compute_tax(**args)
        self.assertEqual(result.alimony_paid, 0)
        self.assertEqual(result.alimony_received, 0)


if __name__ == "__main__":
    unittest.main()
