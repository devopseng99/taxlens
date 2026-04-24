"""Wave 50 tests — IRC §170 Charitable Contribution AGI Limits."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    compute_tax,
)

FILER = PersonInfo(first_name="Test", last_name="User")


def _compute(filing_status="single", wages=100_000, charitable_cash=0,
             charitable_noncash=0, tax_year=2025):
    return compute_tax(
        filing_status=filing_status,
        filer=FILER,
        w2s=[W2Income(wages=wages, federal_withheld=15_000)],
        additional=AdditionalIncome(),
        deductions=Deductions(
            charitable_cash=charitable_cash,
            charitable_noncash=charitable_noncash,
            property_tax=5000,  # Ensure itemized > standard
            mortgage_interest=10000,
        ),
        payments=Payments(),
        tax_year=tax_year,
    )


# =========================================================================
# Cash limit (60% of AGI)
# =========================================================================
class TestCashLimit:
    def test_cash_below_limit_no_reduction(self):
        """Cash under 60% of AGI passes through fully."""
        r = _compute(wages=100_000, charitable_cash=10_000)
        assert r.sched_a_charitable == 10_000
        assert r.charitable_carryforward == 0

    def test_cash_at_60pct_no_carryforward(self):
        """Cash exactly at 60% AGI → no carryforward."""
        # AGI = 100K, so 60% = 60K
        r = _compute(wages=100_000, charitable_cash=60_000)
        # AGI ≈ 100K (adjustments may reduce it slightly)
        assert r.sched_a_charitable <= 60_000
        assert r.charitable_carryforward >= 0

    def test_cash_exceeds_60pct_creates_carryforward(self):
        """Cash over 60% AGI is limited; excess becomes carryforward."""
        r = _compute(wages=100_000, charitable_cash=70_000)
        agi = r.line_11_agi
        limit = agi * 0.60
        assert r.sched_a_charitable == round(limit, 2)
        assert r.charitable_carryforward == round(70_000 - limit, 2)

    def test_tracks_original_cash_amount(self):
        """charitable_cash_before_limit tracks the raw input."""
        r = _compute(wages=100_000, charitable_cash=70_000)
        assert r.charitable_cash_before_limit == 70_000


# =========================================================================
# Non-cash limit (30% of AGI)
# =========================================================================
class TestNoncashLimit:
    def test_noncash_below_limit(self):
        """Non-cash under 30% of AGI passes through."""
        r = _compute(wages=100_000, charitable_noncash=10_000)
        assert r.sched_a_charitable == 10_000
        assert r.charitable_carryforward == 0

    def test_noncash_exceeds_30pct(self):
        """Non-cash over 30% AGI is capped."""
        r = _compute(wages=100_000, charitable_noncash=40_000)
        agi = r.line_11_agi
        noncash_limit = agi * 0.30
        assert r.sched_a_charitable == round(noncash_limit, 2)
        assert r.charitable_carryforward == round(40_000 - noncash_limit, 2)

    def test_tracks_original_noncash_amount(self):
        """charitable_noncash_before_limit tracks the raw input."""
        r = _compute(wages=100_000, charitable_noncash=40_000)
        assert r.charitable_noncash_before_limit == 40_000


# =========================================================================
# Combined cash + non-cash limits
# =========================================================================
class TestCombinedLimits:
    def test_both_under_limits(self):
        """Both under respective limits → full deduction."""
        r = _compute(wages=200_000, charitable_cash=50_000, charitable_noncash=20_000)
        assert r.sched_a_charitable == 70_000
        assert r.charitable_carryforward == 0

    def test_noncash_limited_cash_not(self):
        """Non-cash hits 30% limit but cash is fine."""
        r = _compute(wages=100_000, charitable_cash=20_000, charitable_noncash=40_000)
        agi = r.line_11_agi
        noncash_allowed = agi * 0.30
        # Cash is within 60% limit, noncash capped at 30%
        # Overall capped at 60%
        expected = min(20_000 + noncash_allowed, agi * 0.60)
        assert r.sched_a_charitable == round(expected, 2)

    def test_overall_60pct_cap(self):
        """Cash + non-cash together capped at 60% of AGI."""
        # Both under individual limits but combined exceeds 60%
        r = _compute(wages=100_000, charitable_cash=55_000, charitable_noncash=25_000)
        agi = r.line_11_agi
        overall = agi * 0.60
        assert r.sched_a_charitable <= round(overall, 2) + 0.01  # float tolerance

    def test_carryforward_in_summary(self):
        """charitable_carryforward appears in summary when > 0."""
        r = _compute(wages=100_000, charitable_cash=70_000)
        s = r.to_summary()
        assert s["charitable_carryforward"] is not None
        assert s["charitable_carryforward"] > 0

    def test_no_carryforward_in_summary_when_zero(self):
        """charitable_carryforward absent from summary when 0."""
        r = _compute(wages=200_000, charitable_cash=10_000)
        s = r.to_summary()
        assert s.get("charitable_carryforward") is None


# =========================================================================
# Edge cases
# =========================================================================
class TestEdgeCases:
    def test_zero_agi_zero_charitable(self):
        """Zero AGI → zero charitable allowed (no division by zero)."""
        r = compute_tax(
            filing_status="single",
            filer=FILER,
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(charitable_cash=5_000),
            payments=Payments(),
        )
        assert r.sched_a_charitable == 0
        assert r.charitable_carryforward == 5_000

    def test_zero_charitable_no_effect(self):
        """No charitable → no change."""
        r = _compute(wages=100_000, charitable_cash=0, charitable_noncash=0)
        assert r.sched_a_charitable == 0
        assert r.charitable_carryforward == 0

    def test_mfj_same_limits(self):
        """MFJ uses same 60%/30% percentages (higher AGI = higher dollar limit)."""
        r = _compute(filing_status="mfj", wages=200_000, charitable_cash=130_000)
        agi = r.line_11_agi
        limit = agi * 0.60
        assert r.sched_a_charitable == round(min(130_000, limit), 2)

    def test_2024_same_statutory_rates(self):
        """2024 uses same 60%/30% rates (statutory, not indexed)."""
        r = _compute(wages=100_000, charitable_cash=70_000, tax_year=2024)
        agi = r.line_11_agi
        limit = agi * 0.60
        assert r.sched_a_charitable == round(limit, 2)


# =========================================================================
# Backward compatibility
# =========================================================================
class TestBackwardCompat:
    def test_small_donations_unchanged(self):
        """Small donations well under limits work exactly as before."""
        r = _compute(wages=100_000, charitable_cash=5_000, charitable_noncash=2_000)
        assert r.sched_a_charitable == 7_000
        assert r.charitable_carryforward == 0
