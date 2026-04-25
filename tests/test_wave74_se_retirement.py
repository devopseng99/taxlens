"""Wave 74 tests — Self-Employed Retirement Plans (Schedule 1 Line 16)."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    compute_tax, PersonInfo, W2Income, BusinessIncome, Deductions,
    AdditionalIncome, Payments, SelfEmployedRetirement,
)
from tax_config import get_year_config


# Helper: basic self-employed filer
def _se_filer(net_profit=100_000, se_retirement=None, tax_year=2025):
    return compute_tax(
        filing_status="single",
        filer=PersonInfo(first_name="Test", last_name="SE"),
        w2s=[],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
        businesses=[BusinessIncome(gross_receipts=net_profit * 1.3, other_expenses=net_profit * 0.3)],
        se_retirement_contributions=se_retirement,
        tax_year=tax_year,
    )


# =========================================================================
# SEP-IRA
# =========================================================================
class TestSEPIRA:
    def test_sep_basic_deduction(self):
        """SEP-IRA: 25% of net SE income, deducted above-the-line."""
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=15_000)]
        result = _se_filer(net_profit=100_000, se_retirement=contrib)
        assert result.se_retirement_deduction == 15_000
        assert result.se_retirement_plan_type == "sep_ira"
        assert result.se_retirement_excess == 0

    def test_sep_capped_at_25_pct(self):
        """SEP-IRA contribution exceeding 25% of net SE income is capped."""
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=50_000)]
        result = _se_filer(net_profit=100_000, se_retirement=contrib)
        # Net SE income = profit - 50% of SE tax
        # SE tax = profit * 0.9235 * 0.153 ≈ 14,130
        # Net SE income ≈ 100,000 - 7,065 = 92,935
        # 25% of 92,935 ≈ 23,234
        assert result.se_retirement_deduction < 50_000  # Capped
        assert result.se_retirement_excess > 0
        # Limit should be roughly 25% of (profit - 50% SE tax)
        expected_limit = (100_000 - result.se_tax * 0.5) * 0.25
        assert abs(result.se_retirement_limit - expected_limit) < 1

    def test_sep_dollar_cap(self):
        """SEP-IRA capped at dollar limit for very high earners."""
        c = get_year_config(2025)
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=c.SEP_IRA_LIMIT)]
        result = _se_filer(net_profit=500_000, se_retirement=contrib)
        assert result.se_retirement_deduction == c.SEP_IRA_LIMIT

    def test_sep_does_not_reduce_se_tax(self):
        """CRITICAL: SEP-IRA deduction must NOT reduce SE tax."""
        result_without = _se_filer(net_profit=100_000)
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=15_000)]
        result_with = _se_filer(net_profit=100_000, se_retirement=contrib)
        # SE tax must be IDENTICAL with and without retirement contribution
        assert result_with.se_tax == result_without.se_tax
        assert result_with.sched_se_total == result_without.sched_se_total
        # But AGI should be lower (deduction reduces income tax, not SE tax)
        assert result_with.line_11_agi < result_without.line_11_agi
        assert result_with.line_11_agi == pytest.approx(
            result_without.line_11_agi - 15_000, abs=1
        )


# =========================================================================
# Solo 401(k)
# =========================================================================
class TestSolo401k:
    def test_solo_basic(self):
        """Solo 401(k) basic deduction within limits."""
        contrib = [SelfEmployedRetirement(plan_type="solo_401k", contribution_amount=20_000)]
        result = _se_filer(net_profit=100_000, se_retirement=contrib)
        assert result.se_retirement_deduction == 20_000
        assert result.se_retirement_plan_type == "solo_401k"

    def test_solo_with_catchup(self):
        """Solo 401(k) with age 50+ catch-up."""
        c = get_year_config(2025)
        # Employee deferral limit + catch-up
        employee_max = c.SOLO_401K_EMPLOYEE_LIMIT + c.SOLO_401K_CATCHUP
        contrib = [SelfEmployedRetirement(
            plan_type="solo_401k", contribution_amount=employee_max, age_50_plus=True
        )]
        result = _se_filer(net_profit=200_000, se_retirement=contrib)
        assert result.se_retirement_deduction == employee_max

    def test_solo_total_limit(self):
        """Solo 401(k) total capped at annual limit."""
        c = get_year_config(2025)
        # Try to contribute more than total limit
        contrib = [SelfEmployedRetirement(
            plan_type="solo_401k", contribution_amount=c.SOLO_401K_TOTAL_LIMIT + 10_000
        )]
        result = _se_filer(net_profit=500_000, se_retirement=contrib)
        assert result.se_retirement_deduction <= c.SOLO_401K_TOTAL_LIMIT
        assert result.se_retirement_excess > 0

    def test_solo_does_not_reduce_se_tax(self):
        """Solo 401(k) deduction must NOT reduce SE tax."""
        result_without = _se_filer(net_profit=150_000)
        contrib = [SelfEmployedRetirement(plan_type="solo_401k", contribution_amount=30_000)]
        result_with = _se_filer(net_profit=150_000, se_retirement=contrib)
        assert result_with.se_tax == result_without.se_tax


# =========================================================================
# SIMPLE IRA
# =========================================================================
class TestSimpleIRA:
    def test_simple_basic(self):
        """SIMPLE IRA basic deduction."""
        contrib = [SelfEmployedRetirement(plan_type="simple_ira", contribution_amount=10_000)]
        result = _se_filer(net_profit=100_000, se_retirement=contrib)
        assert result.se_retirement_deduction == 10_000

    def test_simple_with_catchup(self):
        """SIMPLE IRA with age 50+ catch-up."""
        c = get_year_config(2025)
        max_employee = c.SIMPLE_IRA_LIMIT + c.SIMPLE_IRA_CATCHUP
        contrib = [SelfEmployedRetirement(
            plan_type="simple_ira", contribution_amount=max_employee, age_50_plus=True
        )]
        result = _se_filer(net_profit=200_000, se_retirement=contrib)
        assert result.se_retirement_deduction == max_employee


# =========================================================================
# Edge Cases
# =========================================================================
class TestEdgeCases:
    def test_no_se_income_no_deduction(self):
        """No Schedule C profit → no SE retirement deduction (even if contributed)."""
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=10_000)]
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="W2", last_name="Only"),
            w2s=[W2Income(wages=80_000, federal_withheld=10_000, ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            se_retirement_contributions=contrib,
        )
        assert result.se_retirement_deduction == 0

    def test_backward_compatible(self):
        """No se_retirement_contributions = same as before."""
        result = _se_filer(net_profit=100_000, se_retirement=None)
        assert result.se_retirement_deduction == 0
        assert result.se_retirement_plan_type == ""

    def test_schedule_1_generated(self):
        """SE retirement deduction triggers Schedule 1."""
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=10_000)]
        result = _se_filer(net_profit=100_000, se_retirement=contrib)
        assert "Schedule 1" in result.forms_generated

    def test_reduces_taxable_income(self):
        """SE retirement deduction reduces taxable income."""
        result_without = _se_filer(net_profit=100_000)
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=15_000)]
        result_with = _se_filer(net_profit=100_000, se_retirement=contrib)
        assert result_with.line_15_taxable_income < result_without.line_15_taxable_income

    def test_2024_limits(self):
        """2024 limits are different from 2025."""
        c24 = get_year_config(2024)
        c25 = get_year_config(2025)
        assert c24.SOLO_401K_EMPLOYEE_LIMIT == 23_000
        assert c25.SOLO_401K_EMPLOYEE_LIMIT == 23_500
        assert c24.SOLO_401K_TOTAL_LIMIT == 69_000
        assert c25.SOLO_401K_TOTAL_LIMIT == 70_000
        assert c24.SEP_IRA_LIMIT == 69_000
        assert c25.SEP_IRA_LIMIT == 70_000

    def test_excess_tracked(self):
        """Excess contributions over limit are tracked."""
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=80_000)]
        result = _se_filer(net_profit=100_000, se_retirement=contrib)
        assert result.se_retirement_excess > 0
        assert result.se_retirement_contribution == 80_000


# =========================================================================
# Tax Impact Verification
# =========================================================================
class TestTaxImpact:
    def test_income_tax_reduced(self):
        """SE retirement deduction reduces income tax (line 16 tax)."""
        result_without = _se_filer(net_profit=150_000)
        contrib = [SelfEmployedRetirement(plan_type="solo_401k", contribution_amount=25_000)]
        result_with = _se_filer(net_profit=150_000, se_retirement=contrib)
        assert result_with.line_16_tax < result_without.line_16_tax

    def test_combined_with_ira(self):
        """SE retirement + traditional IRA both deductible (separate limits)."""
        from tax_engine import IRAContribution
        contrib = [SelfEmployedRetirement(plan_type="sep_ira", contribution_amount=15_000)]
        ira = [IRAContribution(contribution_amount=7_000)]
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="Both"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            businesses=[BusinessIncome(gross_receipts=130_000, other_expenses=30_000)],
            se_retirement_contributions=contrib,
            ira_contributions=ira,
        )
        assert result.se_retirement_deduction == 15_000
        # IRA may be phased out due to active plan participation, but SE retirement is always allowed
        assert result.se_retirement_deduction > 0
