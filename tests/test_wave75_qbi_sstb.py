"""Wave 75 tests — QBI SSTB Classification (Section 199A(d)(2))."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    compute_tax, PersonInfo, W2Income, BusinessIncome, Deductions,
    AdditionalIncome, Payments,
)
from tax_config import get_year_config


def _biz_filer(net_profit=100_000, is_sstb=False, w2_wages_paid=0,
               filing_status="single", tax_year=2025):
    return compute_tax(
        filing_status=filing_status,
        filer=PersonInfo(first_name="Test", last_name="QBI"),
        w2s=[],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
        businesses=[BusinessIncome(
            gross_receipts=net_profit,
            is_sstb=is_sstb,
            w2_wages_paid=w2_wages_paid,
        )],
        tax_year=tax_year,
    )


def _biz_filer_with_w2(w2_wages=0, net_profit=100_000, is_sstb=False, w2_wages_paid=0,
                        filing_status="single"):
    """Filer with both W-2 wages and business income (to push income above QBI threshold)."""
    return compute_tax(
        filing_status=filing_status,
        filer=PersonInfo(first_name="Test", last_name="QBI"),
        w2s=[W2Income(wages=w2_wages, federal_withheld=w2_wages * 0.2,
                      ss_wages=w2_wages, medicare_wages=w2_wages)] if w2_wages > 0 else [],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
        businesses=[BusinessIncome(
            gross_receipts=net_profit,
            is_sstb=is_sstb,
            w2_wages_paid=w2_wages_paid,
        )],
    )


# =========================================================================
# Below Threshold — SSTB doesn't matter
# =========================================================================
class TestBelowThreshold:
    def test_sstb_below_threshold_full_qbi(self):
        """Below QBI threshold: SSTB gets full 20% deduction (same as non-SSTB)."""
        result_sstb = _biz_filer(net_profit=80_000, is_sstb=True)
        result_normal = _biz_filer(net_profit=80_000, is_sstb=False)
        assert result_sstb.qbi_deduction == result_normal.qbi_deduction
        assert result_sstb.qbi_deduction > 0

    def test_sstb_flag_tracked(self):
        """SSTB flag is recorded on TaxResult."""
        result = _biz_filer(net_profit=80_000, is_sstb=True)
        assert result.qbi_is_sstb is True
        result2 = _biz_filer(net_profit=80_000, is_sstb=False)
        assert result2.qbi_is_sstb is False


# =========================================================================
# Above Threshold — SSTB phases to $0
# =========================================================================
class TestAboveThreshold:
    def test_sstb_above_phaseout_qbi_zero(self):
        """SSTB above phaseout range: QBI = $0."""
        c = get_year_config(2025)
        # Need taxable income above threshold + range
        # Single threshold = ~$191,950, range = $50,000
        # So need taxable > $241,950
        # W-2 wages to push high enough
        result = _biz_filer_with_w2(w2_wages=200_000, net_profit=100_000, is_sstb=True)
        # Taxable income should be well above threshold + range
        assert result.qbi_deduction == 0.0
        assert result.qbi_sstb_phaseout is True

    def test_non_sstb_above_threshold_w2_limitation(self):
        """Non-SSTB above phaseout: QBI limited to W-2 wages paid (not $0)."""
        result = _biz_filer_with_w2(w2_wages=200_000, net_profit=100_000,
                                    is_sstb=False, w2_wages_paid=50_000)
        # Non-SSTB should get W-2 wage limitation: max(50% of 50K, 25% of 50K) = 25K
        assert result.qbi_deduction == 25_000

    def test_non_sstb_above_no_w2_wages_zero(self):
        """Non-SSTB above phaseout with no W-2 wages: QBI = $0 (same as SSTB)."""
        result = _biz_filer_with_w2(w2_wages=200_000, net_profit=100_000,
                                    is_sstb=False, w2_wages_paid=0)
        assert result.qbi_deduction == 0.0


# =========================================================================
# In Phaseout Range — SSTB proportional reduction
# =========================================================================
class TestPhaseoutRange:
    def test_sstb_in_phaseout_partial_qbi(self):
        """SSTB in phaseout range: QBI proportionally reduced."""
        c = get_year_config(2025)
        # Single threshold ~$191,950, range $50K
        # Need taxable income around $210K (roughly halfway through phaseout)
        # Business income ~$100K + W-2 ~$130K → AGI ~$222K → taxable ~$207K
        result = _biz_filer_with_w2(w2_wages=130_000, net_profit=100_000, is_sstb=True)
        # Should have partial QBI (not full, not zero)
        full_qbi = result.sched_c_total_profit * 0.20
        assert result.qbi_deduction > 0
        assert result.qbi_deduction < full_qbi
        assert result.qbi_sstb_phaseout is True

    def test_non_sstb_in_phaseout_different_calc(self):
        """Non-SSTB in phaseout uses different formula (excess over W-2 limit)."""
        result_sstb = _biz_filer_with_w2(w2_wages=130_000, net_profit=100_000,
                                         is_sstb=True, w2_wages_paid=30_000)
        result_normal = _biz_filer_with_w2(w2_wages=130_000, net_profit=100_000,
                                           is_sstb=False, w2_wages_paid=30_000)
        # Different formulas should produce different results
        # (unless they happen to coincide, which is unlikely)
        assert result_sstb.qbi_deduction != result_normal.qbi_deduction


# =========================================================================
# Edge Cases
# =========================================================================
class TestEdgeCases:
    def test_backward_compatible_no_sstb(self):
        """Default is_sstb=False: behavior unchanged."""
        result = _biz_filer(net_profit=100_000, is_sstb=False)
        assert result.qbi_is_sstb is False
        assert result.qbi_deduction > 0

    def test_w2_wages_paid_field(self):
        """w2_wages_paid field exists on BusinessIncome."""
        b = BusinessIncome(gross_receipts=100_000, w2_wages_paid=50_000)
        assert b.w2_wages_paid == 50_000

    def test_mfj_sstb_threshold(self):
        """MFJ SSTB uses MFJ threshold (~$383,900)."""
        c = get_year_config(2025)
        # MFJ below threshold: full QBI
        result = _biz_filer(net_profit=200_000, is_sstb=True, filing_status="mfj")
        assert result.qbi_deduction > 0
        # Taxable income is well below MFJ threshold
        assert result.line_15_taxable_income < c.QBI_TAXABLE_INCOME_LIMIT["mfj"]

    def test_sstb_2024_limits(self):
        """2024 has lower QBI thresholds."""
        c24 = get_year_config(2024)
        c25 = get_year_config(2025)
        assert c24.QBI_TAXABLE_INCOME_LIMIT["single"] < c25.QBI_TAXABLE_INCOME_LIMIT["single"]

    def test_no_business_income_no_qbi(self):
        """No business income: no QBI regardless of SSTB."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="W2", last_name="Only"),
            w2s=[W2Income(wages=80_000, federal_withheld=10_000,
                          ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        assert result.qbi_deduction == 0
        assert result.qbi_is_sstb is False


# =========================================================================
# Tax Impact
# =========================================================================
class TestTaxImpact:
    def test_sstb_pays_more_tax_above_threshold(self):
        """SSTB filer pays more tax than non-SSTB above threshold."""
        result_sstb = _biz_filer_with_w2(w2_wages=200_000, net_profit=100_000,
                                         is_sstb=True, w2_wages_paid=50_000)
        result_normal = _biz_filer_with_w2(w2_wages=200_000, net_profit=100_000,
                                           is_sstb=False, w2_wages_paid=50_000)
        # SSTB gets $0 QBI, non-SSTB gets W-2 limitation
        assert result_sstb.qbi_deduction < result_normal.qbi_deduction
        assert result_sstb.line_24_total_tax > result_normal.line_24_total_tax
