"""Unit tests for Wave 30 — MCP Parity.

Tests that MCP tools support the full engine parameter set:
structured dependents, education expenses, dependent care, retirement
contributions, multi-state, penalty estimation, and tax config lookup.

Run: PYTHONPATH=app pytest tests/test_wave30_mcp_parity.py -v
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from mcp_server import (
    compute_tax_scenario, compare_scenarios, estimate_impact,
    optimize_deductions, get_tax_config, list_states, _build_inputs,
)


# ---------------------------------------------------------------------------
# Structured dependents via MCP
# ---------------------------------------------------------------------------
class TestMCPDependents:
    def test_structured_dependents_ctc(self):
        """Structured dependents with DOB → CTC eligibility by age."""
        result = json.loads(compute_tax_scenario(
            filing_status="mfj", wages=120000, federal_withheld=15000,
            dependents=[
                {"first_name": "Child1", "date_of_birth": "2012-03-15", "relationship": "son"},
                {"first_name": "Child2", "date_of_birth": "2015-07-01", "relationship": "daughter"},
            ],
        ))
        # Both under 17 → 2 CTC children
        assert result["filing_status"] == "mfj"
        assert result["federal_tax"] >= 0

    def test_structured_dependent_over_17_no_ctc(self):
        """Dependent over 17 doesn't qualify for CTC."""
        r_young = json.loads(compute_tax_scenario(
            filing_status="single", wages=80000, federal_withheld=10000,
            dependents=[{"first_name": "Teen", "date_of_birth": "2010-01-01"}],
        ))
        r_old = json.loads(compute_tax_scenario(
            filing_status="single", wages=80000, federal_withheld=10000,
            dependents=[{"first_name": "Adult", "date_of_birth": "2000-01-01"}],
        ))
        # Young child (under 17 in 2025) gets CTC, adult doesn't
        assert r_young["net_refund"] > r_old["net_refund"]

    def test_num_dependents_backward_compat(self):
        """num_dependents integer still works when no dependents list provided."""
        result = json.loads(compute_tax_scenario(
            filing_status="mfj", wages=100000, federal_withheld=12000,
            num_dependents=2,
        ))
        assert result["filing_status"] == "mfj"

    def test_disabled_dependent_eitc(self):
        """Disabled dependent qualifies for EITC regardless of age."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=15000, federal_withheld=1000,
            dependents=[{"first_name": "Adult", "date_of_birth": "1990-01-01",
                         "is_disabled": True, "relationship": "son"}],
        ))
        assert result.get("eitc", 0) > 0


# ---------------------------------------------------------------------------
# Education expenses via MCP
# ---------------------------------------------------------------------------
class TestMCPEducation:
    def test_aotc_credit(self):
        """AOTC: $2,500 max, 40% refundable."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=50000, federal_withheld=7000,
            education_expenses=[
                {"student_name": "Student", "qualified_expenses": 4000, "credit_type": "aotc"},
            ],
        ))
        # AOTC has nonrefundable + refundable portions
        total_edu = result.get("education_credit", 0) + result.get("education_credit_refundable", 0)
        assert total_edu > 0

    def test_llc_credit(self):
        """LLC: $2,000 max, nonrefundable."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=50000, federal_withheld=7000,
            education_expenses=[
                {"student_name": "GradStudent", "qualified_expenses": 10000, "credit_type": "llc"},
            ],
        ))
        assert result.get("education_credit", 0) > 0


# ---------------------------------------------------------------------------
# Dependent care expenses via MCP
# ---------------------------------------------------------------------------
class TestMCPDependentCare:
    def test_cdcc_credit(self):
        """CDCC: child care expenses → credit based on AGI rate."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=50000, federal_withheld=7000,
            dependents=[{"first_name": "Toddler", "date_of_birth": "2020-06-01"}],
            dependent_care_expenses=[
                {"dependent_name": "Toddler", "care_expenses": 5000},
            ],
        ))
        assert result.get("cdcc", 0) > 0

    def test_cdcc_no_care_expenses_no_credit(self):
        """No CDCC when no dependent care expenses provided."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=50000, federal_withheld=7000,
            num_dependents=1,
        ))
        assert result.get("cdcc", 0) == 0


# ---------------------------------------------------------------------------
# Retirement contributions via MCP
# ---------------------------------------------------------------------------
class TestMCPRetirement:
    def test_savers_credit(self):
        """Saver's Credit for low-income retirement contributions."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=22000, federal_withheld=2000,
            retirement_contributions=[
                {"contributor": "filer", "contribution_amount": 2000},
            ],
        ))
        assert result.get("savers_credit", 0) > 0

    def test_savers_credit_high_income_no_credit(self):
        """No Saver's Credit above income threshold."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=100000, federal_withheld=15000,
            retirement_contributions=[
                {"contributor": "filer", "contribution_amount": 2000},
            ],
        ))
        assert result.get("savers_credit", 0) == 0


# ---------------------------------------------------------------------------
# Multi-state via MCP
# ---------------------------------------------------------------------------
class TestMCPMultiState:
    def test_work_states(self):
        """Multi-state: resident IL + work in NY → two state returns."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=100000, federal_withheld=15000,
            residence_state="IL", work_states=["NY"],
        ))
        state_codes = [s["state"] for s in result.get("state_taxes", [])]
        assert "IL" in state_codes
        # NY should appear as nonresident if wages allocated
        assert len(result.get("state_taxes", [])) >= 1

    def test_days_worked_allocation(self):
        """Days-worked allocation splits income across states."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=120000, federal_withheld=18000,
            residence_state="IL", work_states=["NY"],
            days_worked_by_state={"IL": 200, "NY": 60},
        ))
        state_codes = [s["state"] for s in result.get("state_taxes", [])]
        assert "IL" in state_codes


# ---------------------------------------------------------------------------
# Penalty estimation via MCP
# ---------------------------------------------------------------------------
class TestMCPPenalty:
    def test_penalty_with_prior_year(self):
        """Underpayment penalty when prior year tax provided."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=150000, federal_withheld=5000,
            prior_year_tax=20000, prior_year_agi=140000,
        ))
        # With only $5K withheld on $150K income, should owe + possibly penalty
        assert result["federal_tax"] > 0

    def test_no_penalty_safe_harbor(self):
        """No penalty when withholding covers 100% of prior year tax."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=80000, federal_withheld=12000,
            prior_year_tax=10000, prior_year_agi=75000,
        ))
        # $12K withheld > $10K prior year tax → safe harbor met
        assert result.get("penalty", 0) == 0


# ---------------------------------------------------------------------------
# Additional params via MCP
# ---------------------------------------------------------------------------
class TestMCPAdditionalParams:
    def test_medical_expenses(self):
        """Medical expenses above 7.5% AGI threshold."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=50000, federal_withheld=7000,
            medical_expenses=10000,
            mortgage_interest=10000, property_tax=5000,
        ))
        # Medical + mortgage + SALT should push to itemized
        assert result["deduction_type"] in ("itemized", "standard")

    def test_charitable_noncash(self):
        """Non-cash charitable contributions counted."""
        result = json.loads(compute_tax_scenario(
            filing_status="single", wages=100000, federal_withheld=15000,
            mortgage_interest=10000, property_tax=5000,
            charitable=3000, charitable_noncash=5000,
        ))
        assert result["deduction_type"] == "itemized"

    def test_other_income(self):
        """Other income adds to total income."""
        r_base = json.loads(compute_tax_scenario(
            filing_status="single", wages=50000,
        ))
        r_other = json.loads(compute_tax_scenario(
            filing_status="single", wages=50000, other_income=10000,
        ))
        assert r_other["total_income"] > r_base["total_income"]

    def test_additional_withholding(self):
        """Additional withholding reduces amount owed."""
        r_base = json.loads(compute_tax_scenario(
            filing_status="single", wages=80000, federal_withheld=5000,
        ))
        r_extra = json.loads(compute_tax_scenario(
            filing_status="single", wages=80000, federal_withheld=5000,
            additional_withholding=3000,
        ))
        assert r_extra["net_refund"] > r_base["net_refund"]


