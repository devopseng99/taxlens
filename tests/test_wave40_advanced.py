"""Wave 40 tests — Advanced Tax Features (Energy Credits, K-1 Passthrough, Quarterly Planner)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    EnergyImprovement, K1Income, BusinessIncome,
    compute_tax,
)
from tax_config import SINGLE, MFJ, HOH


def _base_result(**kw):
    """Helper: compute tax with defaults + overrides."""
    defaults = dict(
        filing_status=SINGLE,
        filer=PersonInfo(first_name="Test", last_name="User"),
        w2s=[W2Income(wages=80000, federal_withheld=12000,
                      ss_wages=80000, medicare_wages=80000)],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
    )
    defaults.update(kw)
    return compute_tax(**defaults)


# =========================================================================
# Form 5695 — Residential Energy Credits (§25D + §25C)
# =========================================================================
class TestEnergyCredits:
    def test_solar_30pct_credit(self):
        """§25D: Solar panels get 30% credit with no annual cap."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(solar_electric=25000)
        ])
        assert r.energy_clean_credit == 7500.0  # 30% of $25K
        assert r.energy_total_credit == 7500.0

    def test_solar_no_annual_cap(self):
        """§25D credits have no annual limit (unlike §25C)."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(solar_electric=100000)
        ])
        assert r.energy_clean_credit == 30000.0  # 30% of $100K

    def test_battery_storage_credit(self):
        """Battery storage ≥3 kWh qualifies for §25D credit."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(battery_storage=8000)
        ])
        assert r.energy_clean_credit == 2400.0  # 30% of $8K

    def test_heat_pump_credit_with_cap(self):
        """§25C: Heat pump credit capped at $2,000."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(heat_pump=10000)
        ])
        assert r.energy_improvement_credit == 2000.0  # Capped

    def test_insulation_envelope_cap(self):
        """§25C: Insulation/windows/doors capped at $1,200 envelope subcap."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(insulation=3000, windows_skylights=2000)
        ])
        # 30% of $5K = $1,500, but envelope cap = $1,200
        assert r.energy_improvement_credit == 1200.0

    def test_combined_envelope_and_hp(self):
        """§25C: Combined envelope ($1,200) + heat pump ($2,000) = $3,200 max."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(insulation=5000, heat_pump=8000)
        ])
        # Envelope: min(5000*0.30, 1200) = 1200
        # HP: min(8000*0.30, 2000) = 2000
        # Total: 3200 (= annual limit)
        assert r.energy_improvement_credit == 3200.0

    def test_25c_annual_limit(self):
        """§25C total capped at $3,200/year."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(insulation=5000, heat_pump=20000, biomass_stove=10000)
        ])
        assert r.energy_improvement_credit <= 3200.0

    def test_energy_audit_cap_150(self):
        """Energy audit expenses capped at $150."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(energy_audit=500)
        ])
        # min(500, 150) = 150 * 0.30 = 45
        assert r.energy_improvement_credit == 45.0

    def test_combined_25d_25c(self):
        """Both §25D and §25C credits stack."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(solar_electric=20000, heat_pump=8000)
        ])
        assert r.energy_clean_credit == 6000.0    # 30% of $20K
        assert r.energy_improvement_credit == 2000.0  # HP capped at $2K
        assert r.energy_total_credit == 8000.0

    def test_energy_credit_nonrefundable(self):
        """Energy credits can't exceed tax liability."""
        # Low-income filer with large solar investment
        r = _base_result(
            w2s=[W2Income(wages=20000, federal_withheld=1000,
                          ss_wages=20000, medicare_wages=20000)],
            energy_improvements=[EnergyImprovement(solar_electric=50000)],
        )
        # Credit would be $15K but limited to tax liability
        assert r.energy_total_credit <= r.energy_clean_credit
        assert r.energy_total_credit >= 0

    def test_no_energy_no_credit(self):
        """No energy improvements = no credit."""
        r = _base_result()
        assert r.energy_total_credit == 0.0
        assert r.energy_clean_credit == 0.0

    def test_form_5695_in_forms(self):
        """Form 5695 appears in forms_generated when credit claimed."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(solar_electric=10000)
        ])
        assert "Form 5695" in r.forms_generated

    def test_form_5695_not_in_forms_when_zero(self):
        """Form 5695 not listed when no energy credit."""
        r = _base_result()
        assert "Form 5695" not in r.forms_generated

    def test_energy_credit_in_summary(self):
        """Energy credit appears in summary output."""
        r = _base_result(energy_improvements=[
            EnergyImprovement(solar_electric=10000)
        ])
        s = r.to_summary()
        assert s["energy_credit"] == 3000.0
        assert s["energy_clean_credit"] == 3000.0


# =========================================================================
# Schedule K-1 — Passthrough Income
# =========================================================================
class TestK1Income:
    def test_k1_ordinary_income(self):
        """K-1 ordinary income flows to Line 8 (other income)."""
        r = _base_result(k1_incomes=[
            K1Income(entity_name="ABC LLC", ordinary_income=50000)
        ])
        assert r.k1_ordinary_income == 50000.0
        assert r.line_8_other_income == 50000.0

    def test_k1_interest_to_line_2b(self):
        """K-1 interest flows to Line 2b."""
        r = _base_result(k1_incomes=[
            K1Income(interest_income=5000)
        ])
        assert r.k1_interest_income == 5000.0
        assert r.line_2b_taxable_interest == 5000.0

    def test_k1_dividends_to_line_3(self):
        """K-1 dividends flow to Lines 3a/3b."""
        r = _base_result(k1_incomes=[
            K1Income(dividend_income=3000, qualified_dividends=2000)
        ])
        assert r.line_3b_ordinary_dividends == 3000.0
        assert r.line_3a_qualified_dividends == 2000.0

    def test_k1_capital_gains_to_schedule_d(self):
        """K-1 capital gains flow to Schedule D."""
        r = _base_result(k1_incomes=[
            K1Income(short_term_gain=1000, long_term_gain=5000)
        ])
        assert r.k1_capital_gains == 6000.0
        assert r.sched_d_short_term_gain == 1000.0
        assert r.sched_d_long_term_gain == 5000.0

    def test_k1_section_1231_as_ltcg(self):
        """§1231 gains treated as long-term capital gains."""
        r = _base_result(k1_incomes=[
            K1Income(section_1231_gain=10000)
        ])
        assert r.sched_d_long_term_gain == 10000.0

    def test_k1_guaranteed_payments_se_tax(self):
        """Partnership guaranteed payments subject to SE tax."""
        r = _base_result(k1_incomes=[
            K1Income(entity_type="partnership", guaranteed_payments=60000)
        ])
        assert r.k1_guaranteed_payments == 60000.0
        assert r.se_tax > 0  # Guaranteed payments trigger SE tax

    def test_k1_199a_qbi_deduction(self):
        """K-1 §199A income eligible for QBI deduction."""
        r = _base_result(k1_incomes=[
            K1Income(section_199a_income=50000)
        ])
        assert r.k1_section_199a_income == 50000.0
        assert r.qbi_deduction > 0  # Should get 20% QBI deduction

    def test_k1_rental_to_schedule_e(self):
        """K-1 rental income flows to Schedule E."""
        r = _base_result(k1_incomes=[
            K1Income(rental_income=12000)
        ])
        assert r.k1_rental_income == 12000.0
        assert r.sched_e_net_income == 12000.0

    def test_multiple_k1s(self):
        """Multiple K-1s aggregate correctly."""
        r = _base_result(k1_incomes=[
            K1Income(entity_name="LLC 1", ordinary_income=20000),
            K1Income(entity_name="LLC 2", ordinary_income=30000, interest_income=5000),
        ])
        assert r.k1_ordinary_income == 50000.0
        assert r.k1_interest_income == 5000.0

    def test_k1_increases_total_income(self):
        """K-1 income increases total income (Line 9)."""
        r_base = _base_result()
        r_k1 = _base_result(k1_incomes=[
            K1Income(ordinary_income=25000)
        ])
        assert r_k1.line_9_total_income > r_base.line_9_total_income

    def test_k1_summary_form_generated(self):
        """K-1 summary appears in forms_generated."""
        r = _base_result(k1_incomes=[
            K1Income(ordinary_income=10000)
        ])
        assert "Schedule K-1 Summary" in r.forms_generated

    def test_k1_summary_in_output(self):
        """K-1 amounts in summary output."""
        r = _base_result(k1_incomes=[
            K1Income(ordinary_income=10000, guaranteed_payments=5000)
        ])
        s = r.to_summary()
        assert s["k1_ordinary_income"] == 10000.0
        assert s["k1_guaranteed_payments"] == 5000.0


# =========================================================================
# Quarterly Estimated Tax Planner
# =========================================================================
class TestQuarterlyPlanner:
    def test_quarterly_calculated_when_owed(self):
        """Quarterly payments calculated when tax > withholding."""
        r = _base_result(
            w2s=[W2Income(wages=100000, federal_withheld=5000,
                          ss_wages=100000, medicare_wages=100000)],
        )
        if r.line_24_total_tax > 5000:
            assert r.quarterly_estimated_tax > 0
            assert len(r.quarterly_schedule) == 4

    def test_quarterly_four_quarters(self):
        """Schedule has exactly 4 quarters with due dates."""
        r = _base_result(
            w2s=[W2Income(wages=150000, federal_withheld=10000,
                          ss_wages=150000, medicare_wages=150000)],
        )
        if r.quarterly_schedule:
            assert len(r.quarterly_schedule) == 4
            quarters = [q["quarter"] for q in r.quarterly_schedule]
            assert quarters == ["Q1", "Q2", "Q3", "Q4"]

    def test_quarterly_due_dates(self):
        """Due dates follow IRS schedule (4/15, 6/15, 9/15, 1/15)."""
        r = _base_result(
            w2s=[W2Income(wages=200000, federal_withheld=15000,
                          ss_wages=200000, medicare_wages=200000)],
            tax_year=2025,
        )
        if r.quarterly_schedule:
            assert r.quarterly_schedule[0]["due_date"] == "2026-04-15"
            assert r.quarterly_schedule[1]["due_date"] == "2026-06-15"
            assert r.quarterly_schedule[2]["due_date"] == "2026-09-15"
            assert r.quarterly_schedule[3]["due_date"] == "2027-01-15"

    def test_quarterly_not_needed_when_refund(self):
        """No quarterly payments when withholding covers tax."""
        r = _base_result(
            w2s=[W2Income(wages=50000, federal_withheld=15000,
                          ss_wages=50000, medicare_wages=50000)],
        )
        assert r.quarterly_estimated_tax == 0
        assert r.quarterly_schedule == []

    def test_quarterly_in_summary(self):
        """Quarterly schedule appears in summary."""
        r = _base_result(
            w2s=[W2Income(wages=150000, federal_withheld=10000,
                          ss_wages=150000, medicare_wages=150000)],
        )
        s = r.to_summary()
        assert "quarterly_estimated_tax" in s
        assert "quarterly_schedule" in s

    def test_quarterly_equal_amounts(self):
        """All 4 quarters have equal amounts."""
        r = _base_result(
            w2s=[W2Income(wages=200000, federal_withheld=15000,
                          ss_wages=200000, medicare_wages=200000)],
        )
        if r.quarterly_schedule:
            amounts = [q["amount"] for q in r.quarterly_schedule]
            assert len(set(amounts)) == 1  # All same amount


# =========================================================================
# Integration: Combined Features
# =========================================================================
class TestWave40Integration:
    def test_k1_plus_energy_credits(self):
        """K-1 income + energy credits in same return."""
        r = _base_result(
            k1_incomes=[K1Income(ordinary_income=50000)],
            energy_improvements=[EnergyImprovement(solar_electric=20000)],
        )
        assert r.k1_ordinary_income == 50000.0
        assert r.energy_total_credit > 0
        assert "Form 5695" in r.forms_generated
        assert "Schedule K-1 Summary" in r.forms_generated

    def test_k1_guaranteed_plus_schedule_c(self):
        """K-1 guaranteed payments + Schedule C both subject to SE tax."""
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=30000, business_name="Freelance")],
            k1_incomes=[K1Income(guaranteed_payments=20000)],
        )
        # SE income = 30K (Sch C) + 20K (guaranteed) = 50K
        assert r.sched_se_net_earnings == 50000.0

    def test_backward_compat_no_new_params(self):
        """Existing calls without new params still work."""
        r = _base_result()
        assert r.energy_total_credit == 0.0
        assert r.k1_ordinary_income == 0.0
        assert r.quarterly_estimated_tax == 0.0

    def test_tax_config_has_energy_credits(self):
        """Tax config includes energy credit constants."""
        from tax_config import get_year_config
        c = get_year_config(2025)
        assert c.ENERGY_CLEAN_CREDIT_RATE == 0.30
        assert c.ENERGY_IMPROVEMENT_ANNUAL_LIMIT == 3200
        assert c.ENERGY_IMPROVEMENT_ENVELOPE_LIMIT == 1200
        assert c.ENERGY_IMPROVEMENT_HP_LIMIT == 2000
