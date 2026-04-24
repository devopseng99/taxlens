"""Wave 32-33 tests — Schedule E (rental income) + HSA deduction."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, AdditionalIncome, Deductions, Payments,
    RentalProperty, HSAContribution, compute_tax,
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
# Schedule E — Rental Income
# =========================================================================
class TestScheduleERentalIncome:
    def test_single_profitable_rental(self):
        """Rental property with net income increases total income."""
        prop = RentalProperty(
            property_address="123 Main St",
            gross_rents=24000,
            mortgage_interest=6000,
            taxes=3000,
            insurance=1200,
            depreciation=5000,
        )
        result = _compute(rental_properties=[prop])
        assert result.sched_e_total_income == 24000
        assert result.sched_e_total_expenses == 6000 + 3000 + 1200 + 5000
        assert result.sched_e_net_income == 24000 - 15200
        # Rental income included in total income
        assert result.line_9_total_income == 75000 + result.sched_e_net_income
        assert "Schedule E" in result.forms_generated

    def test_multiple_rentals(self):
        """Multiple rental properties are aggregated."""
        p1 = RentalProperty(gross_rents=18000, mortgage_interest=8000, taxes=2000)
        p2 = RentalProperty(gross_rents=12000, repairs=3000, utilities=1500)
        result = _compute(rental_properties=[p1, p2])
        assert result.sched_e_total_income == 30000
        assert result.sched_e_total_expenses == 10000 + 4500
        assert result.sched_e_net_income == 30000 - 14500
        assert len(result.sched_e_properties) == 2

    def test_rental_loss_within_25k_limit(self):
        """Net rental loss under $25K allowed for AGI under $100K."""
        prop = RentalProperty(gross_rents=12000, mortgage_interest=15000, taxes=5000, depreciation=8000)
        # Loss = 12000 - 28000 = -16000 (within $25K limit)
        result = _compute(
            w2s=[W2Income(wages=60000, federal_withheld=8000, ss_wages=60000, medicare_wages=60000)],
            rental_properties=[prop],
        )
        assert result.sched_e_net_income == -16000
        assert result.line_9_total_income == 60000 - 16000

    def test_rental_loss_capped_at_25k(self):
        """Net rental loss exceeding $25K is capped."""
        prop = RentalProperty(gross_rents=5000, mortgage_interest=20000, taxes=5000, depreciation=15000)
        # Raw loss = 5000 - 40000 = -35000, capped at -25000
        result = _compute(
            w2s=[W2Income(wages=60000, federal_withheld=8000, ss_wages=60000, medicare_wages=60000)],
            rental_properties=[prop],
        )
        assert result.sched_e_net_income == -25000

    def test_rental_loss_phaseout_high_agi(self):
        """Rental loss allowance phases out at AGI $100K-$150K."""
        prop = RentalProperty(gross_rents=10000, mortgage_interest=20000, taxes=5000)
        # Raw loss = -15000; AGI from wages = $130K, phaseout reduces $25K by 50% of ($130K-$100K) = $10K
        # Allowed = $25K - $15K = $10K, but loss is only $15K so allowed = min(15000, 10000) = 10000
        result = _compute(
            w2s=[W2Income(wages=130000, federal_withheld=25000, ss_wages=130000, medicare_wages=130000)],
            rental_properties=[prop],
        )
        assert result.sched_e_net_income == -10000

    def test_rental_loss_fully_phased_out(self):
        """Rental loss fully disallowed at AGI >= $150K."""
        prop = RentalProperty(gross_rents=10000, mortgage_interest=20000, taxes=5000)
        result = _compute(
            w2s=[W2Income(wages=160000, federal_withheld=30000, ss_wages=160000, medicare_wages=160000)],
            rental_properties=[prop],
        )
        assert result.sched_e_net_income == 0

    def test_no_rentals_no_schedule_e(self):
        """No rental properties means no Schedule E fields populated."""
        result = _compute()
        assert result.sched_e_net_income == 0
        assert result.sched_e_properties == []
        assert "Schedule E" not in result.forms_generated

    def test_rental_in_summary(self):
        """rental_income appears in to_summary output."""
        prop = RentalProperty(gross_rents=20000, taxes=3000)
        result = _compute(rental_properties=[prop])
        summary = result.to_summary()
        assert "rental_income" in summary
        assert summary["rental_income"] == 17000.0

    def test_rental_property_details_in_result(self):
        """Each property's details are stored in sched_e_properties."""
        prop = RentalProperty(
            property_address="456 Oak Ave",
            rental_days=300,
            personal_use_days=30,
            gross_rents=15000,
            insurance=1000,
        )
        result = _compute(rental_properties=[prop])
        assert len(result.sched_e_properties) == 1
        p = result.sched_e_properties[0]
        assert p["address"] == "456 Oak Ave"
        assert p["rental_days"] == 300
        assert p["gross_rents"] == 15000


