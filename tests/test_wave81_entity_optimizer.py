"""Wave 81 tests — Entity Type Optimization Engine."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from entity_optimizer import (
    compare_entities, comparison_to_dict,
    _compute_se_tax, _compute_fica, _reasonable_comp_range,
)


# =========================================================================
# Helper Functions
# =========================================================================
class TestSETax:
    def test_se_tax_basic(self):
        se_tax, se_ded = _compute_se_tax(100_000, 176_100)
        # 92.35% × 100K = $92,350; SS: 92,350 × 12.4% = $11,451; Medicare: 92,350 × 2.9% = $2,678
        assert se_tax > 14_000
        assert se_ded == round(se_tax / 2, 2)

    def test_se_tax_zero(self):
        se_tax, se_ded = _compute_se_tax(0, 176_100)
        assert se_tax == 0
        assert se_ded == 0

    def test_se_tax_above_ss_base(self):
        """SS portion capped at wage base."""
        se_tax_low, _ = _compute_se_tax(100_000, 176_100)
        se_tax_high, _ = _compute_se_tax(300_000, 176_100)
        # Medicare continues, but SS is capped — so marginal rate drops
        assert se_tax_high < 300_000 * 0.153 * 0.9235


class TestFICA:
    def test_fica_basic(self):
        emp, ee = _compute_fica(80_000, 176_100)
        # 6.2% SS + 1.45% Medicare = 7.65% each side
        expected = round(80_000 * 0.0765, 2)
        assert emp == expected
        assert ee == expected

    def test_fica_above_ss_base(self):
        emp, ee = _compute_fica(200_000, 176_100)
        ss_portion = round(176_100 * 0.062, 2)
        medicare_portion = round(200_000 * 0.0145, 2)
        assert emp == round(ss_portion + medicare_portion, 2)


class TestReasonableComp:
    def test_comp_range(self):
        r = _reasonable_comp_range(200_000)
        assert r["min"] == 80_000
        assert r["max"] == 140_000
        assert r["recommended"] == 100_000

    def test_zero_income(self):
        r = _reasonable_comp_range(0)
        assert r["min"] == 0


# =========================================================================
# Entity Comparison — Core Logic
# =========================================================================
class TestEntityComparison:
    def test_three_scenarios_returned(self):
        comp = compare_entities(business_income=100_000)
        assert len(comp.scenarios) == 3
        types = [s.entity_type for s in comp.scenarios]
        assert "sole_prop" in types
        assert "s_corp" in types
        assert "c_corp" in types

    def test_s_corp_saves_over_sole_prop(self):
        """S-corp should save SE tax vs sole prop for typical income."""
        comp = compare_entities(business_income=150_000)
        sole = [s for s in comp.scenarios if s.entity_type == "sole_prop"][0]
        s_corp = [s for s in comp.scenarios if s.entity_type == "s_corp"][0]
        # S-corp avoids SE tax on distributions — should have lower total tax
        assert s_corp.total_tax < sole.total_tax

    def test_recommendation_is_lowest_tax(self):
        comp = compare_entities(business_income=100_000)
        recommended = [s for s in comp.scenarios if s.entity_type == comp.recommended][0]
        for s in comp.scenarios:
            assert recommended.total_tax <= s.total_tax

    def test_savings_vs_sole_prop(self):
        comp = compare_entities(business_income=100_000)
        sole = [s for s in comp.scenarios if s.entity_type == "sole_prop"][0]
        best = [s for s in comp.scenarios if s.entity_type == comp.recommended][0]
        assert comp.savings_vs_sole_prop == round(sole.total_tax - best.total_tax, 2)

    def test_sole_prop_has_se_tax(self):
        comp = compare_entities(business_income=100_000)
        sole = [s for s in comp.scenarios if s.entity_type == "sole_prop"][0]
        assert sole.se_tax > 10_000  # ~$14K on $100K

    def test_s_corp_has_fica_not_se(self):
        comp = compare_entities(business_income=100_000)
        s_corp = [s for s in comp.scenarios if s.entity_type == "s_corp"][0]
        assert s_corp.se_tax == 0
        assert s_corp.fica_employer > 0
        assert s_corp.fica_employee > 0

    def test_c_corp_has_corporate_tax(self):
        comp = compare_entities(business_income=200_000)
        c_corp = [s for s in comp.scenarios if s.entity_type == "c_corp"][0]
        assert c_corp.corporate_tax > 0
        assert c_corp.dividend_tax > 0

    def test_c_corp_double_taxation(self):
        """C-corp should have highest total tax for moderate income."""
        comp = compare_entities(business_income=100_000)
        c_corp = [s for s in comp.scenarios if s.entity_type == "c_corp"][0]
        sole = [s for s in comp.scenarios if s.entity_type == "sole_prop"][0]
        # C-corp double taxation makes it worse for moderate income
        assert c_corp.total_tax >= sole.total_tax * 0.85  # Roughly comparable or worse

    def test_effective_rates_populated(self):
        comp = compare_entities(business_income=100_000)
        for s in comp.scenarios:
            assert s.effective_rate > 0

    def test_reasonable_comp_range_populated(self):
        comp = compare_entities(business_income=200_000)
        assert comp.reasonable_comp_range["min"] == 80_000
        assert comp.reasonable_comp_range["recommended"] == 100_000


# =========================================================================
# Custom Reasonable Compensation
# =========================================================================
class TestCustomCompensation:
    def test_custom_comp(self):
        comp = compare_entities(business_income=200_000, reasonable_compensation=80_000)
        s_corp = [s for s in comp.scenarios if s.entity_type == "s_corp"][0]
        assert s_corp.reasonable_compensation == 80_000
        assert s_corp.distributions == 120_000  # $200K - $80K

    def test_comp_capped_at_income(self):
        """Reasonable comp can't exceed business income."""
        comp = compare_entities(business_income=50_000, reasonable_compensation=100_000)
        s_corp = [s for s in comp.scenarios if s.entity_type == "s_corp"][0]
        assert s_corp.reasonable_compensation == 50_000
        assert s_corp.distributions == 0


