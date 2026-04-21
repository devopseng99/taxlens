"""Unit tests for multi-state tax computation engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from state_configs import StateConfig, StateTaxResult, get_state_config, clear_config_cache, NO_TAX_STATES
from state_tax_engine import compute_state_tax, compute_all_state_returns, compute_bracket_tax
from tax_engine import (
    compute_tax, PersonInfo, W2Income, StateWageInfo, AdditionalIncome,
    Deductions, Payments, BusinessIncome, CapitalTransaction,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear config cache before each test."""
    clear_config_cache()


# ---------------------------------------------------------------------------
# State Config Loading
# ---------------------------------------------------------------------------
class TestStateConfigLoading:
    def test_load_il(self):
        cfg = get_state_config("IL")
        assert cfg is not None
        assert cfg.name == "Illinois"
        assert cfg.tax_type == "flat"
        assert cfg.rate == 0.0495

    def test_load_ca(self):
        cfg = get_state_config("CA")
        assert cfg is not None
        assert cfg.name == "California"
        assert cfg.tax_type == "graduated"
        assert len(cfg.brackets["single"]) == 10

    def test_load_ny(self):
        cfg = get_state_config("NY")
        assert cfg is not None
        assert cfg.name == "New York"
        assert cfg.has_local_tax is True

    def test_load_nj(self):
        cfg = get_state_config("NJ")
        assert cfg is not None
        assert "PA" in cfg.reciprocal_states

    def test_load_pa(self):
        cfg = get_state_config("PA")
        assert cfg.tax_type == "flat"
        assert cfg.rate == 0.0307
        assert "NJ" in cfg.reciprocal_states

    def test_load_nc(self):
        cfg = get_state_config("NC")
        assert cfg.tax_type == "flat"
        assert cfg.rate == 0.045

    def test_load_ga(self):
        cfg = get_state_config("GA")
        assert cfg.tax_type == "graduated"

    def test_load_oh(self):
        cfg = get_state_config("OH")
        assert cfg.tax_type == "graduated"
        assert "PA" in cfg.reciprocal_states

    def test_no_tax_states_return_none(self):
        for state in ["TX", "FL", "AK", "NV", "WA", "WY"]:
            assert get_state_config(state) is None

    def test_unknown_state_returns_none(self):
        assert get_state_config("ZZ") is None

    def test_case_insensitive(self):
        cfg = get_state_config("il")
        assert cfg is not None
        assert cfg.abbreviation == "IL"


# ---------------------------------------------------------------------------
# Flat Rate States
# ---------------------------------------------------------------------------
class TestFlatRateStates:
    def test_il_basic(self):
        r = compute_state_tax("IL", "single", 80_000, num_exemptions=1)
        assert r.state_code == "IL"
        assert r.taxable_income == 80_000 - 2_775
        assert r.tax == round(r.taxable_income * 0.0495, 2)

    def test_il_mfj_exemptions(self):
        r = compute_state_tax("IL", "mfj", 100_000, num_exemptions=4)  # couple + 2 deps
        expected_exempt = 4 * 2_775
        assert r.exemptions == expected_exempt
        assert r.taxable_income == 100_000 - expected_exempt

    def test_pa_no_exemptions(self):
        r = compute_state_tax("PA", "single", 60_000, num_exemptions=1)
        # PA has no personal exemption
        assert r.taxable_income == 60_000
        assert r.tax == round(60_000 * 0.0307, 2)

    def test_nc_with_standard_deduction(self):
        r = compute_state_tax("NC", "single", 50_000, num_exemptions=1)
        assert r.standard_deduction_amount == 12_750
        assert r.taxable_income == max(0, 50_000 - 12_750)
        assert r.tax == round(r.taxable_income * 0.045, 2)


