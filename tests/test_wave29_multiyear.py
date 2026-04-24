"""Unit tests for Wave 29 — Multi-Year Tax Config (2024 + 2025).

Tests that the engine produces different results for 2024 vs 2025 due to
inflation-adjusted brackets, deductions, and credits.

Run: PYTHONPATH=app pytest tests/test_wave29_multiyear.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    BusinessIncome, compute_tax,
)
from tax_config import (
    get_year_config, SUPPORTED_TAX_YEARS, TAX_YEAR,
    SINGLE, MFJ, HOH, MFS,
)


def make_filer(**kw):
    defaults = dict(first_name="Test", last_name="User", ssn="123-45-6789",
                    address_city="Chicago", address_state="IL", address_zip="60601")
    defaults.update(kw)
    return PersonInfo(**defaults)


def compute(wages=50000, filing_status="single", tax_year=2025, **kw):
    """Helper with tax_year support."""
    w2s = kw.pop("w2s", None)
    if w2s is None:
        w2s = [W2Income(wages=wages, federal_withheld=wages * 0.15,
                        ss_wages=wages, medicare_wages=wages)]
    return compute_tax(
        filing_status=filing_status,
        filer=make_filer(),
        w2s=w2s,
        additional=kw.pop("additional", AdditionalIncome()),
        deductions=kw.pop("deductions", Deductions()),
        payments=kw.pop("payments", Payments()),
        tax_year=tax_year,
        **kw,
    )


# ---------------------------------------------------------------------------
# get_year_config tests
# ---------------------------------------------------------------------------
class TestYearConfig:
    def test_supported_years(self):
        assert 2024 in SUPPORTED_TAX_YEARS
        assert 2025 in SUPPORTED_TAX_YEARS

    def test_default_year_is_2025(self):
        assert TAX_YEAR == 2025

    def test_get_2025_config(self):
        c = get_year_config(2025)
        assert c.STANDARD_DEDUCTION[SINGLE] == 15_000
        assert c.STANDARD_DEDUCTION[MFJ] == 30_000
        assert c.SS_WAGE_BASE == 176_100

    def test_get_2024_config(self):
        c = get_year_config(2024)
        assert c.STANDARD_DEDUCTION[SINGLE] == 14_600
        assert c.STANDARD_DEDUCTION[MFJ] == 29_200
        assert c.SS_WAGE_BASE == 168_600

    def test_unsupported_year_raises(self):
        with pytest.raises(ValueError, match="Unsupported tax year"):
            get_year_config(2023)

    def test_fixed_rates_same_both_years(self):
        c24 = get_year_config(2024)
        c25 = get_year_config(2025)
        assert c24.SS_RATE == c25.SS_RATE == 0.062
        assert c24.NIIT_RATE == c25.NIIT_RATE == 0.038
        assert c24.SE_SS_RATE == c25.SE_SS_RATE == 0.124

    def test_brackets_differ_between_years(self):
        c24 = get_year_config(2024)
        c25 = get_year_config(2025)
        # 10% bracket is wider in 2025 ($11,925 vs $11,600 for single)
        assert c24.FEDERAL_BRACKETS[SINGLE][0][0] == 11_600
        assert c25.FEDERAL_BRACKETS[SINGLE][0][0] == 11_925

    def test_amt_exemption_differs(self):
        c24 = get_year_config(2024)
        c25 = get_year_config(2025)
        assert c24.AMT_EXEMPTION[SINGLE] == 85_700
        assert c25.AMT_EXEMPTION[SINGLE] == 88_100

    def test_eitc_max_differs(self):
        c24 = get_year_config(2024)
        c25 = get_year_config(2025)
        assert c24.EITC_MAX_CREDIT[0] == 632
        assert c25.EITC_MAX_CREDIT[0] == 649

    def test_il_exemption_differs(self):
        c24 = get_year_config(2024)
        c25 = get_year_config(2025)
        assert c24.IL_PERSONAL_EXEMPTION == 2_625
        assert c25.IL_PERSONAL_EXEMPTION == 2_775


# ---------------------------------------------------------------------------
# compute_tax with tax_year parameter
# ---------------------------------------------------------------------------
class TestComputeTaxMultiYear:
    def test_default_year_is_2025(self):
        r = compute(wages=50000)
        assert r.tax_year == 2025

    def test_explicit_2024(self):
        r = compute(wages=50000, tax_year=2024)
        assert r.tax_year == 2024

    def test_unsupported_year_raises(self):
        with pytest.raises(ValueError, match="Unsupported tax year"):
            compute(wages=50000, tax_year=2023)

    def test_standard_deduction_differs(self):
        """2024 single standard deduction = $14,600 vs 2025 = $15,000."""
        r24 = compute(wages=50000, tax_year=2024)
        r25 = compute(wages=50000, tax_year=2025)
        assert r24.standard_deduction == 14_600
        assert r25.standard_deduction == 15_000

    def test_taxable_income_differs(self):
        """Higher standard deduction in 2025 → lower taxable income."""
        r24 = compute(wages=50000, tax_year=2024)
        r25 = compute(wages=50000, tax_year=2025)
        assert r24.line_15_taxable_income > r25.line_15_taxable_income
        assert r24.line_15_taxable_income == 50000 - 14_600  # $35,400
        assert r25.line_15_taxable_income == 50000 - 15_000  # $35,000

    def test_tax_amount_differs(self):
        """Same wages, different tax due to bracket differences."""
        r24 = compute(wages=80000, tax_year=2024)
        r25 = compute(wages=80000, tax_year=2025)
        # Both have different taxable income and different brackets
        assert r24.line_16_tax != r25.line_16_tax

    def test_mfj_deduction_differs(self):
        r24 = compute(wages=80000, filing_status="mfj", tax_year=2024)
        r25 = compute(wages=80000, filing_status="mfj", tax_year=2025)
        assert r24.standard_deduction == 29_200
        assert r25.standard_deduction == 30_000


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------
class TestBackwardCompat:
    def test_no_tax_year_param_uses_2025(self):
        """Calling compute_tax without tax_year still uses 2025 defaults."""
        r = compute_tax(
            filing_status="single",
            filer=make_filer(),
            w2s=[W2Income(wages=50000, federal_withheld=7500,
                          ss_wages=50000, medicare_wages=50000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        assert r.tax_year == 2025
        assert r.standard_deduction == 15_000

    def test_existing_tests_unaffected(self):
        """Module-level constants still export 2025 values."""
        from tax_config import FEDERAL_BRACKETS, STANDARD_DEDUCTION, SS_WAGE_BASE
        assert STANDARD_DEDUCTION[SINGLE] == 15_000
        assert SS_WAGE_BASE == 176_100
        assert FEDERAL_BRACKETS[SINGLE][0][0] == 11_925


# ---------------------------------------------------------------------------
# Year-specific credit differences
# ---------------------------------------------------------------------------
class TestYearSpecificCredits:
    def test_eitc_differs_between_years(self):
        """EITC max credit differs: $632 (2024) vs $649 (2025) for 0 children.
        At $8,300 wages (above 2024's earned_amount $8,260 but below 2025's $8,490),
        2024 is capped at max credit while 2025 is still in phase-in."""
        r24 = compute(wages=8300, tax_year=2024)
        r25 = compute(wages=8300, tax_year=2025)
        assert r24.eitc > 0
        assert r25.eitc > 0
        # 2024: min(8300*0.0765, 632) = min(634.95, 632) = 632 (capped)
        # 2025: min(8300*0.0765, 649) = min(634.95, 649) = 634.95 (still in phase-in)
        assert r24.eitc == 632.0
        assert r25.eitc == pytest.approx(634.95, abs=0.01)

    def test_ss_wage_base_differs(self):
        """SE tax SS portion uses different wage base: $168,600 (2024) vs $176,100 (2025)."""
        biz = [BusinessIncome(business_name="Consulting", gross_receipts=200000)]
        r24 = compute(wages=0, tax_year=2024, w2s=[], businesses=biz)
        r25 = compute(wages=0, tax_year=2025, w2s=[], businesses=biz)
        # Different SS wage base → different SE tax
        assert r24.sched_se_ss_tax != r25.sched_se_ss_tax

    def test_qbi_limit_differs(self):
        """QBI income limit: $182,100 (2024) vs $191,950 (2025) for single.
        Need tentative_taxable (AGI - deduction) between $182,100 and $191,950.
        At $230K gross, AGI ≈ $213K, tentative ≈ $198K (2024) / $198K (2025).
        Both above limits but 2024 is further into phase-out."""
        biz = [BusinessIncome(business_name="Consulting", gross_receipts=230000)]
        r24 = compute(wages=0, tax_year=2024, w2s=[], businesses=biz)
        r25 = compute(wages=0, tax_year=2025, w2s=[], businesses=biz)
        # 2024 QBI limit is lower ($182,100) so phase-out reduces more
        # 2025 QBI limit is higher ($191,950) so less reduction
        assert r25.qbi_deduction >= r24.qbi_deduction
        # Verify both have QBI
        assert r24.qbi_deduction > 0
        assert r25.qbi_deduction > 0


# ---------------------------------------------------------------------------
# Summary includes tax_year
# ---------------------------------------------------------------------------
class TestSummaryYear:
    def test_summary_has_tax_year(self):
        r = compute(wages=50000, tax_year=2024)
        s = r.to_summary()
        assert s["tax_year"] == 2024

    def test_summary_2025(self):
        r = compute(wages=50000, tax_year=2025)
        s = r.to_summary()
        assert s["tax_year"] == 2025