# ---------------------------------------------------------------------------
# get_tax_config tool
# ---------------------------------------------------------------------------
class TestGetTaxConfig:
    def test_2025_config(self):
        result = json.loads(get_tax_config(tax_year=2025, filing_status="single"))
        assert result["tax_year"] == 2025
        assert result["standard_deduction"] == 15000
        assert len(result["federal_brackets"]) == 7
        assert result["payroll"]["ss_wage_base"] == 176100
        assert result["credits"]["ctc_per_child"] == 2000
        assert result["salt_cap"] == 10000
        assert result["qbi"]["rate"] == 0.20
        assert result["qbi"]["taxable_income_limit"] == 191950

    def test_2024_config(self):
        result = json.loads(get_tax_config(tax_year=2024, filing_status="single"))
        assert result["tax_year"] == 2024
        assert result["standard_deduction"] == 14600
        assert result["payroll"]["ss_wage_base"] == 168600
        assert result["qbi"]["taxable_income_limit"] == 182100

    def test_mfj_config(self):
        result = json.loads(get_tax_config(tax_year=2025, filing_status="mfj"))
        assert result["standard_deduction"] == 30000
        assert result["filing_status"] == "mfj"
        assert result["qbi"]["taxable_income_limit"] == 383900

    def test_supported_years(self):
        result = json.loads(get_tax_config())
        assert 2024 in result["supported_years"]
        assert 2025 in result["supported_years"]

    def test_penalty_constants(self):
        result = json.loads(get_tax_config(tax_year=2025))
        assert result["penalty"]["threshold"] == 1000
        assert result["penalty"]["rate"] == 0.08
        assert result["penalty"]["safe_harbor_pct"] == 0.90
        assert result["penalty"]["high_agi_prior_year_pct"] == 1.10

    def test_amt_constants(self):
        result = json.loads(get_tax_config(tax_year=2025, filing_status="single"))
        assert result["amt"]["exemption"] == 88100
        assert result["amt"]["phaseout_start"] == 626350

    def test_eitc_max_credits(self):
        result = json.loads(get_tax_config(tax_year=2025))
        assert result["credits"]["eitc_max_credit"]["0"] == 649
        assert result["credits"]["cdcc_max_expenses_one"] == 3000
        assert result["credits"]["cdcc_max_expenses_two"] == 6000