# =========================================================================
# HSA Deduction
# =========================================================================
class TestHSADeduction:
    def test_hsa_self_coverage(self):
        """HSA self-only contribution reduces AGI (2025 limit: $4,300)."""
        hsa = HSAContribution(contributor="filer", contribution_amount=4300, coverage_type="self")
        result = _compute(hsa_contributions=[hsa])
        assert result.hsa_deduction == 4300
        # AGI should be reduced by HSA deduction
        no_hsa = _compute()
        assert result.line_11_agi == no_hsa.line_11_agi - 4300

    def test_hsa_family_coverage(self):
        """HSA family contribution (2025 limit: $8,550)."""
        hsa = HSAContribution(contribution_amount=8550, coverage_type="family")
        result = _compute(hsa_contributions=[hsa])
        assert result.hsa_deduction == 8550

    def test_hsa_over_limit_capped(self):
        """HSA contribution exceeding limit is capped."""
        hsa = HSAContribution(contribution_amount=10000, coverage_type="self")
        result = _compute(hsa_contributions=[hsa])
        assert result.hsa_deduction == 4300  # 2025 self limit

    def test_hsa_catchup_55_plus(self):
        """Age 55+ gets $1,000 catch-up on top of regular limit."""
        hsa = HSAContribution(contribution_amount=5300, coverage_type="self", age_55_plus=True)
        result = _compute(hsa_contributions=[hsa])
        assert result.hsa_deduction == 5300  # 4300 + 1000

    def test_hsa_family_catchup(self):
        """Family coverage with catch-up: $8,550 + $1,000 = $9,550."""
        hsa = HSAContribution(contribution_amount=9550, coverage_type="family", age_55_plus=True)
        result = _compute(hsa_contributions=[hsa])
        assert result.hsa_deduction == 9550

    def test_hsa_multiple_contributions(self):
        """Multiple HSA contributions (filer + spouse) both get limits."""
        h1 = HSAContribution(contributor="filer", contribution_amount=4300, coverage_type="self")
        h2 = HSAContribution(contributor="spouse", contribution_amount=4300, coverage_type="self")
        result = _compute(hsa_contributions=[h1, h2])
        assert result.hsa_deduction == 8600

    def test_hsa_2024_limits(self):
        """2024 HSA limits are different ($4,150 self, $8,300 family)."""
        hsa = HSAContribution(contribution_amount=5000, coverage_type="self")
        result = _compute(hsa_contributions=[hsa], tax_year=2024)
        assert result.hsa_deduction == 4150  # 2024 self limit

    def test_hsa_in_summary(self):
        """hsa_deduction appears in to_summary output."""
        hsa = HSAContribution(contribution_amount=4000, coverage_type="self")
        result = _compute(hsa_contributions=[hsa])
        summary = result.to_summary()
        assert "hsa_deduction" in summary
        assert summary["hsa_deduction"] == 4000.0

    def test_no_hsa_no_deduction(self):
        """No HSA contributions means no deduction."""
        result = _compute()
        assert result.hsa_deduction == 0


