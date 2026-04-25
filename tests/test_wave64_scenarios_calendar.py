"""Wave 64 tests — Scenario Comparison API + Tax Calendar."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Tax Calendar
# =========================================================================
class TestTaxCalendar:
    def _read_main(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        return open(path).read()

    def test_calendar_endpoint_exists(self):
        src = self._read_main()
        assert "/tax-calendar" in src
        assert "async def tax_calendar" in src

    def test_federal_calendar_defined(self):
        src = self._read_main()
        assert "_TAX_CALENDAR_2025" in src

    def test_calendar_has_april_15(self):
        src = self._read_main()
        assert "2026-04-15" in src

    def test_calendar_has_estimated_dates(self):
        src = self._read_main()
        assert "2026-01-15" in src
        assert "2026-06-15" in src
        assert "2026-09-15" in src

    def test_state_deadlines_defined(self):
        src = self._read_main()
        assert "_STATE_DEADLINES" in src

    def test_state_deadlines_includes_10_states(self):
        src = self._read_main()
        for state in ["CA", "NY", "IL", "NJ", "PA", "GA", "NC", "OH", "TX", "FL"]:
            assert f'"{state}"' in src

    def test_no_income_tax_states_empty(self):
        src = self._read_main()
        # TX and FL have empty lists
        assert '"TX": []' in src
        assert '"FL": []' in src

    def test_calendar_skips_tenant_context(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "middleware", "tenant_context.py")
        src = open(path).read()
        assert "/tax-calendar" in src


# =========================================================================
# Scenario Comparison
# =========================================================================
class TestScenarioComparison:
    def _read_main(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        return open(path).read()

    def test_endpoint_exists(self):
        src = self._read_main()
        assert "/compare-scenarios" in src
        assert "async def compare_scenarios_api" in src

    def test_planning_tag(self):
        src = self._read_main()
        assert '"Planning"' in src

    def test_scenario_limit_validation(self):
        src = self._read_main()
        assert "at least 2 scenarios" in src
        assert "Maximum 4 scenarios" in src

    def test_scenario_result_fields(self):
        src = self._read_main()
        for field in ["total_income", "agi", "taxable_income", "total_tax",
                       "effective_rate", "marginal_rate", "refund", "owed"]:
            assert f'"{field}"' in src

    def test_delta_computation(self):
        src = self._read_main()
        assert "tax_delta" in src
        assert "refund_delta" in src

    def test_base_scenario_field(self):
        src = self._read_main()
        assert "base_scenario" in src

    def test_scenario_comparison_computes(self):
        """Test the comparison logic directly."""
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        results = []
        for wages in [80000, 100000]:
            filer = PersonInfo(first_name="Test", last_name="User")
            result = compute_tax(
                filing_status="single", filer=filer,
                w2s=[W2Income(wages=wages, federal_withheld=wages * 0.15)],
                deductions=Deductions(), additional=AdditionalIncome(),
                payments=Payments(),
            )
            results.append(result)
        assert results[1].line_24_total_tax > results[0].line_24_total_tax

    def test_filing_status_comparison(self):
        """Test that filing status affects outcome."""
        from tax_engine import PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax
        results = {}
        for status in ["single", "mfj"]:
            filer = PersonInfo(first_name="Test", last_name="User")
            result = compute_tax(
                filing_status=status, filer=filer,
                w2s=[W2Income(wages=120000, federal_withheld=18000)],
                deductions=Deductions(), additional=AdditionalIncome(),
                payments=Payments(),
            )
            results[status] = result
        # MFJ should have lower tax on same income
        assert results["mfj"].line_24_total_tax < results["single"].line_24_total_tax