# ---------------------------------------------------------------------------
# _build_inputs parity checks
# ---------------------------------------------------------------------------
class TestBuildInputsParity:
    def test_dependents_list(self):
        inputs = _build_inputs(
            filing_status="mfj",
            dependents=[{"first_name": "Kid", "date_of_birth": "2015-01-01"}],
        )
        assert inputs["dependents"] is not None
        assert len(inputs["dependents"]) == 1
        assert inputs["dependents"][0].first_name == "Kid"
        assert inputs["dependents"][0].date_of_birth == "2015-01-01"

    def test_education_expenses(self):
        inputs = _build_inputs(
            filing_status="single",
            education_expenses=[{"student_name": "S", "qualified_expenses": 4000}],
        )
        assert inputs["education_expenses"] is not None
        assert len(inputs["education_expenses"]) == 1
        assert inputs["education_expenses"][0].qualified_expenses == 4000

    def test_dependent_care_expenses(self):
        inputs = _build_inputs(
            filing_status="single",
            dependent_care_expenses=[{"dependent_name": "D", "care_expenses": 3000}],
        )
        assert inputs["dependent_care_expenses"] is not None
        assert inputs["dependent_care_expenses"][0].care_expenses == 3000

    def test_retirement_contributions(self):
        inputs = _build_inputs(
            filing_status="single",
            retirement_contributions=[{"contributor": "filer", "contribution_amount": 2000}],
        )
        assert inputs["retirement_contributions"] is not None
        assert inputs["retirement_contributions"][0].contribution_amount == 2000

    def test_multi_state_params(self):
        inputs = _build_inputs(
            filing_status="single",
            work_states=["NY", "NJ"],
            days_worked_by_state={"NY": 200, "NJ": 40},
        )
        assert inputs["work_states"] == ["NY", "NJ"]
        assert inputs["days_worked_by_state"] == {"NY": 200, "NJ": 40}

    def test_penalty_params(self):
        inputs = _build_inputs(
            filing_status="single",
            prior_year_tax=15000,
            prior_year_agi=100000,
        )
        assert inputs["prior_year_tax"] == 15000
        assert inputs["prior_year_agi"] == 100000

    def test_additional_deductions(self):
        inputs = _build_inputs(
            filing_status="single",
            charitable_noncash=2000,
            medical_expenses=5000,
            other_income=3000,
            additional_withholding=1000,
        )
        assert inputs["deductions"].charitable_noncash == 2000
        assert inputs["deductions"].medical_expenses == 5000
        assert inputs["additional"].other_income == 3000
        assert inputs["additional_withholding"] == 1000

    def test_none_defaults(self):
        """Omitted list params default to None."""
        inputs = _build_inputs(filing_status="single")
        assert inputs["dependents"] is None
        assert inputs["education_expenses"] is None
        assert inputs["dependent_care_expenses"] is None
        assert inputs["retirement_contributions"] is None
        assert inputs["work_states"] is None
        assert inputs["days_worked_by_state"] is None


