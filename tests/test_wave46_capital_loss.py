"""Wave 46 — Capital Loss Limitation (IRC §1211) tests."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, W2Income, AdditionalIncome, Deductions, Payments, PersonInfo,
    CapitalTransaction,
)


class TestCapitalLossLimitation(unittest.TestCase):
    """Test IRC §1211(b) $3,000/$1,500 capital loss limitation."""

    def _base_args(self, wages=60000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=8000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_net_gain_no_limitation(self):
        """Net capital gains are not limited."""
        args = self._base_args()
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="AAPL", proceeds=15000, cost_basis=10000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, 5000)
        self.assertEqual(result.capital_loss_carryforward, 0)
        self.assertEqual(result.capital_loss_limited, 0)

    def test_small_loss_no_limitation(self):
        """Net capital loss under $3,000 is fully deductible."""
        args = self._base_args()
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="TSLA", proceeds=8000, cost_basis=10000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -2000)
        self.assertEqual(result.capital_loss_carryforward, 0)
        self.assertEqual(result.capital_loss_limited, 0)

    def test_exactly_3000_loss(self):
        """$3,000 net loss is exactly at the limit — no carryforward."""
        args = self._base_args()
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="META", proceeds=7000, cost_basis=10000, is_long_term=False),
            ]
        )
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertEqual(result.capital_loss_carryforward, 0)

    def test_large_loss_capped_at_3000(self):
        """$50,000 net loss is capped at $3,000 deduction, $47,000 carried forward."""
        args = self._base_args()
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="NVDA", proceeds=10000, cost_basis=60000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertEqual(result.capital_loss_carryforward, 47000)
        # sched_d_net_gain still records the true net
        self.assertEqual(result.sched_d_net_gain, -50000)

    def test_mfs_capped_at_1500(self):
        """MFS filers get $1,500 limit instead of $3,000."""
        args = self._base_args(filing_status="mfs")
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="AMZN", proceeds=5000, cost_basis=15000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -1500)
        self.assertEqual(result.capital_loss_carryforward, 8500)

    def test_mfj_gets_3000_limit(self):
        """MFJ filers get the standard $3,000 limit."""
        args = self._base_args(filing_status="mfj")
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="GOOG", proceeds=2000, cost_basis=20000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertEqual(result.capital_loss_carryforward, 15000)

    def test_mixed_gains_and_losses(self):
        """$10K gain + $20K loss = -$10K net → limited to -$3K, carry $7K."""
        args = self._base_args()
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="AAPL", proceeds=15000, cost_basis=5000, is_long_term=True),
                CapitalTransaction(description="TSLA", proceeds=5000, cost_basis=25000, is_long_term=False),
            ]
        )
        result = compute_tax(**args)
        self.assertEqual(result.sched_d_net_gain, -10000)
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertEqual(result.capital_loss_carryforward, 7000)

    def test_loss_reduces_total_income(self):
        """Capital loss deduction reduces line 9 total income."""
        args = self._base_args(wages=60000)
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="X", proceeds=1000, cost_basis=50000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        # $60K wages - $3K capital loss = $57K
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertAlmostEqual(result.line_9_total_income, 57000, places=0)


class TestCapitalLossCarryover(unittest.TestCase):
    """Test prior-year capital loss carryover input."""

    def _base_args(self, wages=60000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=8000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_carryover_with_no_current_transactions(self):
        """$5K prior-year carryover, no current capital transactions."""
        args = self._base_args()
        args["capital_loss_carryover"] = 5000
        result = compute_tax(**args)
        # $5K carryover → net = -$5K → limited to -$3K, carry $2K
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertEqual(result.capital_loss_carryforward, 2000)
        self.assertEqual(result.capital_loss_carryover_used, 5000)

    def test_carryover_under_limit(self):
        """$2K prior-year carryover — fully deductible."""
        args = self._base_args()
        args["capital_loss_carryover"] = 2000
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -2000)
        self.assertEqual(result.capital_loss_carryforward, 0)

    def test_carryover_offset_by_gains(self):
        """$10K carryover + $8K current gain = -$2K net → fully deductible."""
        args = self._base_args()
        args["capital_loss_carryover"] = 10000
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="MSFT", proceeds=18000, cost_basis=10000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        # $8K gain - $10K carryover = -$2K → within limit
        self.assertEqual(result.sched_d_net_gain, -2000)
        self.assertEqual(result.line_7_capital_gain_loss, -2000)
        self.assertEqual(result.capital_loss_carryforward, 0)

    def test_carryover_with_gains_exceeding(self):
        """$5K carryover + $12K gain = $7K net gain → no limitation needed."""
        args = self._base_args()
        args["capital_loss_carryover"] = 5000
        args["additional"] = AdditionalIncome(
            capital_transactions=[
                CapitalTransaction(description="NVDA", proceeds=22000, cost_basis=10000, is_long_term=True),
            ]
        )
        result = compute_tax(**args)
        # $12K gain - $5K carryover = $7K net gain
        self.assertEqual(result.line_7_capital_gain_loss, 7000)
        self.assertEqual(result.capital_loss_carryforward, 0)

    def test_large_carryover_still_limited(self):
        """$100K carryover → limited to -$3K, $97K carried forward."""
        args = self._base_args()
        args["capital_loss_carryover"] = 100000
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertEqual(result.capital_loss_carryforward, 97000)

    def test_zero_carryover_backward_compat(self):
        """Default capital_loss_carryover=0 — backward compatible."""
        args = self._base_args()
        result = compute_tax(**args)
        self.assertEqual(result.capital_loss_carryover_used, 0)
        self.assertEqual(result.capital_loss_carryforward, 0)
        self.assertEqual(result.line_7_capital_gain_loss, 0)


class TestCapitalLossSummary(unittest.TestCase):
    """Test summary output for capital loss limitation."""

    def test_summary_includes_carryforward(self):
        args = dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=50000, federal_withheld=5000, ss_wages=50000, medicare_wages=50000)],
            additional=AdditionalIncome(
                capital_transactions=[
                    CapitalTransaction(description="X", proceeds=1000, cost_basis=20000, is_long_term=True),
                ]
            ),
            deductions=Deductions(),
            payments=Payments(),
        )
        result = compute_tax(**args)
        summary = result.to_summary()
        self.assertEqual(summary["capital_loss_carryforward"], 16000)

    def test_summary_no_carryforward_when_gain(self):
        args = dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=50000, federal_withheld=5000, ss_wages=50000, medicare_wages=50000)],
            additional=AdditionalIncome(
                capital_transactions=[
                    CapitalTransaction(description="X", proceeds=20000, cost_basis=10000, is_long_term=True),
                ]
            ),
            deductions=Deductions(),
            payments=Payments(),
        )
        result = compute_tax(**args)
        summary = result.to_summary()
        self.assertIsNone(summary.get("capital_loss_carryforward"))


class TestCapitalLoss2024(unittest.TestCase):
    """Test capital loss limitation works with 2024 tax year."""

    def test_2024_same_limit(self):
        """$3K limit is statutory, same across years."""
        args = dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=60000, federal_withheld=8000, ss_wages=60000, medicare_wages=60000)],
            additional=AdditionalIncome(
                capital_transactions=[
                    CapitalTransaction(description="X", proceeds=5000, cost_basis=25000, is_long_term=True),
                ]
            ),
            deductions=Deductions(),
            payments=Payments(),
            tax_year=2024,
        )
        result = compute_tax(**args)
        self.assertEqual(result.line_7_capital_gain_loss, -3000)
        self.assertEqual(result.capital_loss_carryforward, 17000)


if __name__ == "__main__":
    unittest.main()
