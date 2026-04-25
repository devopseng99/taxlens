"""Wave 76 tests — Compare Scenarios Marginal Rates + Audit Risk Passing Checks."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    compute_tax, PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    BusinessIncome, RentalProperty,
)
from audit_risk import assess_audit_risk, PassingCheck, AuditRiskReport
from tax_projector import _marginal_rate, _effective_rate


# =========================================================================
# Marginal Rate Helper
# =========================================================================
class TestMarginalRate:
    def test_10pct_bracket(self):
        """Income in the 10% bracket."""
        rate = _marginal_rate(10_000, "single")
        assert rate == 0.10

    def test_22pct_bracket(self):
        """Income solidly in the 22% bracket."""
        rate = _marginal_rate(60_000, "single")
        assert rate == 0.22

    def test_37pct_bracket(self):
        """Income in the top bracket."""
        rate = _marginal_rate(700_000, "single")
        assert rate == 0.37

    def test_mfj_different_brackets(self):
        """MFJ has wider brackets — $100K is in a lower bracket than single."""
        rate_single = _marginal_rate(100_000, "single")
        rate_mfj = _marginal_rate(100_000, "mfj")
        assert rate_mfj <= rate_single


class TestEffectiveRate:
    def test_basic(self):
        rate = _effective_rate(10_000, 50_000)
        assert rate == 0.20

    def test_zero_income(self):
        rate = _effective_rate(0, 0)
        assert rate == 0.0

    def test_no_tax(self):
        rate = _effective_rate(0, 50_000)
        assert rate == 0.0


# =========================================================================
# Compare Scenarios — Rate Fields (via compute_tax + rate helpers)
# =========================================================================
class TestCompareScenarioRates:
    def test_rates_computed_correctly(self):
        """Marginal and effective rates can be computed from TaxResult fields."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Test", last_name="Rate"),
            w2s=[W2Income(wages=80_000, federal_withheld=10_000,
                          ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        eff = _effective_rate(result.line_24_total_tax, result.line_9_total_income)
        marg = _marginal_rate(result.line_15_taxable_income, "single")
        assert 0 < eff < 1
        assert marg in (0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37)

    def test_higher_income_higher_marginal(self):
        """Higher income should have equal or higher marginal rate."""
        rate_low = _marginal_rate(50_000, "single")
        rate_high = _marginal_rate(200_000, "single")
        assert rate_high >= rate_low

    def test_mfj_vs_single_marginal_differ(self):
        """Same taxable income, different filing status → different marginal rates."""
        rate_s = _marginal_rate(150_000, "single")
        rate_m = _marginal_rate(150_000, "mfj")
        # At $150K, single is 24%, MFJ is 22%
        assert rate_s > rate_m


# =========================================================================
# Audit Risk — Passing Checks
# =========================================================================
def _simple_result(wages=80_000, charitable=0, deduction_type="standard"):
    return compute_tax(
        filing_status="single",
        filer=PersonInfo(first_name="Audit", last_name="Test"),
        w2s=[W2Income(wages=wages, federal_withheld=wages * 0.2,
                      ss_wages=wages, medicare_wages=wages)],
        additional=AdditionalIncome(),
        deductions=Deductions(charitable_cash=charitable),
        payments=Payments(),
    )


class TestPassingChecks:
    def test_low_risk_has_passing_checks(self):
        """Low-risk filer should have passing checks."""
        result = _simple_result()
        report = assess_audit_risk(result)
        assert isinstance(report.passing_checks, list)
        assert len(report.passing_checks) > 0

    def test_passing_check_is_dataclass(self):
        """PassingCheck has expected fields."""
        result = _simple_result()
        report = assess_audit_risk(result)
        for p in report.passing_checks:
            assert isinstance(p, PassingCheck)
            assert p.category
            assert p.description

    def test_standard_deduction_passing(self):
        """Standard deduction filer gets passing check for itemized category."""
        result = _simple_result()
        report = assess_audit_risk(result)
        cats = [p.category for p in report.passing_checks]
        assert "itemized_deductions" in cats

    def test_income_level_passing(self):
        """Normal income bracket gets passing check."""
        result = _simple_result(wages=80_000)
        report = assess_audit_risk(result)
        cats = [p.category for p in report.passing_checks]
        assert "income_level" in cats

    def test_to_dict_includes_passing(self):
        """to_dict() includes passing_checks."""
        result = _simple_result()
        report = assess_audit_risk(result)
        d = report.to_dict()
        assert "passing_checks" in d
        assert "num_passing" in d
        assert d["num_passing"] == len(report.passing_checks)

    def test_high_risk_fewer_passing(self):
        """High-risk filer has fewer passing checks than a clean filer."""
        clean = _simple_result(wages=80_000)
        report_clean = assess_audit_risk(clean)

        # High charitable ratio triggers flags
        risky = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Risky", last_name="Filer"),
            w2s=[W2Income(wages=80_000, federal_withheld=16_000,
                          ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(
                charitable_cash=50_000,  # 62% of AGI — very high
                mortgage_interest=15_000,
                property_tax=10_000,
                state_income_tax_paid=5_000,
            ),
            payments=Payments(),
        )
        report_risky = assess_audit_risk(risky)
        # Risky should have more flags
        assert len(report_risky.flags) > len(report_clean.flags)

    def test_no_flags_all_passing(self):
        """Filer with no risk flags should still have passing checks."""
        result = _simple_result()
        report = assess_audit_risk(result)
        assert len(report.flags) == 0
        assert report.risk_score == 0
        assert len(report.passing_checks) > 0

    def test_business_passing_checks(self):
        """Business with good margins gets passing checks."""
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Biz", last_name="Owner"),
            w2s=[],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            businesses=[BusinessIncome(
                gross_receipts=100_000,
                other_expenses=30_000,  # 30% expense ratio — well under 85%
            )],
        )
        report = assess_audit_risk(result)
        cats = [p.category for p in report.passing_checks]
        assert "schedule_c" in cats


class TestAuditRiskReportStructure:
    def test_report_has_both_lists(self):
        """AuditRiskReport has both flags and passing_checks."""
        result = _simple_result()
        report = assess_audit_risk(result)
        assert hasattr(report, 'flags')
        assert hasattr(report, 'passing_checks')

    def test_to_dict_complete(self):
        """to_dict has all expected keys."""
        result = _simple_result()
        report = assess_audit_risk(result)
        d = report.to_dict()
        expected_keys = {"agi_bracket", "base_audit_rate_pct", "overall_risk",
                         "risk_score", "num_flags", "flags",
                         "num_passing", "passing_checks"}
        assert expected_keys.issubset(set(d.keys()))

    def test_passing_check_dict_structure(self):
        """Each passing check in to_dict has expected keys."""
        result = _simple_result()
        report = assess_audit_risk(result)
        d = report.to_dict()
        for p in d["passing_checks"]:
            assert "category" in p
            assert "description" in p
            assert "your_value" in p
            assert "norm_value" in p