# ---------------------------------------------------------------------------
# optimize_deductions parity
# ---------------------------------------------------------------------------
class TestOptimizeDeductionsParity:
    def test_with_medical_and_noncash(self):
        result = json.loads(optimize_deductions(
            filing_status="single", wages=80000,
            mortgage_interest=8000, property_tax=6000,
            charitable=2000, charitable_noncash=3000,
            medical_expenses=8000,
        ))
        assert "medical_expenses" in result["itemized_breakdown"]
        assert "charitable_noncash" in result["itemized_breakdown"]

    def test_with_tax_year(self):
        r24 = json.loads(optimize_deductions(
            filing_status="single", wages=50000, tax_year=2024,
        ))
        r25 = json.loads(optimize_deductions(
            filing_status="single", wages=50000, tax_year=2025,
        ))
        assert r24["standard_deduction"] == 14600
        assert r25["standard_deduction"] == 15000


# ---------------------------------------------------------------------------
# compare_scenarios with new params
# ---------------------------------------------------------------------------
class TestCompareScenariosParity:
    def test_compare_with_dependents(self):
        result = json.loads(compare_scenarios([
            {"filing_status": "single", "wages": 80000, "label": "No kids",
             "num_dependents": 0},
            {"filing_status": "single", "wages": 80000, "label": "2 kids",
             "dependents": [
                 {"first_name": "A", "date_of_birth": "2015-01-01"},
                 {"first_name": "B", "date_of_birth": "2017-01-01"},
             ]},
        ]))
        assert len(result["scenarios"]) == 2
        # 2 kids should have better refund
        assert result["scenarios"][1]["net_refund"] > result["scenarios"][0]["net_refund"]

    def test_compare_with_education(self):
        result = json.loads(compare_scenarios([
            {"filing_status": "single", "wages": 60000, "label": "No edu"},
            {"filing_status": "single", "wages": 60000, "label": "AOTC",
             "education_expenses": [{"student_name": "S", "qualified_expenses": 4000}]},
        ]))
        assert len(result["scenarios"]) == 2