# ---------------------------------------------------------------------------
# Graduated Bracket States
# ---------------------------------------------------------------------------
class TestGraduatedStates:
    def test_ca_low_income(self):
        r = compute_state_tax("CA", "single", 30_000, num_exemptions=1)
        assert r.state_code == "CA"
        assert r.tax > 0
        # CA std ded is $5,540 for single, exemption $144
        assert r.standard_deduction_amount == 5_540
        assert r.exemptions == 144

    def test_ca_high_income_surtax(self):
        r = compute_state_tax("CA", "single", 1_500_000, num_exemptions=1)
        # Should have surtax (Mental Health Tax 1% on income > $1M)
        assert r.surtax > 0
        assert r.total_tax == r.tax + r.surtax

    def test_ny_single(self):
        r = compute_state_tax("NY", "single", 100_000, num_exemptions=1)
        assert r.state_code == "NY"
        assert r.standard_deduction_amount == 8_000
        assert r.tax > 0

    def test_nj_single(self):
        r = compute_state_tax("NJ", "single", 80_000, num_exemptions=1)
        assert r.state_code == "NJ"
        assert r.tax > 0

    def test_ga_mfj(self):
        r = compute_state_tax("GA", "mfj", 120_000, num_exemptions=2)
        assert r.state_code == "GA"
        assert r.tax > 0
        assert r.standard_deduction_amount == 24_000

    def test_oh_zero_bracket(self):
        # Ohio has a 0% bracket up to $26,050
        r = compute_state_tax("OH", "single", 20_000, num_exemptions=1)
        assert r.tax == 0  # Income below 0% bracket


# ---------------------------------------------------------------------------
# No-Tax States
# ---------------------------------------------------------------------------
class TestNoTaxStates:
    def test_tx_no_tax(self):
        r = compute_state_tax("TX", "single", 200_000, num_exemptions=1)
        assert r.tax == 0
        assert r.total_tax == 0

    def test_fl_no_tax(self):
        r = compute_state_tax("FL", "mfj", 500_000, num_exemptions=2)
        assert r.tax == 0
        assert r.total_tax == 0


# ---------------------------------------------------------------------------
# Withholding & Refund/Owed
# ---------------------------------------------------------------------------
class TestWithholding:
    def test_refund(self):
        r = compute_state_tax("IL", "single", 80_000, state_withholding=5_000, num_exemptions=1)
        expected_tax = round((80_000 - 2_775) * 0.0495, 2)
        assert r.total_tax == expected_tax
        if 5_000 > expected_tax:
            assert r.refund > 0
            assert r.owed == 0

    def test_owed(self):
        r = compute_state_tax("IL", "single", 80_000, state_withholding=1_000, num_exemptions=1)
        expected_tax = round((80_000 - 2_775) * 0.0495, 2)
        assert r.owed == round(expected_tax - 1_000, 2)
        assert r.refund == 0

    def test_estimated_payments(self):
        r = compute_state_tax("IL", "single", 80_000, estimated_payments=3_000, num_exemptions=1)
        expected_tax = round((80_000 - 2_775) * 0.0495, 2)
        diff = 3_000 - expected_tax
        if diff >= 0:
            assert r.refund == round(diff, 2)
        else:
            assert r.owed == round(abs(diff), 2)