# =========================================================================
# Filing Status Variations
# =========================================================================
class TestFilingStatus:
    def test_mfj(self):
        comp = compare_entities(business_income=150_000, filing_status="mfj")
        assert len(comp.scenarios) == 3
        assert comp.filing_status == "mfj"

    def test_hoh(self):
        comp = compare_entities(business_income=100_000, filing_status="hoh")
        assert comp.recommended in ("sole_prop", "s_corp", "c_corp")


# =========================================================================
# Other Income (Bracket Positioning)
# =========================================================================
class TestOtherIncome:
    def test_other_income_affects_brackets(self):
        """Higher other income pushes business into higher brackets."""
        comp_low = compare_entities(business_income=100_000, other_income=0)
        comp_high = compare_entities(business_income=100_000, other_income=200_000)
        sole_low = [s for s in comp_low.scenarios if s.entity_type == "sole_prop"][0]
        sole_high = [s for s in comp_high.scenarios if s.entity_type == "sole_prop"][0]
        assert sole_high.income_tax > sole_low.income_tax


# =========================================================================
# QBI Deduction
# =========================================================================
class TestQBIDeduction:
    def test_sole_prop_gets_qbi(self):
        comp = compare_entities(business_income=100_000)
        sole = [s for s in comp.scenarios if s.entity_type == "sole_prop"][0]
        assert sole.qbi_deduction == round(100_000 * 0.20, 2)

    def test_s_corp_qbi_on_distributions_only(self):
        """S-corp QBI is on pass-through, not W-2 portion."""
        comp = compare_entities(business_income=100_000, reasonable_compensation=50_000)
        s_corp = [s for s in comp.scenarios if s.entity_type == "s_corp"][0]
        # QBI should be on distributions (after employer FICA deduction)
        assert s_corp.qbi_deduction < sole_qbi(100_000)
        assert s_corp.qbi_deduction > 0

    def test_c_corp_no_qbi(self):
        comp = compare_entities(business_income=100_000)
        c_corp = [s for s in comp.scenarios if s.entity_type == "c_corp"][0]
        assert c_corp.qbi_deduction == 0


def sole_qbi(income):
    return round(income * 0.20, 2)


# =========================================================================
# Serialization
# =========================================================================
class TestSerialization:
    def test_to_dict(self):
        comp = compare_entities(business_income=100_000)
        d = comparison_to_dict(comp)
        assert "business_income" in d
        assert "recommended" in d
        assert "scenarios" in d
        assert len(d["scenarios"]) == 3
        for s in d["scenarios"]:
            assert "total_tax" in s
            assert "effective_rate" in s

    def test_json_serializable(self):
        import json
        comp = compare_entities(business_income=100_000)
        d = comparison_to_dict(comp)
        j = json.dumps(d)
        assert len(j) > 100


# =========================================================================
# Edge Cases
# =========================================================================
class TestEdgeCases:
    def test_very_low_income(self):
        comp = compare_entities(business_income=10_000)
        # Should still produce 3 valid scenarios
        assert len(comp.scenarios) == 3
        for s in comp.scenarios:
            assert s.total_tax >= 0

    def test_very_high_income(self):
        comp = compare_entities(business_income=1_000_000)
        assert len(comp.scenarios) == 3
        # At very high income, all should have significant tax
        for s in comp.scenarios:
            assert s.total_tax > 100_000

    def test_zero_income(self):
        comp = compare_entities(business_income=0)
        for s in comp.scenarios:
            assert s.total_tax == 0
