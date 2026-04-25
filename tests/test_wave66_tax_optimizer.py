"""Wave 66 tests — Intelligent Tax Optimization Engine."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Basic Optimization
# =========================================================================
class TestBasicOptimization:
    def test_returns_plan(self):
        from tax_optimizer import get_optimization_plan, OptimizationPlan
        plan = get_optimization_plan(wages=80000)
        assert isinstance(plan, OptimizationPlan)
        assert plan.current_tax > 0

    def test_has_recommendations(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000)
        assert len(plan.recommendations) > 0

    def test_recommendations_sorted_by_savings(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000)
        savings = [r.estimated_savings for r in plan.recommendations]
        assert savings == sorted(savings, reverse=True)

    def test_total_savings_sums_correctly(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000)
        expected = sum(r.estimated_savings for r in plan.recommendations)
        assert abs(plan.total_potential_savings - expected) < 0.02


# =========================================================================
# Specific Strategies
# =========================================================================
class TestStrategies:
    def test_hsa_recommendation(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000, has_hsa=False)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Maximize HSA Contributions" in strategies

    def test_ira_recommendation(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=60000, ira_contribution=0)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Maximize IRA Contribution" in strategies

    def test_401k_recommendation(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=100000, has_401k=True, contribution_401k=5000)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Maximize 401(k) Contributions" in strategies

    def test_capital_loss_harvesting(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000, capital_gains_long=10000, capital_losses=0)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Tax-Loss Harvesting" in strategies

    def test_qbi_for_business(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=50000, business_income=30000)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Claim QBI Deduction (Section 199A)" in strategies

    def test_roth_conversion_low_bracket(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=40000)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Roth Conversion Opportunity" in strategies

    def test_dependent_care_fsa(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000, num_dependents=2)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Dependent Care FSA" in strategies

    def test_mega_backdoor_roth_high_income(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=200000, has_401k=True)
        strategies = [r.strategy for r in plan.recommendations]
        assert "Mega Backdoor Roth" in strategies


# =========================================================================
# Recommendation Fields
# =========================================================================
class TestRecommendationFields:
    def test_recommendation_has_required_fields(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000)
        for r in plan.recommendations:
            assert r.strategy
            assert r.category in ("deduction", "credit", "timing", "structure", "retirement")
            assert r.difficulty in ("easy", "moderate", "complex")
            assert r.irs_risk in ("low", "medium", "high")
            assert r.description

    def test_action_items_are_lists(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=80000)
        for r in plan.recommendations:
            assert isinstance(r.action_items, list)


# =========================================================================
# Edge Cases
# =========================================================================
class TestEdgeCases:
    def test_zero_income(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=0)
        assert plan.current_tax == 0

    def test_high_income(self):
        from tax_optimizer import get_optimization_plan
        plan = get_optimization_plan(wages=500000)
        assert plan.current_tax > 0
        assert len(plan.recommendations) > 0


# =========================================================================
# API Endpoint
# =========================================================================
class TestEndpoint:
    def test_optimize_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/optimize" in src
        assert "get_optimization_plan" in src

    def test_optimizer_module_callable(self):
        from tax_optimizer import get_optimization_plan
        assert callable(get_optimization_plan)
