"""Unit tests for TaxLens MCP tool handlers.

Tests the handler functions directly (not via HTTP transport).
Run: PYTHONPATH=app pytest tests/test_mcp_tools.py -v
"""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from mcp_server import (
    compute_tax_scenario, compare_scenarios, estimate_impact,
    optimize_deductions, list_states, _build_inputs,
)


class TestComputeTaxScenario:
    def test_single_basic(self):
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=75000, federal_withheld=10000,
        ))
        assert result["filing_status"] == "single"
        assert result["total_income"] == 75000
        assert result["agi"] == 75000
        assert result["federal_tax"] > 0
        assert result["draft_id"]

    def test_mfj_with_dependents(self):
        result = json.loads(compute_tax_scenario(
            filing_status="mfj", wages=120000, federal_withheld=15000,
            num_dependents=2,
        ))
        assert result["filing_status"] == "mfj"
        assert result["net_refund"] > result.get("net_refund_no_ctc", -999)  # CTC helps

    def test_with_investments(self):
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=60000, federal_withheld=8000,
            ordinary_dividends=3000, qualified_dividends=2000,
            long_term_gains=5000, interest=1000,
        ))
        assert result["total_income"] > 60000
        assert result["agi"] > 60000

    def test_business_income(self):
        result = json.loads(compute_tax_scenario(
            filing_status="single", business_income=80000, business_expenses=20000,
        ))
        assert result["business_income"] == 60000  # gross - expenses
        assert result["se_tax"] > 0

    def test_ca_state_tax(self):
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=100000, federal_withheld=15000,
            residence_state="CA",
        ))
        assert len(result["state_taxes"]) == 1
        assert result["state_taxes"][0]["state"] == "CA"
        assert result["state_taxes"][0]["tax"] > 0

    def test_tx_no_state_tax(self):
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=100000, residence_state="TX",
        ))
        assert result["state_taxes"] == []

    def test_deductions(self):
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=100000,
            mortgage_interest=15000, property_tax=8000, charitable=5000,
        ))
        assert result["deduction_type"] == "itemized"

    def test_invalid_status(self):
        with pytest.raises(ValueError):
            compute_tax_scenario(filing_status="invalid", wages=50000)


class TestCompareScenarios:
    def test_single_vs_mfj(self):
        result = json.loads(compare_scenarios([
            {"filing_status": "single", "wages": 95000, "label": "Single"},
            {"filing_status": "mfj", "wages": 95000, "label": "MFJ"},
        ]))
        assert len(result["scenarios"]) == 2
        assert result["scenarios"][0]["scenario_label"] == "Single"
        assert result["scenarios"][1]["scenario_label"] == "MFJ"
        assert "recommendation" in result
        assert "comparison" in result
        # MFJ should have lower tax on same income
        assert result["scenarios"][1]["federal_tax"] < result["scenarios"][0]["federal_tax"]

    def test_state_comparison(self):
        result = json.loads(compare_scenarios([
            {"filing_status": "single", "wages": 100000, "residence_state": "CA", "label": "CA"},
            {"filing_status": "single", "wages": 100000, "residence_state": "TX", "label": "TX"},
        ]))
        assert len(result["scenarios"]) == 2
        # TX resident should have better net_refund (no state tax)
        tx_refund = result["scenarios"][1]["net_refund"]
        ca_refund = result["scenarios"][0]["net_refund"]
        assert tx_refund > ca_refund


class TestEstimateImpact:
    def test_raise_impact(self):
        result = json.loads(estimate_impact(
            base_scenario={"filing_status": "single", "wages": 80000},
            change_description="$10K raise",
            changes={"wages": 90000},
        ))
        assert result["change"] == "$10K raise"
        assert result["deltas"]["total_income"] == 10000
        assert result["deltas"]["federal_tax"] > 0
        assert "effective_marginal_rate" in result

    def test_new_business(self):
        result = json.loads(estimate_impact(
            base_scenario={"filing_status": "single", "wages": 60000},
            change_description="Start freelancing",
            changes={"business_income": 20000, "business_expenses": 5000},
        ))
        assert result["deltas"]["total_income"] > 0
        assert result["deltas"]["se_tax"] > 0


class TestOptimizeDeductions:
    def test_itemized_better(self):
        result = json.loads(optimize_deductions(
            filing_status="single", wages=100000,
            mortgage_interest=15000, property_tax=8000, charitable=5000,
        ))
        assert result["optimal_choice"] == "itemized"
        assert result["savings_from_optimal"] > 0
        assert "Itemize" in result["recommendation"]

    def test_standard_better(self):
        result = json.loads(optimize_deductions(
            filing_status="single", wages=50000,
            mortgage_interest=2000, property_tax=1500,
        ))
        assert result["optimal_choice"] == "standard"
        assert "standard deduction" in result["recommendation"]


class TestListStates:
    def test_all_states(self):
        result = json.loads(list_states())
        assert result["count"] == 10
        codes = [s["code"] for s in result["supported_states"]]
        assert "IL" in codes
        assert "CA" in codes
        assert "TX" in codes

    def test_tax_types(self):
        result = json.loads(list_states())
        states = {s["code"]: s for s in result["supported_states"]}
        assert states["IL"]["tax_type"] == "flat"
        assert states["CA"]["tax_type"] == "graduated"
        assert states["TX"]["tax_type"] == "none"
        assert "rate" in states["IL"]
        assert "top_rate" in states["CA"]


class TestBuildInputs:
    def test_basic(self):
        inputs = _build_inputs(filing_status="single", wages=50000)
        assert inputs["filing_status"] == "single"
        assert len(inputs["w2s"]) == 1
        assert inputs["w2s"][0].wages == 50000

    def test_no_wages(self):
        inputs = _build_inputs(filing_status="single")
        assert len(inputs["w2s"]) == 0

    def test_capital_gains(self):
        inputs = _build_inputs(filing_status="single", long_term_gains=5000, short_term_gains=-1000)
        txns = inputs["additional"].capital_transactions
        assert len(txns) == 2
        # Long-term: proceeds=5000, cost=0
        lt = [t for t in txns if t.is_long_term][0]
        assert lt.proceeds == 5000
        # Short-term: proceeds=0, cost=1000 (loss)
        st = [t for t in txns if not t.is_long_term][0]
        assert st.cost_basis == 1000