# ---------------------------------------------------------------------------
# Multi-State Workers
# ---------------------------------------------------------------------------
class TestMultiStateWorkers:
    def test_single_state_resident(self):
        """Single state: only resident return generated."""
        results = compute_all_state_returns(
            residence_state="IL",
            work_states=[],
            filing_status="single",
            federal_agi=80_000,
            w2_state_wages={"IL": 80_000},
            w2_state_withheld={"IL": 3_000},
            num_exemptions=1,
        )
        assert len(results) == 1
        assert results[0].state_code == "IL"
        assert results[0].return_type == "resident"

    def test_nj_resident_ny_worker(self):
        """Classic NJ→NY commuter: nonresident NY + resident NJ with credit."""
        results = compute_all_state_returns(
            residence_state="NJ",
            work_states=["NY"],
            filing_status="single",
            federal_agi=120_000,
            w2_state_wages={"NY": 120_000},
            w2_state_withheld={"NY": 6_000, "NJ": 0},
            num_exemptions=1,
        )
        # Should have 2 returns: NY nonresident + NJ resident
        assert len(results) == 2

        ny_return = [r for r in results if r.state_code == "NY"][0]
        nj_return = [r for r in results if r.state_code == "NJ"][0]

        assert ny_return.return_type == "nonresident"
        assert ny_return.allocated_income == 120_000
        assert ny_return.total_tax > 0

        assert nj_return.return_type == "resident"
        assert nj_return.credit_for_other_states > 0  # Credit for NY tax paid

    def test_reciprocal_il_wi(self):
        """IL resident working in WI: reciprocal agreement, no WI return."""
        results = compute_all_state_returns(
            residence_state="IL",
            work_states=["WI"],
            filing_status="single",
            federal_agi=70_000,
            w2_state_wages={"IL": 70_000},
            w2_state_withheld={"IL": 2_500},
            num_exemptions=1,
        )
        # Only IL resident return (WI skipped due to reciprocal)
        assert len(results) == 1
        assert results[0].state_code == "IL"
        assert results[0].return_type == "resident"

    def test_reciprocal_pa_nj(self):
        """NJ resident working in PA: reciprocal, no PA return."""
        results = compute_all_state_returns(
            residence_state="NJ",
            work_states=["PA"],
            filing_status="single",
            federal_agi=80_000,
            w2_state_wages={"PA": 80_000},
            w2_state_withheld={"NJ": 0},
            num_exemptions=1,
        )
        assert len(results) == 1
        assert results[0].state_code == "NJ"

    def test_tx_resident_no_state_return(self):
        """TX resident: no state return needed."""
        results = compute_all_state_returns(
            residence_state="TX",
            work_states=[],
            filing_status="single",
            federal_agi=100_000,
            w2_state_wages={},
            w2_state_withheld={},
            num_exemptions=1,
        )
        assert len(results) == 0  # No state returns

    def test_tx_resident_ny_worker(self):
        """TX resident, works in NY: only NY nonresident return."""
        results = compute_all_state_returns(
            residence_state="TX",
            work_states=["NY"],
            filing_status="single",
            federal_agi=150_000,
            w2_state_wages={"NY": 150_000},
            w2_state_withheld={"NY": 8_000},
            num_exemptions=1,
        )
        assert len(results) == 1
        assert results[0].state_code == "NY"
        assert results[0].return_type == "nonresident"

    def test_days_worked_allocation(self):
        """Days-worked fallback for allocation."""
        results = compute_all_state_returns(
            residence_state="NJ",
            work_states=["NY"],
            filing_status="single",
            federal_agi=120_000,
            w2_state_wages={},  # No W-2 state breakdown
            w2_state_withheld={},
            num_exemptions=1,
            days_worked_by_state={"NY": 200, "NJ": 50},
            total_wages=120_000,
        )
        ny_return = [r for r in results if r.state_code == "NY"][0]
        expected_allocation = 120_000 * (200 / 250)
        assert abs(ny_return.allocated_income - expected_allocation) < 1

    def test_credit_capped_at_resident_tax(self):
        """Credit for other states can't exceed resident state's tax on same income."""
        results = compute_all_state_returns(
            residence_state="NJ",
            work_states=["NY"],
            filing_status="single",
            federal_agi=120_000,
            w2_state_wages={"NY": 120_000},
            w2_state_withheld={"NY": 6_000},
            num_exemptions=1,
        )
        nj_return = [r for r in results if r.state_code == "NJ"][0]
        ny_return = [r for r in results if r.state_code == "NY"][0]

        # Credit should be <= min(NY tax, NJ tax * allocation%)
        income_ratio = ny_return.allocated_income / 120_000
        max_credit = nj_return.total_tax * income_ratio
        assert nj_return.credit_for_other_states <= ny_return.total_tax + 0.01
        assert nj_return.credit_for_other_states <= max_credit + 0.01


