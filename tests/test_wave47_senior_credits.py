"""Wave 47 — Additional Standard Deduction (Age 65+/Blind) + REST API Credit Fields."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, W2Income, AdditionalIncome, Deductions, Payments, PersonInfo,
    EducationExpense, DependentCareExpense, RetirementContribution,
)


class TestAdditionalStandardDeduction(unittest.TestCase):
    """Test additional standard deduction for age 65+ and blind filers."""

    def _base_args(self, wages=50000, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=5000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_no_additional_default(self):
        """Default: no additional deduction."""
        args = self._base_args()
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 0)
        self.assertEqual(result.standard_deduction, 15000)  # 2025 single

    def test_single_age_65(self):
        """Single filer 65+ gets $2,000 additional (2025)."""
        args = self._base_args()
        args["filer_age_65_plus"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 2000)
        self.assertEqual(result.standard_deduction, 17000)

    def test_single_blind(self):
        """Single blind filer gets $2,000 additional (2025)."""
        args = self._base_args()
        args["filer_is_blind"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 2000)
        self.assertEqual(result.standard_deduction, 17000)

    def test_single_65_and_blind(self):
        """Single filer who is both 65+ and blind gets $4,000 (2x$2,000)."""
        args = self._base_args()
        args["filer_age_65_plus"] = True
        args["filer_is_blind"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 4000)
        self.assertEqual(result.standard_deduction, 19000)

    def test_mfj_one_spouse_65(self):
        """MFJ: one spouse 65+ gets $1,600 additional (2025 married rate)."""
        args = self._base_args(filing_status="mfj")
        args["filer_age_65_plus"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 1600)
        self.assertEqual(result.standard_deduction, 31600)  # 30000 + 1600

    def test_mfj_both_65(self):
        """MFJ: both spouses 65+ gets $3,200 (2x$1,600)."""
        args = self._base_args(filing_status="mfj")
        args["filer_age_65_plus"] = True
        args["spouse_age_65_plus"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 3200)
        self.assertEqual(result.standard_deduction, 33200)

    def test_mfj_both_65_one_blind(self):
        """MFJ: both 65+ and one blind = 3 additional items = $4,800."""
        args = self._base_args(filing_status="mfj")
        args["filer_age_65_plus"] = True
        args["filer_is_blind"] = True
        args["spouse_age_65_plus"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 4800)

    def test_mfj_all_four(self):
        """MFJ: both 65+ and both blind = 4 items = $6,400."""
        args = self._base_args(filing_status="mfj")
        args["filer_age_65_plus"] = True
        args["filer_is_blind"] = True
        args["spouse_age_65_plus"] = True
        args["spouse_is_blind"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 6400)
        self.assertEqual(result.standard_deduction, 36400)

    def test_hoh_uses_single_rate(self):
        """HoH gets single rate ($2,000) not married rate."""
        args = self._base_args(filing_status="hoh")
        args["filer_age_65_plus"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 2000)

    def test_mfs_uses_married_rate(self):
        """MFS gets married rate ($1,600)."""
        args = self._base_args(filing_status="mfs")
        args["filer_age_65_plus"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 1600)

    def test_reduces_tax(self):
        """Additional deduction should reduce taxable income and tax."""
        args = self._base_args(wages=50000)
        base_result = compute_tax(**args)
        args["filer_age_65_plus"] = True
        senior_result = compute_tax(**args)
        # $2K more deduction → lower taxable income → lower tax
        self.assertLess(senior_result.line_15_taxable_income, base_result.line_15_taxable_income)
        self.assertLess(senior_result.line_24_total_tax, base_result.line_24_total_tax)

    def test_2024_amounts(self):
        """2024 uses different additional amounts ($1,950/$1,550)."""
        args = self._base_args()
        args["filer_age_65_plus"] = True
        args["tax_year"] = 2024
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 1950)

    def test_spouse_flags_ignored_for_single(self):
        """Spouse flags have no effect on single filers."""
        args = self._base_args()
        args["spouse_age_65_plus"] = True
        args["spouse_is_blind"] = True
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 0)

    def test_itemized_still_wins_if_higher(self):
        """If itemized > standard+additional, itemized is still chosen."""
        args = self._base_args(wages=100000)
        args["filer_age_65_plus"] = True
        args["deductions"] = Deductions(
            mortgage_interest=15000, property_tax=8000, state_income_tax_paid=10000,
            charitable_cash=5000,
        )
        result = compute_tax(**args)
        # Standard = 15000 + 2000 = 17000
        # Itemized = 15000 + 10000(SALT cap) + 5000 = 30000
        self.assertEqual(result.deduction_type, "itemized")


class TestEducationCreditViaAPI(unittest.TestCase):
    """Test that education credits are now reachable via REST API path."""

    def _base_args(self, wages=50000):
        return dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=5000, ss_wages=wages, medicare_wages=wages)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_aotc_via_engine(self):
        """AOTC works when education_expenses param is provided."""
        args = self._base_args()
        args["education_expenses"] = [
            EducationExpense(student_name="Student", qualified_expenses=4000, credit_type="aotc"),
        ]
        result = compute_tax(**args)
        # AOTC $2,500 = $1,500 nonrefundable + $1,000 refundable
        self.assertEqual(result.education_credit, 1500)  # nonrefundable portion
        self.assertEqual(result.education_credit_refundable, 1000)  # 40% refundable

    def test_cdcc_via_engine(self):
        """CDCC works when dependent_care_expenses param is provided."""
        args = self._base_args(wages=30000)
        args["dependent_care_expenses"] = [
            DependentCareExpense(dependent_name="Child", care_expenses=3000),
        ]
        result = compute_tax(**args)
        self.assertGreater(result.cdcc, 0)

    def test_savers_credit_via_engine(self):
        """Saver's Credit works when retirement_contributions param is provided."""
        args = self._base_args(wages=25000)
        args["retirement_contributions"] = [
            RetirementContribution(contributor="filer", contribution_amount=2000),
        ]
        result = compute_tax(**args)
        self.assertGreater(result.savers_credit, 0)


class TestBackwardCompat(unittest.TestCase):
    """Backward compatibility — new params default to no effect."""

    def test_no_age_blind_flags(self):
        args = dict(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=50000, federal_withheld=5000, ss_wages=50000, medicare_wages=50000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        result = compute_tax(**args)
        self.assertEqual(result.additional_standard_deduction, 0)
        self.assertEqual(result.standard_deduction, 15000)


if __name__ == "__main__":
    unittest.main()
