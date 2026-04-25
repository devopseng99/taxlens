"""Pluggable state tax configuration modules.

Each state is a separate module (e.g., state_configs/il.py) exporting a STATE_CONFIG object.
States are loaded dynamically via get_state_config().
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StateConfig:
    """Tax configuration for a single state."""
    name: str                                    # "Illinois"
    abbreviation: str                            # "IL"
    tax_type: str                                # "flat", "graduated", "none"
    form_name: str = ""                          # "IL-1040"

    # Flat-rate states
    rate: float = 0.0                            # e.g., 0.0495 for IL

    # Graduated-bracket states: {filing_status: [(upper_limit, rate), ...]}
    brackets: dict = field(default_factory=dict)

    # Exemptions & deductions
    personal_exemption: float = 0.0              # Per-person exemption amount
    standard_deduction: dict = field(default_factory=dict)  # {filing_status: amount}

    # Multi-state
    reciprocal_states: set = field(default_factory=set)  # States with reciprocal agreements
    has_local_tax: bool = False                  # NYC, OH municipal, etc.

    # Surtaxes
    surtax_rate: float = 0.0                     # e.g., CA Mental Health 1%
    surtax_threshold: float = 0.0                # e.g., $1M for CA

    # PTET (Pass-Through Entity Tax)
    ptet_available: bool = False                  # State offers PTET election
    ptet_entity_types: set = field(default_factory=set)  # e.g., {"s_corp", "partnership"}

    # Entity-level replacement/franchise taxes
    pprt_rate: float = 0.0                        # Personal Property Replacement Tax (IL: 1.5%)
    pprt_entity_types: set = field(default_factory=set)  # Entity types subject to PPRT


@dataclass
class StateTaxResult:
    """Result of a single state tax computation."""
    state_code: str = ""
    state_name: str = ""
    form_name: str = ""
    return_type: str = "resident"                # "resident" or "nonresident"

    # Income
    federal_agi: float = 0.0
    additions: float = 0.0
    subtractions: float = 0.0
    base_income: float = 0.0
    exemptions: float = 0.0
    standard_deduction_amount: float = 0.0
    taxable_income: float = 0.0

    # Tax
    tax: float = 0.0
    surtax: float = 0.0
    total_tax: float = 0.0

    # Payments
    withholding: float = 0.0
    estimated_payments: float = 0.0
    credit_for_other_states: float = 0.0

    # Bottom line
    refund: float = 0.0
    owed: float = 0.0

    # PTET credit
    ptet_credit: float = 0.0                     # PTET credit applied to this state

    # Entity-level taxes
    pprt_tax: float = 0.0                        # IL Personal Property Replacement Tax

    # Allocation (for nonresident returns)
    allocated_income: float = 0.0                # Income sourced to this state
    allocation_pct: float = 1.0                  # Fraction of income allocated


# Cache for loaded state configs
_config_cache: dict[str, Optional[StateConfig]] = {}

# States with no income tax
NO_TAX_STATES = {"AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"}


def get_state_config(state_code: str) -> Optional[StateConfig]:
    """Load a state's tax configuration module dynamically.

    Returns None if the state has no income tax or no config module exists.
    """
    state_code = state_code.upper()

    if state_code in _config_cache:
        return _config_cache[state_code]

    if state_code in NO_TAX_STATES:
        _config_cache[state_code] = None
        return None

    try:
        # 'in' is a Python keyword, so Indiana uses 'in_.py'
        module_name = state_code.lower()
        if module_name == "in":
            module_name = "in_"
        mod = importlib.import_module(f"state_configs.{module_name}")
        config = getattr(mod, "STATE_CONFIG", None)
        _config_cache[state_code] = config
        return config
    except ModuleNotFoundError:
        _config_cache[state_code] = None
        return None


def clear_config_cache():
    """Clear the config cache (useful for testing)."""
    _config_cache.clear()
