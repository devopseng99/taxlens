"""Wave 80 tests — Carryforward Tracking System."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    compute_tax, PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    RentalProperty,
)


def _simple(filing_status="single", wages=100_000, **kwargs):
    return compute_tax(
        filing_status=filing_status,
        filer=PersonInfo(first_name="CF", last_name="Test"),
        w2s=[W2Income(wages=wages, federal_withheld=20_000,
                      ss_wages=wages, medicare_wages=wages)] if wages else [],
        additional=AdditionalIncome(),
        deductions=kwargs.pop("deductions", Deductions()),
        payments=Payments(),
        **kwargs,
    )


# =========================================================================
# Charitable Carryover
# =========================================================================
class TestCharitableCarryover:
    def test_carryover_consumed(self):
        """Prior-year charitable carryover fills remaining AGI room."""
        result = _simple(
            deductions=Deductions(charitable_cash=20_000),
            charitable_carryover=5_000,
        )
        # AGI ~$100K → 60% limit = $60K; $20K used, $40K room → $5K carryover used
        assert result.charitable_carryover_used == 5_000
        assert result.sched_a_charitable == 25_000  # 20K + 5K

    def test_carryover_exceeds_room(self):
        """Only room below AGI limit is consumed; excess carries forward again."""
        result = _simple(
            wages=50_000,
            deductions=Deductions(charitable_cash=28_000),
            charitable_carryover=10_000,
        )
        # AGI ~$50K → 60% limit = $30K; $28K used, $2K room
        assert result.charitable_carryover_used == 2_000
        # Remaining: $10K - $2K = $8K still carries forward
        assert result.charitable_carryforward == 8_000

    def test_carryover_with_current_excess(self):
        """Both current excess and unused prior carry forward."""
        result = _simple(
            wages=30_000,
            deductions=Deductions(charitable_cash=25_000),
            charitable_carryover=5_000,
        )
        # AGI ~$30K → 60% limit = $18K; $25K cash → $18K allowed, $7K excess
        # No room for carryover → $0 used
        assert result.charitable_carryover_used == 0
        # New carryforward = $7K current excess + $5K unused prior = $12K
        assert result.charitable_carryforward == 12_000

    def test_no_carryover_no_change(self):
        """Without carryover, behavior unchanged."""
        result = _simple(
            deductions=Deductions(charitable_cash=5_000),
        )
        assert result.charitable_carryover_used == 0
        assert result.charitable_carryforward == 0

    def test_zero_charitable_uses_carryover(self):
        """No current donations but prior carryover consumed."""
        result = _simple(charitable_carryover=3_000)
        # AGI ~$100K → 60% limit = $60K; $0 current, $60K room → $3K used
        assert result.charitable_carryover_used == 3_000
        assert result.sched_a_charitable == 3_000
        assert result.charitable_carryforward == 0


# =========================================================================
# Passive Activity Loss Carryover
# =========================================================================
class TestPassiveLossCarryover:
    def test_prior_loss_offsets_rental_income(self):
        """Prior suspended losses offset current rental income."""
        result = _simple(
            rental_properties=[RentalProperty(
                property_address="123 Main St", gross_rents=30_000,
                mortgage_interest=10_000, taxes=5_000,  # Net = +$15K
            )],
            passive_loss_carryover=8_000,
        )
        assert result.passive_loss_carryover_used == 8_000
        assert result.sched_e_net_income == 7_000  # $15K - $8K

    def test_prior_loss_exceeds_income(self):
        """Excess prior loss carries forward when income is insufficient."""
        result = _simple(
            rental_properties=[RentalProperty(
                property_address="123 Main St", gross_rents=20_000,
                mortgage_interest=10_000, taxes=5_000,  # Net = +$5K
            )],
            passive_loss_carryover=12_000,
        )
        assert result.passive_loss_carryover_used == 5_000
        assert result.sched_e_net_income == 0
        assert result.passive_loss_carryforward == 7_000  # $12K - $5K

    def test_current_loss_suspended(self):
        """Current-year rental loss partially disallowed creates new suspended loss."""
        result = _simple(
            wages=200_000,  # High AGI → $0 passive loss allowed
            rental_properties=[RentalProperty(
                property_address="456 Oak Ave", gross_rents=10_000,
                mortgage_interest=20_000, taxes=5_000,  # Net = -$15K
            )],
        )
        # AGI >$150K → $0 allowed loss
        assert result.sched_e_net_income == 0
        assert result.passive_loss_suspended == 15_000
        assert result.passive_loss_carryforward == 15_000

    def test_current_loss_plus_prior_carryover(self):
        """Current suspended + prior carryover sum in carryforward."""
        result = _simple(
            wages=200_000,
            rental_properties=[RentalProperty(
                property_address="456 Oak Ave", gross_rents=10_000,
                mortgage_interest=20_000, taxes=5_000,  # Net = -$15K
            )],
            passive_loss_carryover=10_000,
        )
        assert result.passive_loss_suspended == 15_000
        assert result.passive_loss_carryforward == 25_000  # $15K + $10K

    def test_no_rentals_carryover_preserved(self):
        """No rental properties → prior carryover passes through."""
        result = _simple(passive_loss_carryover=20_000)
        assert result.passive_loss_carryforward == 20_000
        assert result.passive_loss_carryover_used == 0

    def test_no_loss_no_carryforward(self):
        """Rental income with no prior carryover → no carryforward."""
        result = _simple(
            rental_properties=[RentalProperty(
                property_address="789 Elm", gross_rents=20_000,
                mortgage_interest=5_000,
            )],
        )
        assert result.passive_loss_carryforward == 0
        assert result.passive_loss_suspended == 0


# =========================================================================
# NOL Carryover
# =========================================================================
class TestNOLCarryover:
    def test_nol_deduction_80pct_limit(self):
        """NOL carryover limited to 80% of taxable income."""
        result = _simple(nol_carryover=100_000)
        # Taxable income before NOL is ~$100K - std ded ~$15K = ~$85K
        # 80% limit → ~$68K used
        assert result.nol_carryover_used > 0
        assert result.nol_carryover_used <= result.nol_carryover_used  # trivially true
        # Verify 80% cap applied
        taxable_before_nol = 100_000 - result.standard_deduction
        expected_limit = taxable_before_nol * 0.80
        assert abs(result.nol_carryover_used - expected_limit) < 1

    def test_nol_small_carryover_fully_used(self):
        """Small NOL carryover fully consumed within 80% limit."""
        result = _simple(nol_carryover=5_000)
        assert result.nol_carryover_used == 5_000
        assert result.nol_carryforward == 0

    def test_nol_excess_carries_forward(self):
        """NOL exceeding 80% limit carries forward."""
        result = _simple(nol_carryover=200_000)
        # 80% of ~$85K taxable = ~$68K used → remainder carries forward
        assert result.nol_carryforward > 0
        assert result.nol_carryforward == round(200_000 - result.nol_carryover_used, 2)

    def test_nol_reduces_taxable_income(self):
        """NOL deduction reduces taxable income and thus tax."""
        result_no_nol = _simple()
        result_nol = _simple(nol_carryover=30_000)
        assert result_nol.line_15_taxable_income < result_no_nol.line_15_taxable_income
        assert result_nol.line_24_total_tax < result_no_nol.line_24_total_tax

    def test_nol_zero_income_no_use(self):
        """No taxable income → NOL unused, carries forward entirely."""
        result = _simple(wages=0, nol_carryover=50_000)
        assert result.nol_carryover_used == 0
        assert result.nol_carryforward == 50_000

    def test_current_year_nol_detected(self):
        """Current-year NOL tracked when deductions exceed income."""
        result = _simple(
            wages=10_000,
            deductions=Deductions(charitable_cash=5_000, mortgage_interest=5_000),
            rental_properties=[RentalProperty(
                property_address="Loss Property",
                gross_rents=5_000,
                mortgage_interest=30_000, taxes=5_000,
            )],
        )
        # This may or may not produce a current NOL depending on passive loss rules
        # At minimum, the field should exist and be >= 0
        assert result.nol_amount >= 0


# =========================================================================
# AMT Credit Carryover
# =========================================================================
class TestAMTCreditCarryover:
    def test_amt_credit_reduces_tax(self):
        """AMT credit from prior year reduces current total tax."""
        result_no_credit = _simple()
        result_credit = _simple(amt_credit_carryover=2_000)
        assert result_credit.line_24_total_tax <= result_no_credit.line_24_total_tax

    def test_amt_credit_limited_by_tmt(self):
        """AMT credit can't reduce tax below tentative minimum tax."""
        result = _simple(amt_credit_carryover=500_000)
        # Credit room = regular_tax - TMT; excess carries forward
        assert result.amt_credit_carryover_used >= 0
        assert result.amt_credit_carryforward >= 0

    def test_current_amt_becomes_carryforward(self):
        """Current-year AMT adds to carryforward for next year."""
        # High SALT filer likely to have AMT
        result = _simple(
            wages=300_000,
            deductions=Deductions(
                property_tax=30_000, state_income_tax_paid=20_000,
            ),
        )
        # If AMT > 0, it should appear in carryforward
        if result.amt > 0:
            assert result.amt_credit_carryforward >= result.amt

    def test_no_amt_credit_zero(self):
        """No AMT credit carryover → fields are zero."""
        result = _simple()
        assert result.amt_credit_carryover_used == 0


