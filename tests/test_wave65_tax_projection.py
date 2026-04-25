"""Wave 65 tests — Tax Projection + Multi-Year Planning + Roth Optimizer."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Inflation Adjustment
# =========================================================================
class TestInflation:
    def test_inflate_function(self):
        from tax_projector import inflate
        # $15000 * 1.028 = $15420, rounded to nearest $50 = $15400
        result = inflate(15000)
        assert result % 50 == 0
        assert result > 15000

    def test_inflate_custom_factor(self):
        from tax_projector import inflate
        result = inflate(10000, 1.05)
        assert result == 10500

    def test_cpi_factor(self):
        from tax_projector import CPI_U_2026_FACTOR
        assert 1.01 < CPI_U_2026_FACTOR < 1.10


# =========================================================================
# 2026 Projected Constants
# =========================================================================
class TestProjectedConstants:
    def test_returns_dict(self):
        from tax_projector import get_2026_projected_constants
        constants = get_2026_projected_constants()
        assert isinstance(constants, dict)
        assert constants["tax_year"] == 2026

    def test_standard_deduction_inflated(self):
        from tax_projector import get_2026_projected_constants
        from tax_config import get_year_config
        c2025 = get_year_config(2025)
        constants = get_2026_projected_constants()
        assert constants["standard_deduction_single"] > c2025.STANDARD_DEDUCTION["single"]

    def test_salt_cap_unchanged(self):
        from tax_projector import get_2026_projected_constants
        from tax_config import get_year_config
        c2025 = get_year_config(2025)
        constants = get_2026_projected_constants()
        assert constants["salt_cap"] == c2025.SALT_CAP

    def test_has_note(self):
        from tax_projector import get_2026_projected_constants
        constants = get_2026_projected_constants()
        assert "CPI-U" in constants["note"]


# =========================================================================
# Multi-Year Projection
# =========================================================================
class TestProjection:
    def test_3_year_projection(self):
        from tax_projector import ProjectionScenario, project_tax_liability
        base = ProjectionScenario(wages=80000, federal_withheld=12000)
        results = project_tax_liability(base)
        assert len(results) == 3
        assert results[0].tax_year == 2024
        assert results[2].tax_year == 2026

    def test_income_grows(self):
        from tax_projector import ProjectionScenario, project_tax_liability
        base = ProjectionScenario(wages=80000, federal_withheld=12000, income_growth_rate=0.05)
        results = project_tax_liability(base)
        assert results[1].total_income > results[0].total_income
        assert results[2].total_income > results[1].total_income

    def test_2026_is_projected(self):
        from tax_projector import ProjectionScenario, project_tax_liability
        base = ProjectionScenario(wages=80000, federal_withheld=12000)
        results = project_tax_liability(base)
        assert results[0].is_projected is False
        assert results[1].is_projected is False
        assert results[2].is_projected is True

    def test_custom_years(self):
        from tax_projector import ProjectionScenario, project_tax_liability
        base = ProjectionScenario(wages=50000)
        results = project_tax_liability(base, years=2, start_year=2025)
        assert len(results) == 2
        assert results[0].tax_year == 2025

    def test_effective_rate_reasonable(self):
        from tax_projector import ProjectionScenario, project_tax_liability
        base = ProjectionScenario(wages=80000, filing_status="single")
        results = project_tax_liability(base)
        for r in results:
            assert 0 <= r.effective_rate <= 50


# =========================================================================
# Roth Conversion Optimizer
# =========================================================================
class TestRothOptimizer:
    def test_basic_optimization(self):
        from tax_projector import optimize_roth_conversion
        result = optimize_roth_conversion(wages=80000, target_bracket_rate=0.22)
        assert result.optimal_conversion >= 0
        assert result.stays_in_bracket is True

    def test_zero_conversion_when_already_at_target(self):
        from tax_projector import optimize_roth_conversion
        # Very high income already above target bracket
        result = optimize_roth_conversion(wages=500000, target_bracket_rate=0.22)
        assert result.optimal_conversion == 0

    def test_tax_on_conversion(self):
        from tax_projector import optimize_roth_conversion
        result = optimize_roth_conversion(wages=50000, target_bracket_rate=0.24)
        if result.optimal_conversion > 0:
            assert result.tax_on_conversion > 0
            assert result.total_tax_with_conversion > result.total_tax_without_conversion

    def test_marginal_rate_at_conversion(self):
        from tax_projector import optimize_roth_conversion
        result = optimize_roth_conversion(wages=60000, target_bracket_rate=0.22)
        assert result.marginal_rate_at_conversion <= 22.1  # Allow small float imprecision


# =========================================================================
# API Endpoints
# =========================================================================
class TestEndpoints:
    def test_projection_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/tax-projection" in src
        assert "async def tax_projection" in src

    def test_roth_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/roth-optimizer" in src
        assert "async def roth_optimizer" in src

    def test_projector_module_exists(self):
        from tax_projector import project_tax_liability, optimize_roth_conversion
        assert callable(project_tax_liability)
        assert callable(optimize_roth_conversion)
