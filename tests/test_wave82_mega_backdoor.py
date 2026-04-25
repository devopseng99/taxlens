"""Wave 82 tests — Mega Backdoor Roth Calculator."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from mega_backdoor_roth import compute_mega_backdoor, result_to_dict


# =========================================================================
# Basic Space Calculation
# =========================================================================
class TestSpaceCalculation:
    def test_basic_space(self):
        """Standard scenario: $23.5K deferrals + $10K match = $36.5K used of $70K."""
        r = compute_mega_backdoor(
            employee_deferrals=23_500,
            employer_match=10_000,
            tax_year=2025,
        )
        assert r.section_415c_limit == 70_000
        assert r.employee_deferrals == 23_500
        assert r.employer_match == 10_000
        assert r.used_space == 33_500
        assert r.after_tax_space == 36_500
        assert r.mega_backdoor_amount == 36_500

    def test_max_deferrals_with_match(self):
        """High earner maxing out deferrals with generous match."""
        r = compute_mega_backdoor(
            employee_deferrals=23_500,
            employer_match=23_500,  # 100% match
            tax_year=2025,
        )
        assert r.used_space == 47_000
        assert r.mega_backdoor_amount == 23_000  # $70K - $47K

    def test_no_space_left(self):
        """Deferrals + match fill §415(c) entirely."""
        r = compute_mega_backdoor(
            employee_deferrals=23_500,
            employer_match=46_500,  # Fills to $70K
            tax_year=2025,
        )
        assert r.mega_backdoor_amount == 0

    def test_overflow_no_space(self):
        """Match exceeds limit — space is zero."""
        r = compute_mega_backdoor(
            employee_deferrals=23_500,
            employer_match=50_000,
            tax_year=2025,
        )
        assert r.mega_backdoor_amount == 0

    def test_no_deferrals(self):
        """Zero deferrals — full §415(c) minus match is available."""
        r = compute_mega_backdoor(
            employee_deferrals=0,
            employer_match=5_000,
            tax_year=2025,
        )
        assert r.mega_backdoor_amount == 65_000

    def test_no_match(self):
        """No employer match — all non-deferral space is available."""
        r = compute_mega_backdoor(
            employee_deferrals=23_500,
            employer_match=0,
            tax_year=2025,
        )
        assert r.mega_backdoor_amount == 46_500


# =========================================================================
# Age 50+ Catch-up
# =========================================================================
class TestCatchUp:
    def test_catchup_increases_deferral_room(self):
        """Age 50+ can defer extra $7,500 without reducing §415(c) space."""
        r = compute_mega_backdoor(
            employee_deferrals=31_000,  # $23.5K + $7.5K catch-up
            employer_match=10_000,
            age_50_plus=True,
            tax_year=2025,
        )
        # Catch-up doesn't count toward §415(c)
        # Used: $23.5K (deferral cap) + $10K match = $33.5K
        assert r.used_space == 33_500
        assert r.mega_backdoor_amount == 36_500

    def test_no_catchup_under_50(self):
        """Under 50 — deferrals capped at §402(g) even if more contributed."""
        r = compute_mega_backdoor(
            employee_deferrals=31_000,  # Trying to defer $31K
            employer_match=10_000,
            age_50_plus=False,
            tax_year=2025,
        )
        # Capped at $23.5K
        assert r.employee_deferrals == 23_500
        assert r.used_space == 33_500


# =========================================================================
# Tax Year Variations
# =========================================================================
class TestTaxYears:
    def test_2024_limits(self):
        r = compute_mega_backdoor(employee_deferrals=23_000, employer_match=10_000, tax_year=2024)
        assert r.section_415c_limit == 69_000
        assert r.employee_deferral_limit == 23_000
        assert r.mega_backdoor_amount == 36_000  # $69K - $33K

    def test_2025_limits(self):
        r = compute_mega_backdoor(employee_deferrals=23_500, employer_match=10_000, tax_year=2025)
        assert r.section_415c_limit == 70_000
        assert r.mega_backdoor_amount == 36_500

    def test_2026_limits(self):
        r = compute_mega_backdoor(employee_deferrals=24_000, employer_match=10_000, tax_year=2026)
        assert r.section_415c_limit == 72_000
        assert r.mega_backdoor_amount == 38_000


# =========================================================================
# Projection
# =========================================================================
class TestProjection:
    def test_roth_beats_taxable(self):
        """Roth growth should exceed taxable account growth."""
        r = compute_mega_backdoor(
            employee_deferrals=23_500,
            employer_match=10_000,
            projection_years=10,
            annual_return=0.07,
        )
        assert r.projected_roth_value > r.projected_taxable_value
        assert r.projected_tax_savings > 0

    def test_longer_projection_bigger_savings(self):
        r10 = compute_mega_backdoor(employee_deferrals=23_500, employer_match=10_000, projection_years=10)
        r20 = compute_mega_backdoor(employee_deferrals=23_500, employer_match=10_000, projection_years=20)
        assert r20.projected_tax_savings > r10.projected_tax_savings

    def test_zero_space_no_projection(self):
        """No mega backdoor space → no projection values."""
        r = compute_mega_backdoor(
            employee_deferrals=23_500,
            employer_match=46_500,
        )
        assert r.projected_roth_value == 0
        assert r.projected_tax_savings == 0


# =========================================================================
# Serialization
# =========================================================================
class TestSerialization:
    def test_to_dict(self):
        r = compute_mega_backdoor(employee_deferrals=23_500, employer_match=10_000)
        d = result_to_dict(r)
        assert "limits" in d
        assert "inputs" in d
        assert "analysis" in d
        assert "projection" in d
        assert "recommendation" in d
        assert d["analysis"]["mega_backdoor_amount"] == 36_500

    def test_recommendation_text(self):
        r = compute_mega_backdoor(employee_deferrals=23_500, employer_match=10_000)
        d = result_to_dict(r)
        assert "Significant opportunity" in d["recommendation"]

    def test_no_space_recommendation(self):
        r = compute_mega_backdoor(employee_deferrals=23_500, employer_match=46_500)
        d = result_to_dict(r)
        assert "No after-tax space" in d["recommendation"]
        assert d["projection"] is None

    def test_json_serializable(self):
        import json
        r = compute_mega_backdoor(employee_deferrals=23_500, employer_match=10_000)
        d = result_to_dict(r)
        j = json.dumps(d)
        assert len(j) > 100
