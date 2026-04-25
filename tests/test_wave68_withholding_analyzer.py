"""Wave 68 tests — Withholding Analyzer / W-4 Recommendations."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Basic Analysis
# =========================================================================
class TestBasicAnalysis:
    def test_returns_result(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=80000,
            federal_withheld_ytd=6000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        assert result.projected_tax > 0
        assert result.projected_withholding > 0

    def test_projected_withholding_extrapolated(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=80000,
            federal_withheld_ytd=6000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        # 6000/13 * 26 = 12000
        assert abs(result.projected_withholding - 12000) < 1

    def test_gap_positive_when_underpaid(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=150000,
            federal_withheld_ytd=5000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        assert result.gap > 0
        assert "Underpaid" in result.gap_description

    def test_gap_negative_when_overpaid(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=50000,
            federal_withheld_ytd=10000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        assert result.gap < 0
        assert "Overpaid" in result.gap_description

    def test_on_target(self):
        """Withholding approximately matching tax produces neutral message."""
        from withholding_analyzer import WithholdingInput, analyze_withholding
        # ~$9,214 tax on $80k single.  Withhold 9214/26*13 = ~4607 YTD
        inp = WithholdingInput(
            annual_wages=80000,
            federal_withheld_ytd=4607,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        assert abs(result.gap) < 200
        assert "on target" in result.gap_description.lower() or "on track" in result.gap_description.lower()


# =========================================================================
# W-4 Recommendations
# =========================================================================
class TestW4Recommendations:
    def test_recommends_extra_when_underpaid(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=120000,
            federal_withheld_ytd=5000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        assert result.recommended_extra_per_period > 0
        assert result.remaining_periods == 13
        assert "Add" in result.adjustment_description

    def test_no_adjustment_when_overpaid(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=50000,
            federal_withheld_ytd=10000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        assert result.recommended_extra_per_period == 0
        assert "reduce" in result.adjustment_description.lower()

    def test_target_refund_mode(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=80000,
            federal_withheld_ytd=4000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
            target_refund=2000,
        )
        result = analyze_withholding(inp)
        assert result.target_refund == 2000
        # target_withholding = tax + 2000
        assert result.target_withholding > result.projected_tax


# =========================================================================
# Penalty Detection
# =========================================================================
class TestPenalty:
    def test_penalty_risk_when_severely_underpaid(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=200000,
            federal_withheld_ytd=2000,
            pay_periods_per_year=26,
            pay_periods_elapsed=20,
        )
        result = analyze_withholding(inp)
        assert result.at_risk_of_penalty is True

    def test_no_penalty_risk_when_close(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(
            annual_wages=60000,
            federal_withheld_ytd=4000,
            pay_periods_per_year=26,
            pay_periods_elapsed=13,
        )
        result = analyze_withholding(inp)
        assert result.at_risk_of_penalty is False

    def test_safe_harbor_higher_for_high_income(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        low = WithholdingInput(annual_wages=60000, federal_withheld_ytd=3000,
                               pay_periods_per_year=26, pay_periods_elapsed=13)
        high = WithholdingInput(annual_wages=200000, federal_withheld_ytd=10000,
                                pay_periods_per_year=26, pay_periods_elapsed=13)
        r_low = analyze_withholding(low)
        r_high = analyze_withholding(high)
        # High income uses 110% safe harbor
        assert r_high.safe_harbor_amount > r_high.projected_tax


# =========================================================================
# Rate Calculations
# =========================================================================
class TestRates:
    def test_effective_rate_reasonable(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(annual_wages=80000, federal_withheld_ytd=6000,
                               pay_periods_per_year=26, pay_periods_elapsed=13)
        result = analyze_withholding(inp)
        assert 0.05 < result.effective_rate < 0.30

    def test_marginal_rate_for_80k(self):
        from withholding_analyzer import WithholdingInput, analyze_withholding
        inp = WithholdingInput(annual_wages=80000, federal_withheld_ytd=6000,
                               pay_periods_per_year=26, pay_periods_elapsed=13)
        result = analyze_withholding(inp)
        assert result.marginal_rate == 0.22  # 22% bracket


# =========================================================================
# Endpoint
# =========================================================================
class TestEndpoint:
    def test_withholding_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/withholding-check" in src
        assert "async def withholding_check" in src

    def test_analyzer_module_callable(self):
        from withholding_analyzer import analyze_withholding, WithholdingInput
        assert callable(analyze_withholding)
