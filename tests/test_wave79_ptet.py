"""Wave 79 tests — PTET (Pass-Through Entity Tax) Framework."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    compute_tax, PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    K1Income,
)
from state_configs import get_state_config, clear_config_cache


# =========================================================================
# State Config — PTET Availability
# =========================================================================
class TestPTETConfig:
    def setup_method(self):
        clear_config_cache()

    def test_ca_ptet_available(self):
        c = get_state_config("CA")
        assert c.ptet_available is True
        assert "s_corp" in c.ptet_entity_types
        assert "partnership" in c.ptet_entity_types

    def test_ny_ptet_available(self):
        c = get_state_config("NY")
        assert c.ptet_available is True

    def test_il_ptet_available(self):
        c = get_state_config("IL")
        assert c.ptet_available is True

    def test_nj_ptet_available(self):
        c = get_state_config("NJ")
        assert c.ptet_available is True

    def test_pa_no_ptet(self):
        """PA doesn't have standard PTET in our config."""
        c = get_state_config("PA")
        assert c.ptet_available is False

    def test_no_tax_state_no_ptet(self):
        """No-tax states have no config at all."""
        c = get_state_config("FL")
        assert c is None


# =========================================================================
# K1Income PTET Fields
# =========================================================================
class TestK1PTETFields:
    def test_ptet_fields_exist(self):
        k1 = K1Income(
            entity_name="Test LLC",
            entity_type="partnership",
            ordinary_income=100_000,
            ptet_election=True,
            ptet_state="CA",
            ptet_tax_paid=9_300,
        )
        assert k1.ptet_election is True
        assert k1.ptet_state == "CA"
        assert k1.ptet_tax_paid == 9_300

    def test_ptet_defaults_off(self):
        k1 = K1Income(ordinary_income=50_000)
        assert k1.ptet_election is False
        assert k1.ptet_state == ""
        assert k1.ptet_tax_paid == 0.0


# =========================================================================
# PTET Credit Computation
# =========================================================================
def _ptet_filer(ptet_state="IL", ptet_tax_paid=5_000, ordinary_income=100_000,
                residence_state="IL", filing_status="single"):
    return compute_tax(
        filing_status=filing_status,
        filer=PersonInfo(first_name="PTET", last_name="Filer"),
        w2s=[],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
        k1_incomes=[K1Income(
            entity_name="Test S-Corp",
            entity_type="s_corp",
            ordinary_income=ordinary_income,
            ptet_election=True,
            ptet_state=ptet_state,
            ptet_tax_paid=ptet_tax_paid,
        )],
        residence_state=residence_state,
    )


class TestPTETCredit:
    def test_ptet_credit_tracked(self):
        """PTET credit should appear on TaxResult."""
        result = _ptet_filer()
        assert result.ptet_total_credit == 5_000
        assert len(result.ptet_credits) == 1
        assert result.ptet_credits[0]["state"] == "IL"
        assert result.ptet_credits[0]["tax_paid"] == 5_000

    def test_ptet_credit_reduces_state_tax(self):
        """PTET credit should reduce state tax owed."""
        result_no_ptet = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="No", last_name="PTET"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(
                entity_name="Test S-Corp",
                entity_type="s_corp",
                ordinary_income=100_000,
            )],
            residence_state="IL",
        )
        result_ptet = _ptet_filer()

        # Find IL state returns
        il_no_ptet = [sr for sr in result_no_ptet.state_returns if sr.state_code == "IL"]
        il_ptet = [sr for sr in result_ptet.state_returns if sr.state_code == "IL"]

        assert len(il_no_ptet) > 0
        assert len(il_ptet) > 0

        # PTET should reduce state tax
        assert il_ptet[0].total_tax < il_no_ptet[0].total_tax

    def test_ptet_credit_applied_to_state(self):
        """State return should show PTET credit."""
        result = _ptet_filer()
        il_return = [sr for sr in result.state_returns if sr.state_code == "IL"][0]
        assert il_return.ptet_credit == 5_000

    def test_no_ptet_no_credit(self):
        """Without PTET election, no credit."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="No", last_name="PTET"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(
                entity_name="Test S-Corp",
                entity_type="s_corp",
                ordinary_income=100_000,
            )],
            residence_state="IL",
        )
        assert result.ptet_total_credit == 0.0
        assert result.ptet_credits == []

    def test_multiple_k1_ptet(self):
        """Multiple K-1s with PTET should sum credits."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Multi", last_name="K1"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[
                K1Income(
                    entity_name="LLC-A", entity_type="partnership",
                    ordinary_income=60_000,
                    ptet_election=True, ptet_state="IL", ptet_tax_paid=3_000,
                ),
                K1Income(
                    entity_name="S-Corp-B", entity_type="s_corp",
                    ordinary_income=40_000,
                    ptet_election=True, ptet_state="IL", ptet_tax_paid=2_000,
                ),
            ],
            residence_state="IL",
        )
        assert result.ptet_total_credit == 5_000
        assert len(result.ptet_credits) == 2