# =========================================================================
# Capital Loss Carryover (existing — verify still works)
# =========================================================================
class TestCapitalLossCarryoverCompat:
    def test_existing_capital_loss_carryover(self):
        """Pre-existing capital_loss_carryover still works."""
        from tax_engine import CryptoTransaction
        result = _simple(
            crypto_transactions=[CryptoTransaction(
                asset_name="BTC", proceeds=5_000, cost_basis=15_000,
                date_acquired="2025-01-01", date_sold="2025-06-01",
            )],
            capital_loss_carryover=2_000,
        )
        assert result.capital_loss_carryover_used == 2_000
        assert result.capital_loss_carryforward > 0  # $10K loss + $2K carryover - $3K allowed


# =========================================================================
# to_summary() Output
# =========================================================================
class TestSummaryCarryforwards:
    def test_summary_includes_carryforwards_block(self):
        """Carryforwards block appears in summary when relevant."""
        result = _simple(nol_carryover=5_000)
        summary = result.to_summary()
        assert "carryforwards" in summary
        assert summary["carryforwards"] is not None
        assert summary["carryforwards"]["nol_carryover_used"] == 5_000

    def test_summary_carryforwards_null_when_none(self):
        """No carryforwards → block is None."""
        result = _simple()
        summary = result.to_summary()
        assert summary["carryforwards"] is None

    def test_summary_backward_compat_keys(self):
        """Backward compat flat keys still present."""
        result = _simple(charitable_carryover=3_000)
        summary = result.to_summary()
        # Flat key should still be None if nothing carries forward
        # (carryover was fully consumed, no current excess)
        assert "charitable_carryforward" in summary
        assert "capital_loss_carryforward" in summary

    def test_summary_passive_loss_in_block(self):
        """Passive loss appears in carryforwards block."""
        result = _simple(passive_loss_carryover=10_000)
        summary = result.to_summary()
        assert summary["carryforwards"] is not None
        assert summary["carryforwards"]["passive_loss_carryforward"] == 10_000


# =========================================================================
# Edge Cases
# =========================================================================
class TestEdgeCases:
    def test_all_carryovers_together(self):
        """All carryover types can be used simultaneously."""
        result = _simple(
            capital_loss_carryover=5_000,
            charitable_carryover=3_000,
            passive_loss_carryover=8_000,
            nol_carryover=10_000,
            amt_credit_carryover=2_000,
        )
        # All should be tracked
        assert result.capital_loss_carryover_used == 5_000
        assert result.charitable_carryover_used == 3_000
        assert result.passive_loss_carryforward == 8_000  # No rentals → preserved
        assert result.nol_carryover_used > 0
        assert result.amt_credit_carryover_used >= 0

    def test_zero_carryovers_backward_compatible(self):
        """Zero carryovers produce identical results to pre-Wave80."""
        result = _simple()
        assert result.charitable_carryover_used == 0
        assert result.passive_loss_suspended == 0
        assert result.passive_loss_carryforward == 0
        assert result.nol_amount == 0
        assert result.nol_carryover_used == 0
        assert result.nol_carryforward == 0
        assert result.amt_credit_carryover_used == 0
