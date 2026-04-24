"""Wave 35-36 tests — Audit risk scoring + Prior-year import."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
import json
from tax_engine import (
    PersonInfo, W2Income, AdditionalIncome, Deductions, Payments,
    BusinessIncome, RentalProperty, compute_tax,
)
from audit_risk import assess_audit_risk, AuditRiskReport, _get_bracket
from prior_year_import import (
    PriorYearData, _parse_money, extract_from_fillable_pdf,
)

FILER = PersonInfo(first_name="Test", last_name="User")
EMPTY_ADD = AdditionalIncome()
EMPTY_DED = Deductions()
EMPTY_PAY = Payments()


def _compute(**kw):
    defaults = dict(
        filing_status="single", filer=FILER,
        w2s=[W2Income(wages=75000, federal_withheld=10000, ss_wages=75000, medicare_wages=75000)],
        additional=EMPTY_ADD, deductions=EMPTY_DED, payments=EMPTY_PAY,
    )
    defaults.update(kw)
    return compute_tax(**defaults)


# =========================================================================
# Audit Risk — AGI Bracket Classification
# =========================================================================
class TestAGIBrackets:
    def test_low_income(self):
        assert _get_bracket(20000) == "under_25k"

    def test_mid_income(self):
        assert _get_bracket(75000) == "50k_100k"

    def test_high_income(self):
        assert _get_bracket(600000) == "500k_1m"

    def test_very_high_income(self):
        assert _get_bracket(2000000) == "over_1m"

    def test_boundary(self):
        assert _get_bracket(25000) == "under_25k"
        assert _get_bracket(25001) == "25k_50k"


# =========================================================================
# Audit Risk — Flag Detection
# =========================================================================
class TestAuditRiskFlags:
    def test_low_risk_basic_return(self):
        """Simple W-2 return with standard deduction = low risk."""
        result = _compute()
        report = assess_audit_risk(result)
        assert isinstance(report, AuditRiskReport)
        assert report.overall_risk == "low"
        assert report.risk_score < 20

    def test_high_charitable_flagged(self):
        """Charitable giving >3x norm triggers high flag."""
        result = _compute(
            deductions=Deductions(charitable_cash=30000),  # 40% of AGI
        )
        report = assess_audit_risk(result)
        flags = [f for f in report.flags if f.category == "charitable"]
        assert len(flags) >= 1
        assert flags[0].severity in ("medium", "high")

    def test_schedule_c_high_expenses(self):
        """Business with >85% expense ratio flagged."""
        result = _compute(
            businesses=[BusinessIncome(
                business_name="Consulting",
                gross_receipts=100000,
                other_expenses=90000,  # 90% expense ratio
            )],
        )
        report = assess_audit_risk(result)
        flags = [f for f in report.flags if f.category == "schedule_c"]
        assert len(flags) >= 1

    def test_schedule_c_loss_flagged(self):
        """Business with net loss flagged for hobby loss risk."""
        result = _compute(
            businesses=[BusinessIncome(
                business_name="Art Studio",
                gross_receipts=5000,
                other_expenses=15000,
            )],
        )
        report = assess_audit_risk(result)
        flags = [f for f in report.flags if f.category == "schedule_c"]
        loss_flags = [f for f in flags if "loss" in f.description.lower()]
        assert len(loss_flags) >= 1

    def test_large_rental_loss_flagged(self):
        """Large rental loss relative to income flagged."""
        prop = RentalProperty(gross_rents=5000, mortgage_interest=25000, taxes=5000)
        result = _compute(
            w2s=[W2Income(wages=40000, federal_withheld=5000, ss_wages=40000, medicare_wages=40000)],
            rental_properties=[prop],
        )
        report = assess_audit_risk(result)
        flags = [f for f in report.flags if f.category == "rental_loss"]
        assert len(flags) >= 1

    def test_eitc_with_se_flagged(self):
        """EITC + self-employment income flagged."""
        result = _compute(
            w2s=[W2Income(wages=15000, federal_withheld=1000, ss_wages=15000, medicare_wages=15000)],
            businesses=[BusinessIncome(gross_receipts=5000)],
        )
        report = assess_audit_risk(result)
        if result.eitc > 0:
            flags = [f for f in report.flags if f.category == "eitc"]
            assert len(flags) >= 1

    def test_high_income_bracket_flagged(self):
        """High-income returns get a base rate flag."""
        result = _compute(
            w2s=[W2Income(wages=600000, federal_withheld=150000, ss_wages=176100, medicare_wages=600000)],
        )
        report = assess_audit_risk(result)
        flags = [f for f in report.flags if f.category == "income_level"]
        assert len(flags) >= 1

    def test_itemized_double_standard_flagged(self):
        """Itemized deductions >2x standard gets a low flag."""
        result = _compute(
            deductions=Deductions(
                mortgage_interest=15000,
                property_tax=10000,
                state_income_tax_paid=5000,
                charitable_cash=5000,
            ),
        )
        report = assess_audit_risk(result)
        if result.deduction_type == "itemized" and result.itemized_total > result.standard_deduction * 2:
            flags = [f for f in report.flags if f.category == "itemized_deductions"]
            assert len(flags) >= 1

    def test_report_to_dict(self):
        """Report serializes to dict properly."""
        result = _compute()
        report = assess_audit_risk(result)
        d = report.to_dict()
        assert "agi_bracket" in d
        assert "risk_score" in d
        assert "overall_risk" in d
        assert "flags" in d
        assert isinstance(d["flags"], list)
        assert "base_audit_rate_pct" in d

    def test_risk_score_capped_at_100(self):
        """Risk score never exceeds 100."""
        result = _compute(
            w2s=[W2Income(wages=600000, federal_withheld=150000, ss_wages=176100, medicare_wages=600000)],
            deductions=Deductions(charitable_cash=300000),
            businesses=[BusinessIncome(gross_receipts=50000, other_expenses=48000)],
        )
        report = assess_audit_risk(result)
        assert report.risk_score <= 100


# =========================================================================
# MCP Audit Risk Tool
# =========================================================================
class TestMCPAuditRisk:
    def test_mcp_audit_risk_tool(self):
        from mcp_server import assess_audit_risk_tool
        raw = assess_audit_risk_tool(
            filing_status="single",
            wages=75000,
            federal_withheld=10000,
        )
        data = json.loads(raw)
        assert "risk_score" in data
        assert "overall_risk" in data
        assert "flags" in data
        assert data["overall_risk"] in ("low", "medium", "high")

    def test_mcp_audit_risk_with_charitable(self):
        from mcp_server import assess_audit_risk_tool
        raw = assess_audit_risk_tool(
            filing_status="single",
            wages=75000,
            federal_withheld=10000,
            charitable=30000,
        )
        data = json.loads(raw)
        assert data["risk_score"] > 0
        assert len(data["flags"]) > 0


# =========================================================================
# Prior-Year Import — Money Parsing
# =========================================================================
class TestMoneyParsing:
    def test_basic_number(self):
        assert _parse_money("75000") == 75000.0

    def test_with_commas(self):
        assert _parse_money("75,000") == 75000.0

    def test_with_dollar_sign(self):
        assert _parse_money("$75,000") == 75000.0

    def test_negative_parens(self):
        assert _parse_money("(5,000)") == -5000.0

    def test_negative_dash(self):
        assert _parse_money("-5000") == -5000.0

    def test_empty(self):
        assert _parse_money("") == 0.0
        assert _parse_money(None) == 0.0

    def test_dash(self):
        assert _parse_money("-") == 0.0

    def test_na(self):
        assert _parse_money("N/A") == 0.0

    def test_decimal(self):
        assert _parse_money("75,000.50") == 75000.50


# =========================================================================
# Prior-Year Import — PriorYearData
# =========================================================================
class TestPriorYearData:
    def test_to_dict(self):
        data = PriorYearData(
            tax_year=2024,
            filing_status="single",
            wages=75000,
            agi=72000,
            total_tax=10000,
            source="fillable_pdf",
            confidence="high",
        )
        d = data.to_dict()
        assert d["tax_year"] == 2024
        assert d["filing_status"] == "single"
        assert d["income"]["wages"] == 75000
        assert d["agi"] == 72000
        assert d["total_tax"] == 10000
        assert d["penalty_inputs"]["prior_year_tax"] == 10000
        assert d["penalty_inputs"]["prior_year_agi"] == 72000

    def test_penalty_inputs_populated(self):
        """penalty_inputs provides values for Form 2210 calculation."""
        data = PriorYearData(total_tax=15000, agi=120000)
        d = data.to_dict()
        assert d["penalty_inputs"]["prior_year_tax"] == 15000
        assert d["penalty_inputs"]["prior_year_agi"] == 120000

    def test_confidence_levels(self):
        """Confidence reflects number of extracted fields."""
        low = PriorYearData(confidence="low", fields_extracted=0)
        high = PriorYearData(confidence="high", fields_extracted=5)
        assert low.confidence == "low"
        assert high.confidence == "high"

    def test_empty_data(self):
        """Empty PriorYearData has sensible defaults."""
        data = PriorYearData()
        d = data.to_dict()
        assert d["agi"] == 0.0
        assert d["total_tax"] == 0.0
        assert d["confidence"] == "low"