# =========================================================================
# SALT Cap Bypass (the key PTET value proposition)
# =========================================================================
class TestSALTBypass:
    def test_ptet_bypasses_salt_cap(self):
        """PTET entity-level tax is NOT subject to $10K SALT cap.

        A filer with $100K K-1 income in IL would owe ~$4,950 state tax.
        Without PTET: this $4,950 is personal state tax, subject to SALT cap.
        With PTET: the entity pays the tax directly (not on the personal return),
        and the filer claims a credit. The SALT cap only applies to personal
        state tax payments, not entity-level PTET.
        """
        # Filer with high state tax + property tax — SALT capped at $10K
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="SALT", last_name="Test"),
            w2s=[W2Income(wages=200_000, federal_withheld=40_000,
                          ss_wages=200_000, medicare_wages=200_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(
                property_tax=15_000,
                state_income_tax_paid=12_000,  # Total SALT = $27K, capped at $10K
            ),
            payments=Payments(),
            k1_incomes=[K1Income(
                entity_name="My S-Corp",
                entity_type="s_corp",
                ordinary_income=100_000,
                ptet_election=True,
                ptet_state="IL",
                ptet_tax_paid=4_950,
            )],
            residence_state="IL",
        )
        # SALT is capped at $10K for personal itemized deductions
        assert result.sched_a_salt == 10_000
        # But PTET credit reduces state tax separately
        assert result.ptet_total_credit == 4_950


# =========================================================================
# to_summary() Output
# =========================================================================
class TestSummaryOutput:
    def test_summary_includes_ptet(self):
        result = _ptet_filer()
        summary = result.to_summary()
        assert "ptet_total_credit" in summary
        assert summary["ptet_total_credit"] == 5_000
        assert summary["ptet_credits"] is not None
        assert len(summary["ptet_credits"]) == 1

    def test_summary_state_taxes_include_ptet(self):
        result = _ptet_filer()
        summary = result.to_summary()
        il_state = [s for s in summary["state_taxes"] if s["state"] == "IL"]
        assert len(il_state) > 0
        assert il_state[0]["ptet_credit"] == 5_000

    def test_summary_no_ptet_null(self):
        """No PTET → ptet_credits is null in summary."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="No", last_name="PTET"),
            w2s=[W2Income(wages=80_000, federal_withheld=16_000,
                          ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        summary = result.to_summary()
        assert summary["ptet_total_credit"] == 0.0
        assert summary["ptet_credits"] is None


# =========================================================================
# Edge Cases
# =========================================================================
class TestEdgeCases:
    def test_ptet_zero_tax_paid(self):
        """PTET election with $0 tax paid → no credit."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Zero", last_name="PTET"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(
                entity_name="Test",
                ordinary_income=50_000,
                ptet_election=True,
                ptet_state="IL",
                ptet_tax_paid=0,
            )],
            residence_state="IL",
        )
        assert result.ptet_total_credit == 0.0

    def test_backward_compatible(self):
        """K-1 without PTET fields works as before."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Old", last_name="K1"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            k1_incomes=[K1Income(
                entity_name="Old LLC",
                ordinary_income=50_000,
            )],
            residence_state="IL",
        )
        assert result.ptet_total_credit == 0.0
        assert result.k1_ordinary_income == 50_000
