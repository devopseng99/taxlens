"""Wave 44 — Social Security Benefits (SSA-1099) taxability tests."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    SocialSecurityBenefit, compute_tax,
    W2Income, AdditionalIncome, Deductions, Payments, PersonInfo,
)


class TestSocialSecurityBenefit(unittest.TestCase):
    """Test SocialSecurityBenefit dataclass."""

    def test_basic_benefit(self):
        b = SocialSecurityBenefit(recipient="filer", gross_benefits=24000)
        self.assertEqual(b.gross_benefits, 24000)
        self.assertEqual(b.federal_withheld, 0)

    def test_with_withholding(self):
        b = SocialSecurityBenefit(gross_benefits=24000, federal_withheld=2400)
        self.assertEqual(b.federal_withheld, 2400)

    def test_defaults(self):
        b = SocialSecurityBenefit()
        self.assertEqual(b.recipient, "filer")
        self.assertEqual(b.gross_benefits, 0)
        self.assertEqual(b.federal_withheld, 0)


class TestSSTaxability(unittest.TestCase):
    """Test Social Security benefits IRC §86 taxability formula."""

    def _base_args(self, wages=0, filing_status="single"):
        return dict(
            filing_status=filing_status,
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=wages, federal_withheld=0, ss_wages=wages, medicare_wages=wages)] if wages > 0 else [],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )

    def test_zero_taxable_below_base_single(self):
        """Single filer with SS $20K + no other income: provisional=$10K < $25K → 0% taxable."""
        args = self._base_args()
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=20000)]
        result = compute_tax(**args)
        self.assertEqual(result.ss_gross_benefits, 20000)
        self.assertEqual(result.ss_taxable_amount, 0)
        self.assertEqual(result.ss_taxable_pct, 0)

    def test_50_pct_between_thresholds_single(self):
        """Single: wages $20K + SS $20K → provisional $30K (between $25K and $34K) → up to 50%."""
        args = self._base_args(wages=20000)
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=20000)]
        result = compute_tax(**args)
        # Provisional = 20000 + 10000 = 30000
        self.assertEqual(result.ss_provisional_income, 30000)
        # taxable = min(20000*0.5, (30000-25000)*0.5) = min(10000, 2500) = 2500
        self.assertEqual(result.ss_taxable_amount, 2500)
        self.assertAlmostEqual(result.ss_taxable_pct, 0.125)

    def test_85_pct_above_upper_single(self):
        """Single: wages $60K + SS $24K → provisional $72K (above $34K) → up to 85%."""
        args = self._base_args(wages=60000)
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=24000)]
        result = compute_tax(**args)
        # Provisional = 60000 + 12000 = 72000
        self.assertEqual(result.ss_provisional_income, 72000)
        # fifty_pct = min(12000, (34000-25000)*0.5) = min(12000, 4500) = 4500
        # eighty_five_pct = (72000-34000)*0.85 = 32300
        # total = min(4500+32300, 24000*0.85) = min(36800, 20400) = 20400
        self.assertEqual(result.ss_taxable_amount, 20400)
        self.assertAlmostEqual(result.ss_taxable_pct, 0.85)

    def test_mfj_higher_thresholds(self):
        """MFJ: wages $20K + SS $24K → provisional $32K = base threshold → 0% taxable."""
        args = self._base_args(wages=20000, filing_status="mfj")
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=24000)]
        result = compute_tax(**args)
        # Provisional = 20000 + 12000 = 32000 = base threshold for MFJ
        self.assertEqual(result.ss_provisional_income, 32000)
        self.assertEqual(result.ss_taxable_amount, 0)

    def test_mfj_between_thresholds(self):
        """MFJ: wages $30K + SS $24K → provisional $42K (between $32K and $44K)."""
        args = self._base_args(wages=30000, filing_status="mfj")
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=24000)]
        result = compute_tax(**args)
        # Provisional = 30000 + 12000 = 42000
        # taxable = min(12000, (42000-32000)*0.5) = min(12000, 5000) = 5000
        self.assertEqual(result.ss_taxable_amount, 5000)

    def test_mfs_always_taxable(self):
        """MFS: thresholds are $0 — SS is almost always taxable."""
        args = self._base_args(wages=10000, filing_status="mfs")
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=12000)]
        result = compute_tax(**args)
        # Provisional = 10000 + 6000 = 16000 > upper ($0)
        # All above upper → up to 85%
        self.assertGreater(result.ss_taxable_amount, 0)
        self.assertLessEqual(result.ss_taxable_pct, 0.85)

    def test_ss_adds_to_total_income(self):
        """Taxable SS benefits are included in line 9 total income."""
        args = self._base_args(wages=50000)
        base_result = compute_tax(**args)
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=24000)]
        result = compute_tax(**args)
        # Total income should increase by the taxable SS amount
        self.assertGreater(result.line_9_total_income, base_result.line_9_total_income)
        increase = result.line_9_total_income - base_result.line_9_total_income
        self.assertAlmostEqual(increase, result.ss_taxable_amount, places=2)

    def test_ss_withholding_reduces_tax_owed(self):
        """SS withholding (W-4V) is included in line 25 federal withheld."""
        args = self._base_args(wages=50000)
        args["w2s"][0].federal_withheld = 5000
        args["social_security_benefits"] = [
            SocialSecurityBenefit(gross_benefits=24000, federal_withheld=2400),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ss_federal_withheld, 2400)
        self.assertGreaterEqual(result.line_25_federal_withheld, 7400)  # 5000 W-2 + 2400 SS

    def test_multiple_ss_benefits(self):
        """Multiple SSA-1099 forms (filer + spouse) aggregate correctly."""
        args = self._base_args(wages=40000, filing_status="mfj")
        args["social_security_benefits"] = [
            SocialSecurityBenefit(recipient="filer", gross_benefits=18000, federal_withheld=1800),
            SocialSecurityBenefit(recipient="spouse", gross_benefits=12000, federal_withheld=1200),
        ]
        result = compute_tax(**args)
        self.assertEqual(result.ss_gross_benefits, 30000)
        self.assertEqual(result.ss_federal_withheld, 3000)

    def test_forms_generated_includes_ssa(self):
        """forms_generated includes 'SSA-1099 Summary' when SS benefits present."""
        args = self._base_args(wages=30000)
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=20000)]
        result = compute_tax(**args)
        self.assertIn("SSA-1099 Summary", result.forms_generated)

    def test_summary_includes_social_security(self):
        """to_summary() includes social_security section."""
        args = self._base_args(wages=40000)
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=24000)]
        result = compute_tax(**args)
        summary = result.to_summary()
        self.assertIn("social_security", summary)
        self.assertEqual(summary["social_security"]["gross_benefits"], 24000)

    def test_backward_compat_no_ss(self):
        """No SS params — backward compatible, zero defaults."""
        args = self._base_args(wages=50000)
        result = compute_tax(**args)
        self.assertEqual(result.ss_gross_benefits, 0)
        self.assertEqual(result.ss_taxable_amount, 0)
        self.assertEqual(result.ss_taxable_pct, 0)

    def test_hoh_uses_single_thresholds(self):
        """Head of household uses same thresholds as single ($25K/$34K)."""
        args = self._base_args(wages=20000, filing_status="hoh")
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=20000)]
        result = compute_tax(**args)
        # Same as single test case
        self.assertEqual(result.ss_provisional_income, 30000)
        self.assertEqual(result.ss_taxable_amount, 2500)

    def test_max_85_pct_cap(self):
        """Taxable amount never exceeds 85% of benefits regardless of income."""
        args = self._base_args(wages=200000)
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=30000)]
        result = compute_tax(**args)
        max_taxable = 30000 * 0.85
        self.assertAlmostEqual(result.ss_taxable_amount, max_taxable, places=2)
        self.assertAlmostEqual(result.ss_taxable_pct, 0.85)

    def test_combined_with_retirement_distributions(self):
        """SS benefits + 1099-R distributions together (common retiree scenario)."""
        from tax_engine import RetirementDistribution
        args = self._base_args()
        args["retirement_distributions"] = [
            RetirementDistribution(gross_distribution=30000, taxable_amount=30000, distribution_code="7"),
        ]
        args["social_security_benefits"] = [
            SocialSecurityBenefit(gross_benefits=24000),
        ]
        result = compute_tax(**args)
        # Provisional income includes retirement taxable as other income
        self.assertEqual(result.ss_provisional_income, 30000 + 12000)  # retirement + 50% SS
        self.assertGreater(result.ss_taxable_amount, 0)
        # Both are reflected in total income
        self.assertGreater(result.line_9_total_income, 30000 + result.ss_taxable_amount - 1)

    def test_2024_tax_year(self):
        """2024 tax year uses same SS thresholds (statutory, not indexed)."""
        args = self._base_args(wages=50000)
        args["tax_year"] = 2024
        args["social_security_benefits"] = [SocialSecurityBenefit(gross_benefits=24000)]
        result = compute_tax(**args)
        self.assertGreater(result.ss_taxable_amount, 0)


if __name__ == "__main__":
    unittest.main()
