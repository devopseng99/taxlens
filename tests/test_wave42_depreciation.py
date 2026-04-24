"""Wave 42 tests — Depreciation & Form 4562 (MACRS, Section 179, Bonus)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    BusinessIncome, DepreciableAsset,
    compute_tax,
)
from tax_config import (
    SINGLE, MFJ, MACRS_TABLES, BONUS_DEPRECIATION_RATES,
    get_year_config,
)


def _base_result(**kw):
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
# DepreciableAsset Dataclass
# =========================================================================
class TestDepreciableAsset:
    def test_5yr_macrs_year1(self):
        """5-year MACRS, year 1: 20% of cost."""
        asset = DepreciableAsset(cost=10000, macrs_class=5, recovery_year=1,
                                  bonus_depreciation=False, section_179_elected=0)
        depr = asset.compute_depreciation(2025)
        assert depr == round(10000 * 0.2000, 2)

    def test_5yr_macrs_year2(self):
        """5-year MACRS, year 2: 32% of cost."""
        asset = DepreciableAsset(cost=10000, macrs_class=5, recovery_year=2,
                                  bonus_depreciation=False)
        depr = asset.compute_depreciation(2025)
        assert depr == round(10000 * 0.3200, 2)

    def test_7yr_macrs_year1(self):
        """7-year MACRS, year 1: 14.29%."""
        asset = DepreciableAsset(cost=50000, macrs_class=7, recovery_year=1,
                                  bonus_depreciation=False, section_179_elected=0)
        depr = asset.compute_depreciation(2025)
        assert depr == round(50000 * 0.1429, 2)

    def test_3yr_macrs_full_schedule(self):
        """3-year MACRS recovers 100% over 4 periods (half-year)."""
        total = 0
        for yr in range(1, 5):
            asset = DepreciableAsset(cost=10000, macrs_class=3, recovery_year=yr,
                                      bonus_depreciation=False, section_179_elected=0)
            total += asset.compute_depreciation(2025)
        assert abs(total - 10000) < 1.0  # Should recover ~100%

    def test_residential_rental_straight_line(self):
        """27.5-year residential rental: straight-line."""
        asset = DepreciableAsset(cost=275000, macrs_class=27, recovery_year=1,
                                  asset_use="rental")
        depr = asset.compute_depreciation(2025)
        assert depr == round(275000 / 27.5, 2)

    def test_nonresidential_39yr(self):
        """39-year nonresidential: straight-line."""
        asset = DepreciableAsset(cost=390000, macrs_class=39, recovery_year=1,
                                  asset_use="rental")
        depr = asset.compute_depreciation(2025)
        assert depr == round(390000 / 39.0, 2)

    def test_real_property_no_bonus(self):
        """Real property (27.5/39) not eligible for bonus depreciation."""
        asset = DepreciableAsset(cost=275000, macrs_class=27, recovery_year=1,
                                  bonus_depreciation=True, asset_use="rental")
        depr_with_bonus = asset.compute_depreciation(2025)
        asset2 = DepreciableAsset(cost=275000, macrs_class=27, recovery_year=1,
                                   bonus_depreciation=False, asset_use="rental")
        depr_no_bonus = asset2.compute_depreciation(2025)
        assert depr_with_bonus == depr_no_bonus  # Bonus has no effect on real property

    def test_real_property_no_section_179(self):
        """Real property not eligible for Section 179."""
        asset = DepreciableAsset(cost=275000, macrs_class=27, recovery_year=1,
                                  section_179_elected=50000, asset_use="rental")
        depr = asset.compute_depreciation(2025)
        # Section 179 skipped for real property, so just straight-line
        assert depr == round(275000 / 27.5, 2)

    def test_is_real_property(self):
        assert DepreciableAsset(macrs_class=27).is_real_property is True
        assert DepreciableAsset(macrs_class=39).is_real_property is True
        assert DepreciableAsset(macrs_class=5).is_real_property is False
        assert DepreciableAsset(macrs_class=7).is_real_property is False

    def test_business_use_percentage(self):
        """Business use < 100% reduces depreciable basis."""
        asset = DepreciableAsset(cost=10000, macrs_class=5, recovery_year=1,
                                  business_use_pct=60.0,
                                  bonus_depreciation=False, section_179_elected=0)
        depr = asset.compute_depreciation(2025)
        assert depr == round(10000 * 0.60 * 0.2000, 2)

    def test_zero_cost(self):
        asset = DepreciableAsset(cost=0, macrs_class=5, recovery_year=1)
        assert asset.compute_depreciation(2025) == 0.0


# =========================================================================
# Section 179
# =========================================================================
class TestSection179:
    def test_section_179_basic(self):
        """Section 179 deduction in year 1."""
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(description="Laptop", cost=3000,
                                  section_179_elected=3000, bonus_depreciation=False),
            ],
        )
        assert r.depreciation_section_179 == 3000.0
        assert r.depreciation_total >= 3000.0

    def test_section_179_not_year2(self):
        """Section 179 only applies in recovery year 1."""
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=3000, section_179_elected=3000,
                                  recovery_year=2, bonus_depreciation=False),
            ],
        )
        assert r.depreciation_section_179 == 0.0

    def test_section_179_limit_2025(self):
        """Section 179 capped at $1,250,000 for 2025."""
        c = get_year_config(2025)
        assert c.SECTION_179_LIMIT == 1_250_000

    def test_section_179_limit_2024(self):
        c = get_year_config(2024)
        assert c.SECTION_179_LIMIT == 1_160_000


# =========================================================================
# Bonus Depreciation
# =========================================================================
class TestBonusDepreciation:
    def test_bonus_rate_2025(self):
        """2025 bonus depreciation rate is 40%."""
        assert BONUS_DEPRECIATION_RATES[2025] == 0.40

    def test_bonus_rate_2024(self):
        assert BONUS_DEPRECIATION_RATES[2024] == 0.60

    def test_bonus_applies_year1(self):
        """Bonus depreciation applies in year 1."""
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=10000, macrs_class=5, recovery_year=1,
                                  date_placed_in_service="2025-06-01",
                                  section_179_elected=0, bonus_depreciation=True),
            ],
        )
        # Bonus: 40% of 10000 = 4000; remaining 6000 * 20% MACRS = 1200; total = 5200
        assert r.depreciation_bonus == 4000.0
        assert r.depreciation_total == 5200.0

    def test_no_bonus_year2(self):
        """Bonus depreciation only applies in recovery year 1."""
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=10000, macrs_class=5, recovery_year=2,
                                  bonus_depreciation=True),
            ],
        )
        assert r.depreciation_bonus == 0.0

    def test_bonus_with_section_179(self):
        """Section 179 reduces basis before bonus is applied."""
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=10000, macrs_class=5, recovery_year=1,
                                  date_placed_in_service="2025-01-15",
                                  section_179_elected=4000, bonus_depreciation=True),
            ],
        )
        # S179: 4000; Remaining: 6000; Bonus: 40% * 6000 = 2400; MACRS: 3600 * 20% = 720
        assert r.depreciation_section_179 == 4000.0
        assert r.depreciation_bonus == 2400.0
        expected_macrs = round(3600 * 0.2000, 2)
        assert abs(r.depreciation_macrs - expected_macrs) < 1.0
        expected_total = 4000 + 2400 + expected_macrs
        assert abs(r.depreciation_total - expected_total) < 1.0


# =========================================================================
# Engine Integration
# =========================================================================
class TestDepreciationEngine:
    def test_business_depreciation_reduces_schedule_c(self):
        """Business depreciation reduces Schedule C profit."""
        r_no_depr = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000, other_expenses=20000)],
        )
        r_with_depr = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000, other_expenses=20000)],
            depreciable_assets=[
                DepreciableAsset(cost=50000, macrs_class=5, recovery_year=1,
                                  bonus_depreciation=False, section_179_elected=0,
                                  asset_use="business"),
            ],
        )
        # 5-yr MACRS year 1: 20% * 50000 = 10000
        assert r_with_depr.sched_c_total_profit < r_no_depr.sched_c_total_profit
        assert r_with_depr.depreciation_business == 10000.0

    def test_rental_depreciation_reduces_schedule_e(self):
        """Rental depreciation reduces Schedule E net income."""
        from tax_engine import RentalProperty
        r_no_depr = _base_result(
            rental_properties=[RentalProperty(gross_rents=24000, insurance=2000)],
        )
        r_with_depr = _base_result(
            rental_properties=[RentalProperty(gross_rents=24000, insurance=2000)],
            depreciable_assets=[
                DepreciableAsset(cost=275000, macrs_class=27, recovery_year=1,
                                  asset_use="rental"),
            ],
        )
        assert r_with_depr.sched_e_net_income < r_no_depr.sched_e_net_income
        assert r_with_depr.depreciation_rental == round(275000 / 27.5, 2)

    def test_mixed_business_and_rental(self):
        """Assets split between business and rental."""
        from tax_engine import RentalProperty
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            rental_properties=[RentalProperty(gross_rents=24000)],
            depreciable_assets=[
                DepreciableAsset(description="Laptop", cost=3000, macrs_class=5,
                                  asset_use="business", bonus_depreciation=False,
                                  section_179_elected=0),
                DepreciableAsset(description="Rental roof", cost=20000, macrs_class=27,
                                  asset_use="rental"),
            ],
        )
        assert r.depreciation_business == round(3000 * 0.2000, 2)
        assert r.depreciation_rental == round(20000 / 27.5, 2)
        assert r.depreciation_total == r.depreciation_business + r.depreciation_rental

    def test_depreciation_reduces_tax(self):
        """Depreciation reduces taxable income and therefore tax."""
        r_no_depr = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
        )
        r_with_depr = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=50000, macrs_class=5,
                                  section_179_elected=50000, bonus_depreciation=False),
            ],
        )
        assert r_with_depr.line_15_taxable_income < r_no_depr.line_15_taxable_income

    def test_form_4562_in_forms(self):
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=5000, macrs_class=5, bonus_depreciation=False,
                                  section_179_elected=0),
            ],
        )
        assert "Form 4562" in r.forms_generated

    def test_no_form_4562_without_assets(self):
        r = _base_result()
        assert "Form 4562" not in r.forms_generated

    def test_depreciation_summary_in_output(self):
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=10000, macrs_class=5, section_179_elected=5000,
                                  date_placed_in_service="2025-03-01",
                                  bonus_depreciation=True),
            ],
        )
        s = r.to_summary()
        assert s["depreciation"] is not None
        assert s["depreciation"]["assets"] == 1
        assert s["depreciation"]["section_179"] == 5000.0
        assert s["depreciation"]["total"] > 0

    def test_no_depreciation_summary_when_none(self):
        r = _base_result()
        s = r.to_summary()
        assert s["depreciation"] is None

    def test_backward_compat(self):
        """No depreciable assets = no impact."""
        r = _base_result()
        assert r.depreciation_assets_count == 0
        assert r.depreciation_total == 0.0

    def test_macrs_tables_exist(self):
        """MACRS tables defined for common classes."""
        assert 3 in MACRS_TABLES
        assert 5 in MACRS_TABLES
        assert 7 in MACRS_TABLES
        assert 15 in MACRS_TABLES

    def test_15yr_macrs(self):
        """15-year MACRS (land improvements)."""
        asset = DepreciableAsset(cost=100000, macrs_class=15, recovery_year=1,
                                  bonus_depreciation=False, section_179_elected=0)
        depr = asset.compute_depreciation(2025)
        assert depr == round(100000 * 0.0500, 2)

    def test_2024_bonus_rate(self):
        """2024 tax year uses 60% bonus."""
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=10000, macrs_class=5, recovery_year=1,
                                  date_placed_in_service="2024-06-01",
                                  section_179_elected=0, bonus_depreciation=True),
            ],
            tax_year=2024,
        )
        assert r.depreciation_bonus == 6000.0  # 60% of 10000

    def test_assets_count(self):
        r = _base_result(
            businesses=[BusinessIncome(gross_receipts=100000)],
            depreciable_assets=[
                DepreciableAsset(cost=5000, macrs_class=5, bonus_depreciation=False,
                                  section_179_elected=0),
                DepreciableAsset(cost=3000, macrs_class=7, bonus_depreciation=False,
                                  section_179_elected=0),
            ],
        )
        assert r.depreciation_assets_count == 2
