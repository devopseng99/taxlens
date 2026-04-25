"""Wave 78 tests — TCJA Sunset 2025 vs 2026 Comparison Engine."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    compute_tax, PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    BusinessIncome,
)
from tax_config import get_year_config, SUPPORTED_TAX_YEARS


# =========================================================================
# 2026 Config Existence
# =========================================================================
class TestConfig2026:
    def test_2026_supported(self):
        assert 2026 in SUPPORTED_TAX_YEARS

    def test_2026_config_loadable(self):
        c = get_year_config(2026)
        assert hasattr(c, 'FEDERAL_BRACKETS')
        assert hasattr(c, 'STANDARD_DEDUCTION')

    def test_2026_brackets_have_396(self):
        """2026 reverts to 39.6% top rate."""
        c = get_year_config(2026)
        top_rate = c.FEDERAL_BRACKETS["single"][-1][1]
        assert top_rate == 0.396

    def test_2025_brackets_have_37(self):
        """2025 has 37% top rate (TCJA)."""
        c = get_year_config(2025)
        top_rate = c.FEDERAL_BRACKETS["single"][-1][1]
        assert top_rate == 0.37

    def test_2026_standard_deduction_lower(self):
        """2026 standard deduction is roughly half of 2025."""
        c25 = get_year_config(2025)
        c26 = get_year_config(2026)
        assert c26.STANDARD_DEDUCTION["single"] < c25.STANDARD_DEDUCTION["single"]
        assert c26.STANDARD_DEDUCTION["single"] < 10_000

    def test_2026_qbi_rate_zero(self):
        """QBI §199A expires in 2026."""
        c = get_year_config(2026)
        assert c.QBI_DEDUCTION_RATE == 0.00

    def test_2025_qbi_rate_20pct(self):
        """QBI still 20% in 2025."""
        c = get_year_config(2025)
        assert c.QBI_DEDUCTION_RATE == 0.20

    def test_2026_salt_cap_removed(self):
        """SALT cap removed in 2026 (effectively unlimited)."""
        c = get_year_config(2026)
        assert c.SALT_CAP > 100_000_000

    def test_2025_salt_cap_10k(self):
        """SALT capped at $10K in 2025."""
        c = get_year_config(2025)
        assert c.SALT_CAP == 10_000

    def test_2026_ctc_reduced(self):
        """CTC drops from $2K to $1K in 2026."""
        c26 = get_year_config(2026)
        assert c26.CTC_PER_CHILD == 1_000

    def test_2025_ctc_2000(self):
        c25 = get_year_config(2025)
        assert c25.CTC_PER_CHILD == 2_000

    def test_2026_personal_exemption_restored(self):
        """Personal exemption restored in 2026."""
        c = get_year_config(2026)
        assert c.PERSONAL_EXEMPTION > 5_000

    def test_2026_amт_exemption_lower(self):
        """AMT exemption drops in 2026."""
        c25 = get_year_config(2025)
        c26 = get_year_config(2026)
        assert c26.AMT_EXEMPTION["single"] < c25.AMT_EXEMPTION["single"]

    def test_2026_has_15pct_bracket(self):
        """Pre-TCJA has 15% bracket (TCJA merged into 12%)."""
        c = get_year_config(2026)
        rates = [r for _, r in c.FEDERAL_BRACKETS["single"]]
        assert 0.15 in rates

    def test_2025_no_15pct_bracket(self):
        """TCJA has 12% bracket, not 15%."""
        c = get_year_config(2025)
        rates = [r for _, r in c.FEDERAL_BRACKETS["single"]]
        assert 0.15 not in rates
        assert 0.12 in rates


# =========================================================================
# Computation with 2026
# =========================================================================
def _compute(wages=80_000, tax_year=2025, filing_status="single", **kwargs):
    return compute_tax(
        filing_status=filing_status,
        filer=PersonInfo(first_name="TCJA", last_name="Test"),
        w2s=[W2Income(wages=wages, federal_withheld=wages * 0.2,
                      ss_wages=wages, medicare_wages=wages)],
        additional=AdditionalIncome(),
        deductions=Deductions(**kwargs),
        payments=Payments(),
        tax_year=tax_year,
    )


class TestTCJAComputation:
    def test_2026_computes_without_error(self):
        """Basic computation works for 2026."""
        result = _compute(tax_year=2026)
        assert result.line_24_total_tax > 0

    def test_2026_higher_tax_same_income(self):
        """Same W-2 income, 2026 should have higher tax (for typical earners)."""
        r25 = _compute(wages=100_000, tax_year=2025)
        r26 = _compute(wages=100_000, tax_year=2026)
        # Higher brackets + lower standard deduction → more tax
        assert r26.line_24_total_tax > r25.line_24_total_tax

    def test_2026_lower_standard_deduction_used(self):
        """2026 should use lower standard deduction."""
        r25 = _compute(tax_year=2025)
        r26 = _compute(tax_year=2026)
        if r25.deduction_type == "standard" and r26.deduction_type == "standard":
            assert r26.line_13_deduction < r25.line_13_deduction

    def test_2026_no_qbi_deduction(self):
        """2026 should not get QBI deduction."""
        r = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Biz", last_name="Owner"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            businesses=[BusinessIncome(gross_receipts=80_000)],
            tax_year=2026,
        )
        assert r.qbi_deduction == 0.0

    def test_2025_gets_qbi_deduction(self):
        """2025 should get QBI deduction."""
        r = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Biz", last_name="Owner"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            businesses=[BusinessIncome(gross_receipts=80_000)],
            tax_year=2025,
        )
        assert r.qbi_deduction > 0

    def test_2026_salt_unlimited(self):
        """2026 should not cap SALT deduction."""
        r = _compute(
            wages=200_000, tax_year=2026,
            property_tax=15_000, state_income_tax_paid=10_000,
        )
        # $25K SALT should be fully deductible (no $10K cap)
        assert r.sched_a_salt == 25_000

    def test_2025_salt_capped(self):
        """2025 should cap SALT at $10K."""
        r = _compute(
            wages=200_000, tax_year=2025,
            property_tax=15_000, state_income_tax_paid=10_000,
        )
        assert r.sched_a_salt == 10_000

    def test_personal_exemption_2026(self):
        """2026 single filer gets 1 personal exemption."""
        r = _compute(wages=80_000, tax_year=2026)
        assert r.personal_exemption > 5_000

    def test_personal_exemption_2025_zero(self):
        """2025 filer gets $0 personal exemption (TCJA)."""
        r = _compute(wages=80_000, tax_year=2025)
        assert r.personal_exemption == 0.0

    def test_personal_exemption_mfj_2026(self):
        """MFJ gets 2 personal exemptions in 2026."""
        r = compute_tax(
            filing_status="mfj",
            filer=PersonInfo(first_name="Test", last_name="MFJ"),
            w2s=[W2Income(wages=100_000, federal_withheld=20_000,
                          ss_wages=100_000, medicare_wages=100_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            tax_year=2026,
        )
        c26 = get_year_config(2026)
        assert r.personal_exemption == c26.PERSONAL_EXEMPTION * 2

    def test_personal_exemption_with_dependents(self):
        """Dependents add personal exemptions in 2026."""
        r = _compute(wages=80_000, tax_year=2026)
        r_dep = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Parent", last_name="Test"),
            w2s=[W2Income(wages=80_000, federal_withheld=16_000,
                          ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            num_dependents=2,
            tax_year=2026,
        )
        c26 = get_year_config(2026)
        assert r_dep.personal_exemption == c26.PERSONAL_EXEMPTION * 3  # filer + 2 deps


# =========================================================================
# High SALT Filer (biggest TCJA benefit reversal)
# =========================================================================
class TestHighSALTFiler:
    def test_high_salt_filer_saves_in_2026(self):
        """High-SALT filer may pay LESS tax in 2026 (SALT cap removed)."""
        # Filer with $50K in state/property taxes — currently capped at $10K
        r25 = _compute(
            wages=400_000, tax_year=2025,
            property_tax=25_000, state_income_tax_paid=25_000,
            mortgage_interest=20_000,
        )
        r26 = _compute(
            wages=400_000, tax_year=2026,
            property_tax=25_000, state_income_tax_paid=25_000,
            mortgage_interest=20_000,
        )
        # SALT deduction: 2025 = $10K, 2026 = $50K
        assert r25.sched_a_salt == 10_000
        assert r26.sched_a_salt == 50_000
        # The $40K extra SALT deduction may offset higher bracket rates
        # (This is the key policy insight — high-SALT states benefit from sunset)


# =========================================================================
# CTC Impact
# =========================================================================
class TestCTCImpact:
    def test_ctc_lower_in_2026(self):
        """CTC drops from $2K to $1K per child in 2026."""
        r25 = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Parent", last_name="CTC"),
            w2s=[W2Income(wages=60_000, federal_withheld=12_000,
                          ss_wages=60_000, medicare_wages=60_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            num_dependents=2,
            tax_year=2025,
        )
        r26 = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Parent", last_name="CTC"),
            w2s=[W2Income(wages=60_000, federal_withheld=12_000,
                          ss_wages=60_000, medicare_wages=60_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            num_dependents=2,
            tax_year=2026,
        )
        assert r25.line_27_ctc > r26.line_27_ctc  # $4K vs $2K