# =========================================================================
# Combined: Rental + HSA
# =========================================================================
class TestCombinedRentalHSA:
    def test_rental_income_plus_hsa_deduction(self):
        """Rental income increases total income, HSA reduces AGI."""
        prop = RentalProperty(gross_rents=24000, taxes=4000)
        hsa = HSAContribution(contribution_amount=4300, coverage_type="self")
        result = _compute(rental_properties=[prop], hsa_contributions=[hsa])
        # Total income = wages(75000) + rental(20000) = 95000
        assert result.line_9_total_income == 95000
        # AGI = 95000 - adjustments(HSA=4300)
        assert result.hsa_deduction == 4300
        assert result.sched_e_net_income == 20000

    def test_rental_loss_with_hsa(self):
        """Rental loss and HSA both reduce taxable income."""
        prop = RentalProperty(gross_rents=5000, mortgage_interest=15000, taxes=3000)
        hsa = HSAContribution(contribution_amount=4300, coverage_type="self")
        result = _compute(rental_properties=[prop], hsa_contributions=[hsa])
        assert result.sched_e_net_income == -13000
        assert result.hsa_deduction == 4300
        # Total income = 75000 - 13000 = 62000
        assert result.line_9_total_income == 62000


# =========================================================================
# MCP _build_inputs Integration
# =========================================================================
class TestMCPRentalHSA:
    def test_build_inputs_rental(self):
        from mcp_server import _build_inputs
        inputs = _build_inputs(
            filing_status="single", wages=80000, federal_withheld=12000,
            rental_properties=[{
                "property_address": "123 Test St",
                "gross_rents": 20000,
                "mortgage_interest": 5000,
                "taxes": 2000,
            }],
        )
        assert inputs["rental_properties"] is not None
        assert len(inputs["rental_properties"]) == 1
        rp = inputs["rental_properties"][0]
        assert isinstance(rp, RentalProperty)
        assert rp.gross_rents == 20000
        assert rp.mortgage_interest == 5000

    def test_build_inputs_hsa(self):
        from mcp_server import _build_inputs
        inputs = _build_inputs(
            filing_status="single", wages=80000, federal_withheld=12000,
            hsa_contributions=[{
                "contributor": "filer",
                "contribution_amount": 4300,
                "coverage_type": "self",
                "age_55_plus": False,
            }],
        )
        assert inputs["hsa_contributions"] is not None
        assert len(inputs["hsa_contributions"]) == 1
        h = inputs["hsa_contributions"][0]
        assert isinstance(h, HSAContribution)
        assert h.contribution_amount == 4300

    def test_mcp_compute_with_rental(self):
        from mcp_server import _build_inputs
        inputs = _build_inputs(
            filing_status="single", wages=80000, federal_withheld=12000,
            rental_properties=[{"gross_rents": 18000, "taxes": 3000, "insurance": 1200}],
        )
        result = compute_tax(**inputs)
        assert result.sched_e_net_income == 13800
        assert result.line_9_total_income == 80000 + 13800

    def test_mcp_compute_with_hsa(self):
        from mcp_server import _build_inputs
        inputs = _build_inputs(
            filing_status="single", wages=80000, federal_withheld=12000,
            hsa_contributions=[{"contribution_amount": 4300, "coverage_type": "self"}],
        )
        result = compute_tax(**inputs)
        assert result.hsa_deduction == 4300

    def test_get_tax_config_includes_hsa_and_rental(self):
        import json
        from mcp_server import get_tax_config
        raw = get_tax_config(tax_year=2025)
        config = json.loads(raw)
        assert "hsa" in config
        assert config["hsa"]["limit_self"] == 4300
        assert config["hsa"]["limit_family"] == 8550
        assert config["hsa"]["catchup_55_plus"] == 1000
        assert "rental" in config
        assert config["rental"]["passive_loss_limit"] == 25000
        assert config["rental"]["phaseout_start_agi"] == 100000

    def test_get_tax_config_2024_hsa(self):
        import json
        from mcp_server import get_tax_config
        raw = get_tax_config(tax_year=2024)
        config = json.loads(raw)
        assert config["hsa"]["limit_self"] == 4150
        assert config["hsa"]["limit_family"] == 8300
