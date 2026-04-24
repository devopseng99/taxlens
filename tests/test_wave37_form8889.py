"""Wave 37 — Form 8889 HSA Reporting tests.

Tests Form 8889 line item computation, employer contributions,
excess contribution detection, summary output, and MCP integration.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from tax_engine import (
    compute_tax, HSAContribution, PersonInfo, W2Income,
    Deductions, AdditionalIncome, Payments, TaxResult,
)
from tax_config import get_year_config


def _base_result(**kwargs):
    """Compute a basic return with HSA contributions."""
    defaults = dict(
        filing_status="single",
        filer=PersonInfo(first_name="Jane", last_name="Doe"),
        w2s=[W2Income(wages=80_000, federal_withheld=12_000)],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
    )
    defaults.update(kwargs)
    return compute_tax(**defaults)


# -----------------------------------------------------------------------
# Form 8889 Line Computation
# -----------------------------------------------------------------------

class TestForm8889Lines:
    """Test Form 8889 line item calculations."""

    def test_personal_contributions_only(self):
        """Personal contributions tracked on Line 2."""
        r = _base_result(hsa_contributions=[
            HSAContribution(contribution_amount=3_000, coverage_type="self"),
        ])
        assert r.form_8889_contributions == 3_000
        assert r.form_8889_employer == 0
        assert r.form_8889_deduction == 3_000
        assert r.hsa_deduction == 3_000

    def test_employer_contributions_tracked(self):
        """Employer contributions recorded on Line 9."""
        r = _base_result(hsa_contributions=[
            HSAContribution(
                contribution_amount=2_000,
                employer_contributions=1_500,
                coverage_type="self",
            ),
        ])
        assert r.form_8889_contributions == 2_000
        assert r.form_8889_employer == 1_500
        assert r.form_8889_deduction == 2_000  # 4300 limit - 1500 employer = 2800 room > 2000

    def test_employer_reduces_deductible_room(self):
        """When employer fills most of the limit, personal deduction is reduced."""
        c = get_year_config(2025)
        r = _base_result(hsa_contributions=[
            HSAContribution(
                contribution_amount=3_000,
                employer_contributions=3_000,
                coverage_type="self",
            ),
        ])
        # Limit = 4300, employer = 3000, room = 1300
        assert r.form_8889_deduction == 1_300
        assert r.hsa_deduction == 1_300

    def test_employer_exceeds_limit_no_deduction(self):
        """When employer contributions alone exceed limit, personal deduction = 0."""
        r = _base_result(hsa_contributions=[
            HSAContribution(
                contribution_amount=1_000,
                employer_contributions=5_000,
                coverage_type="self",
            ),
        ])
        # Limit = 4300, employer = 5000 > limit, room = 0
        assert r.form_8889_deduction == 0
        assert r.hsa_deduction == 0

    def test_contribution_limit_self_2025(self):
        """Line 7 = $4,300 for self-only coverage (2025)."""
        r = _base_result(hsa_contributions=[
            HSAContribution(contribution_amount=4_300, coverage_type="self"),
        ])
        assert r.form_8889_limit == 4_300

    def test_contribution_limit_family_2025(self):
        """Line 7 = $8,550 for family coverage (2025)."""
        r = _base_result(hsa_contributions=[
            HSAContribution(contribution_amount=5_000, coverage_type="family"),
        ])
        assert r.form_8889_limit == 8_550

    def test_catchup_increases_limit(self):
        """Age 55+ catch-up adds $1,000 to limit."""
        r = _base_result(hsa_contributions=[
            HSAContribution(
                contribution_amount=5_300,
                coverage_type="self",
                age_55_plus=True,
            ),
        ])
        assert r.form_8889_limit == 5_300  # 4300 + 1000

    def test_2024_limits(self):
        """2024 uses Rev. Proc. 2023-34 limits."""
        r = compute_tax(
            filing_status="single",
            filer=PersonInfo(first_name="Jane", last_name="Doe"),
            w2s=[W2Income(wages=80_000, federal_withheld=12_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            hsa_contributions=[
                HSAContribution(contribution_amount=4_200, coverage_type="self"),
            ],
            tax_year=2024,
        )
        assert r.form_8889_limit == 4_150  # 2024 self limit
        assert r.form_8889_deduction == 4_150  # Capped at limit


# -----------------------------------------------------------------------
# Excess Contribution Detection
# -----------------------------------------------------------------------

class TestExcessContributions:
    """Test excess contribution detection (6% excise via Form 5329)."""

    def test_no_excess_within_limit(self):
        """No excess when total <= limit."""
        r = _base_result(hsa_contributions=[
            HSAContribution(contribution_amount=4_000, coverage_type="self"),
        ])
        assert r.form_8889_excess == 0

    def test_excess_personal_over_limit(self):
        """Excess when personal contributions exceed limit."""
        r = _base_result(hsa_contributions=[
            HSAContribution(contribution_amount=5_000, coverage_type="self"),
        ])
        # Total = 5000, limit = 4300, excess = 700
        assert r.form_8889_excess == 700

    def test_excess_combined_over_limit(self):
        """Excess when personal + employer exceed limit."""
        r = _base_result(hsa_contributions=[
            HSAContribution(
                contribution_amount=3_000,
                employer_contributions=2_000,
                coverage_type="self",
            ),
        ])
        # Total = 5000, limit = 4300, excess = 700
        assert r.form_8889_excess == 700

    def test_no_excess_with_catchup(self):
        """Catch-up prevents excess for 55+ filers."""
        r = _base_result(hsa_contributions=[
            HSAContribution(
                contribution_amount=5_000,
                coverage_type="self",
                age_55_plus=True,
            ),
        ])
        # Limit = 4300 + 1000 = 5300 > 5000
        assert r.form_8889_excess == 0


# -----------------------------------------------------------------------
# Summary and Forms Generated
# -----------------------------------------------------------------------

class TestSummaryAndForms:
    """Test summary output and forms list."""

    def test_form_8889_in_forms_generated(self):
        """Form 8889 appears in forms_generated when HSA contributions present."""
        r = _base_result(hsa_contributions=[
            HSAContribution(contribution_amount=2_000, coverage_type="self"),
        ])
        assert "Form 8889" in r.forms_generated

    def test_no_form_8889_without_hsa(self):
        """Form 8889 not generated when no HSA contributions."""
        r = _base_result()
        assert "Form 8889" not in r.forms_generated

    def test_summary_form_8889_section(self):
        """Summary includes form_8889 section with all fields."""
        r = _base_result(hsa_contributions=[
            HSAContribution(
                contribution_amount=3_000,
                employer_contributions=1_000,
                coverage_type="self",
            ),
        ])
        s = r.to_summary()
        assert s["form_8889"] is not None
        assert s["form_8889"]["personal_contributions"] == 3_000
        assert s["form_8889"]["employer_contributions"] == 1_000
        assert s["form_8889"]["contribution_limit"] == 4_300
        assert s["form_8889"]["deduction"] == 3_000  # 4300 - 1000 = 3300 room > 3000

    def test_summary_no_form_8889_without_hsa(self):
        """Summary form_8889 is None when no HSA."""
        r = _base_result()
        s = r.to_summary()
        assert s.get("form_8889") is None


# -----------------------------------------------------------------------
# MCP Integration
# -----------------------------------------------------------------------

class TestMCPIntegration:
    """Test MCP server integration with Form 8889 fields."""

    def test_build_inputs_employer_contributions(self):
        """_build_inputs passes employer_contributions through."""
        from mcp_server import _build_inputs
        inputs = _build_inputs(
            filing_status="single",
            hsa_contributions=[{
                "contribution_amount": 3000,
                "employer_contributions": 1500,
                "coverage_type": "self",
            }],
        )
        hsa_list = inputs["hsa_contributions"]
        assert len(hsa_list) == 1
        assert hsa_list[0].employer_contributions == 1500

    def test_get_tax_config_hdhp_limits(self):
        """get_tax_config returns HDHP limits for Form 8889."""
        c = get_year_config(2025)
        assert c.HDHP_MIN_DEDUCTIBLE_SELF == 1_650
        assert c.HDHP_MIN_DEDUCTIBLE_FAMILY == 3_300
        assert c.HDHP_MAX_OOP_SELF == 8_300
        assert c.HDHP_MAX_OOP_FAMILY == 16_600

    def test_get_tax_config_hdhp_2024(self):
        """2024 HDHP limits are different."""
        c = get_year_config(2024)
        assert c.HDHP_MIN_DEDUCTIBLE_SELF == 1_600
        assert c.HDHP_MIN_DEDUCTIBLE_FAMILY == 3_200


# -----------------------------------------------------------------------
# Backward Compatibility
# -----------------------------------------------------------------------

class TestBackwardCompat:
    """Ensure existing HSA behavior is preserved."""

    def test_no_employer_contributions_default(self):
        """employer_contributions defaults to 0."""
        hsa = HSAContribution(contribution_amount=3_000)
        assert hsa.employer_contributions == 0

    def test_existing_hsa_deduction_unchanged(self):
        """HSA deduction without employer contributions works as before."""
        r = _base_result(hsa_contributions=[
            HSAContribution(contribution_amount=4_000, coverage_type="self"),
        ])
        assert r.hsa_deduction == 4_000
        assert r.form_8889_deduction == 4_000
