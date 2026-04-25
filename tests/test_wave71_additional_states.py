"""Wave 71 tests — Additional 10 state tax engines (VA, MA, WA, MI, AZ, CO, MN, MD, WI, IN)."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from state_configs import get_state_config, clear_config_cache, NO_TAX_STATES


@pytest.fixture(autouse=True)
def clear_cache():
    clear_config_cache()
    yield
    clear_config_cache()


# =========================================================================
# Config Loading
# =========================================================================
class TestConfigLoading:
    @pytest.mark.parametrize("state", ["VA", "MA", "MI", "AZ", "CO", "MN", "MD", "WI", "IN"])
    def test_config_loads(self, state):
        config = get_state_config(state)
        assert config is not None
        assert config.abbreviation == state

    def test_wa_is_no_tax(self):
        assert "WA" in NO_TAX_STATES
        assert get_state_config("WA") is None

    @pytest.mark.parametrize("state,expected_type", [
        ("VA", "graduated"), ("MA", "flat"), ("MI", "flat"),
        ("AZ", "flat"), ("CO", "flat"), ("MN", "graduated"),
        ("MD", "graduated"), ("WI", "graduated"), ("IN", "flat"),
    ])
    def test_tax_types(self, state, expected_type):
        config = get_state_config(state)
        assert config.tax_type == expected_type


# =========================================================================
# Flat-Rate States
# =========================================================================
class TestFlatStates:
    def test_ma_rate(self):
        config = get_state_config("MA")
        assert config.rate == 0.05

    def test_ma_surtax(self):
        config = get_state_config("MA")
        assert config.surtax_rate == 0.04
        assert config.surtax_threshold == 1_000_000

    def test_mi_rate(self):
        config = get_state_config("MI")
        assert config.rate == 0.0425

    def test_az_rate(self):
        config = get_state_config("AZ")
        assert config.rate == 0.025

    def test_co_rate(self):
        config = get_state_config("CO")
        assert config.rate == 0.044

    def test_in_rate(self):
        config = get_state_config("IN")
        assert config.rate == 0.0305


# =========================================================================
# Graduated-Bracket States
# =========================================================================
class TestGraduatedStates:
    def test_va_brackets(self):
        config = get_state_config("VA")
        assert len(config.brackets["single"]) == 4
        assert config.brackets["single"][-1][1] == 0.0575

    def test_mn_brackets(self):
        config = get_state_config("MN")
        assert len(config.brackets["single"]) == 4
        assert config.brackets["single"][-1][1] == 0.0985

    def test_md_brackets(self):
        config = get_state_config("MD")
        assert len(config.brackets["single"]) == 8
        assert config.brackets["single"][-1][1] == 0.0575

    def test_wi_brackets(self):
        config = get_state_config("WI")
        assert len(config.brackets["single"]) == 4
        assert config.brackets["single"][-1][1] == 0.0765


# =========================================================================
# Reciprocal Agreements
# =========================================================================
class TestReciprocal:
    def test_va_reciprocal(self):
        config = get_state_config("VA")
        assert "PA" in config.reciprocal_states
        assert "DC" in config.reciprocal_states

    def test_md_reciprocal(self):
        config = get_state_config("MD")
        assert "VA" in config.reciprocal_states
        assert "PA" in config.reciprocal_states
        assert "DC" in config.reciprocal_states

    def test_mi_reciprocal(self):
        config = get_state_config("MI")
        assert "OH" in config.reciprocal_states
        assert "IN" in config.reciprocal_states
        assert "WI" in config.reciprocal_states

    def test_wi_reciprocal(self):
        config = get_state_config("WI")
        assert "IL" in config.reciprocal_states
        assert "IN" in config.reciprocal_states
        assert "MI" in config.reciprocal_states

    def test_in_reciprocal(self):
        config = get_state_config("IN")
        assert "OH" in config.reciprocal_states
        assert "MI" in config.reciprocal_states
        assert "WI" in config.reciprocal_states

    def test_mn_reciprocal(self):
        config = get_state_config("MN")
        assert "MI" in config.reciprocal_states


# =========================================================================
# State Tax Computation
# =========================================================================
class TestComputation:
    @pytest.mark.parametrize("state", ["VA", "MA", "MI", "AZ", "CO", "MN", "MD", "WI", "IN"])
    def test_compute_produces_result(self, state):
        from state_tax_engine import compute_state_tax
        result = compute_state_tax(state, "single", 80000)
        assert result.total_tax > 0
        assert result.state_code == state

    def test_flat_state_computation(self):
        from state_tax_engine import compute_state_tax
        result = compute_state_tax("MI", "single", 80000)
        # MI: 4.25% of (AGI - exemptions)
        assert result.total_tax > 0
        assert result.total_tax < 80000 * 0.0425  # Less than gross due to exemption

    def test_graduated_state_computation(self):
        from state_tax_engine import compute_state_tax
        result = compute_state_tax("VA", "single", 80000)
        assert result.total_tax > 0
        # VA top rate is 5.75%
        assert result.total_tax < 80000 * 0.0575

    def test_wa_no_tax(self):
        from state_tax_engine import compute_state_tax
        result = compute_state_tax("WA", "single", 80000)
        assert result.total_tax == 0

    def test_total_states_now_20(self):
        """Verify we now support 20 states (10 original + 9 new + WA no-tax)."""
        supported = ["IL", "CA", "NY", "NJ", "PA", "NC", "GA", "OH", "TX", "FL",
                      "VA", "MA", "MI", "AZ", "CO", "MN", "MD", "WI", "IN", "WA"]
        for state in supported:
            if state in NO_TAX_STATES:
                continue
            config = get_state_config(state)
            assert config is not None, f"Missing config for {state}"
