"""Wave 83 tests — IL PPRT (Personal Property Replacement Tax)."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    compute_tax, PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    K1Income,
)
from state_configs import get_state_config, clear_config_cache


# =========================================================================
# State Config — PPRT Availability
# =========================================================================
class TestPPRTConfig:
    def setup_method(self):
        clear_config_cache()

    def test_il_pprt_rate(self):
        c = get_state_config("IL")
        assert c.pprt_rate == 0.015
        assert "s_corp" in c.pprt_entity_types
        assert "partnership" in c.pprt_entity_types

    def test_ca_no_pprt(self):
        """CA doesn't have PPRT."""
        c = get_state_config("CA")
        assert c.pprt_rate == 0.0

    def test_ny_no_pprt(self):
        c = get_state_config("NY")
        assert c.pprt_rate == 0.0


# =========================================================================
# PPRT Computation
# =========================================================================
def _il_k1_filer(ordinary_income=100_000, entity_type="s_corp", residence_state="IL"):
    return compute_tax(
        filing_status="single",
        filer=PersonInfo(first_name="PPRT", last_name="Test"),
        w2s=[],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
        k1_incomes=[K1Income(
            entity_name="Test Entity",
            entity_type=entity_type,
            ordinary_income=ordinary_income,
        )],
        residence_state=residence_state,
    )


class TestPPRTComputation:
    def test_pprt_on_s_corp_income(self):
        """S-corp K-1 income in IL triggers 1.5% PPRT."""
        result = _il_k1_filer(ordinary_income=100_000, entity_type="s_corp")
        assert result.pprt_total == 1_500  # 100K × 1.5%
        assert len(result.pprt_details) == 1
        assert result.pprt_details[0]["tax"] == 1_500
        assert result.pprt_details[0]["rate"] == 0.015

    def test_pprt_on_partnership_income(self):
        """Partnership K-1 income in IL also triggers PPRT."""
        result = _il_k1_filer(ordinary_income=80_000, entity_type="partnership")
        assert result.pprt_total == 1_200  # 80K × 1.5%

    def test_pprt_not_on_trust(self):
        """Trust K-1 income should NOT trigger PPRT."""
        result = _il_k1_filer(ordinary_income=100_000, entity_type="trust")
        assert result.pprt_total == 0
        assert result.pprt_details == []

    def test_pprt_zero_income(self):
        """Zero K-1 income → no PPRT."""
        result = _il_k1_filer(ordinary_income=0)
        assert result.pprt_total == 0

    def test_pprt_multiple_entities(self):
        """Multiple K-1s in IL → PPRT on each."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Multi", last_name="K1"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[
                K1Income(entity_name="LLC-A", entity_type="partnership",
                         ordinary_income=60_000),
                K1Income(entity_name="S-Corp-B", entity_type="s_corp",
                         ordinary_income=40_000),
            ],
            residence_state="IL",
        )
        assert result.pprt_total == 1_500  # (60K + 40K) × 1.5%
        assert len(result.pprt_details) == 2

    def test_pprt_non_il_state(self):
        """K-1 income in non-IL state → no PPRT."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="CA", last_name="Filer"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(
                entity_name="CA Corp", entity_type="s_corp",
                ordinary_income=100_000,
            )],
            residence_state="CA",
        )
        assert result.pprt_total == 0


# =========================================================================
# PPRT Impact on State Return
# =========================================================================
class TestPPRTStateReturn:
    def test_pprt_increases_il_state_tax(self):
        """PPRT should increase IL state total_tax."""
        result_no_k1 = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="No", last_name="K1"),
            w2s=[W2Income(wages=100_000, federal_withheld=20_000,
                          ss_wages=100_000, medicare_wages=100_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            residence_state="IL",
        )
        result_k1 = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="With", last_name="K1"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(entity_name="My LLC", entity_type="s_corp",
                                 ordinary_income=100_000)],
            residence_state="IL",
        )
        il_k1 = [sr for sr in result_k1.state_returns if sr.state_code == "IL"][0]
        assert il_k1.pprt_tax == 1_500

    def test_pprt_in_state_taxes_summary(self):
        """to_summary() should include pprt_tax in state_taxes."""
        result = _il_k1_filer()
        summary = result.to_summary()
        il_state = [s for s in summary["state_taxes"] if s["state"] == "IL"]
        assert len(il_state) > 0
        assert il_state[0]["pprt_tax"] == 1_500


# =========================================================================
# to_summary() Output
# =========================================================================
class TestSummaryOutput:
    def test_summary_includes_pprt(self):
        result = _il_k1_filer()
        summary = result.to_summary()
        assert summary["pprt_total"] == 1_500
        assert summary["pprt_details"] is not None
        assert len(summary["pprt_details"]) == 1

    def test_summary_no_pprt_null(self):
        """No PPRT → null in summary."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="No", last_name="PPRT"),
            w2s=[W2Income(wages=80_000, federal_withheld=16_000,
                          ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        summary = result.to_summary()
        assert summary["pprt_total"] is None
        assert summary["pprt_details"] is None


# =========================================================================
# Edge Cases
# =========================================================================
class TestEdgeCases:
    def test_pprt_with_ptet_credit(self):
        """PPRT and PTET credit both applied correctly."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Both", last_name="Test"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(
                entity_name="My S-Corp", entity_type="s_corp",
                ordinary_income=100_000,
                ptet_election=True, ptet_state="IL", ptet_tax_paid=4_950,
            )],
            residence_state="IL",
        )
        assert result.ptet_total_credit == 4_950
        assert result.pprt_total == 1_500
        il_return = [sr for sr in result.state_returns if sr.state_code == "IL"][0]
        assert il_return.ptet_credit == 4_950
        assert il_return.pprt_tax == 1_500

    def test_backward_compatible(self):
        """K-1 without PPRT-triggering entity type works as before."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Old", last_name="K1"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(entity_name="Trust", entity_type="trust",
                                 ordinary_income=50_000)],
            residence_state="IL",
        )
        assert result.pprt_total == 0