# ---------------------------------------------------------------------------
# Backward Compatibility
# ---------------------------------------------------------------------------
class TestBackwardCompat:
    def test_il_fields_populated(self):
        """Verify il_* fields are still populated for IL residents."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="User"),
            w2s=[W2Income(wages=80_000, federal_withheld=10_000, state_withheld=3_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            residence_state="IL",
        )
        assert result.il_line_1_federal_agi > 0
        assert result.il_line_11_tax > 0
        assert result.il_line_18_withheld == 3_000
        assert result.residence_state == "IL"

    def test_il_in_forms_generated(self):
        """IL-1040 should appear in forms_generated for IL residents."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(),
            w2s=[W2Income(wages=50_000, federal_withheld=5_000, state_withheld=2_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            residence_state="IL",
        )
        assert "IL-1040" in result.forms_generated

    def test_state_taxes_in_summary(self):
        """to_summary() should include state_taxes array."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(),
            w2s=[W2Income(wages=50_000, federal_withheld=5_000, state_withheld=2_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            residence_state="IL",
        )
        summary = result.to_summary()
        assert "state_taxes" in summary
        assert len(summary["state_taxes"]) == 1
        assert summary["state_taxes"][0]["state"] == "IL"
        # Backward compat keys still present
        assert "illinois_tax" in summary
        assert summary["illinois_tax"] == summary["state_taxes"][0]["tax"]

    def test_ca_resident(self):
        """CA resident should get CA state return."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(),
            w2s=[W2Income(wages=100_000, federal_withheld=15_000, state_withheld=5_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            residence_state="CA",
        )
        assert result.residence_state == "CA"
        assert len(result.state_returns) == 1
        assert result.state_returns[0].state_code == "CA"
        assert "CA-540" in result.forms_generated
        # IL fields should be zero/empty
        assert result.il_line_11_tax == 0

    def test_tx_resident_no_state_forms(self):
        """TX resident: no state forms generated."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(),
            w2s=[W2Income(wages=80_000, federal_withheld=10_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            residence_state="TX",
        )
        assert result.residence_state == "TX"
        assert len(result.state_returns) == 0
        assert "IL-1040" not in result.forms_generated

    def test_multi_state_nj_ny(self):
        """NJ resident, NY worker: both state forms generated."""
        w2 = W2Income(
            wages=120_000, federal_withheld=18_000,
            state_wage_infos=[
                StateWageInfo(state="NY", state_wages=120_000, state_withheld=6_000),
            ],
        )
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(),
            w2s=[w2],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            residence_state="NJ",
            work_states=["NY"],
        )
        assert result.residence_state == "NJ"
        assert len(result.state_returns) == 2
        state_codes = {sr.state_code for sr in result.state_returns}
        assert "NY" in state_codes
        assert "NJ" in state_codes
        # Both forms present
        assert "IT-201" in result.forms_generated  # NY
        assert "NJ-1040" in result.forms_generated  # NJ


# ---------------------------------------------------------------------------
# W2Income StateWageInfo
# ---------------------------------------------------------------------------
class TestStateWageInfo:
    def test_w2_with_state_infos(self):
        w2 = W2Income(
            wages=120_000,
            state_wage_infos=[
                StateWageInfo(state="NY", state_wages=100_000, state_withheld=5_000),
                StateWageInfo(state="NJ", state_wages=20_000, state_withheld=800),
            ],
        )
        assert len(w2.state_wage_infos) == 2
        assert w2.state_wage_infos[0].state == "NY"

    def test_w2_without_state_infos_backward_compat(self):
        """Legacy W2Income without state_wage_infos still works."""
        w2 = W2Income(wages=80_000, state_wages=80_000, state_withheld=3_000)
        assert w2.state_wage_infos == []
        assert w2.state_wages == 80_000
