"""Texas state tax configuration — 2025 tax year.

Texas has no state income tax.
"""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Texas",
    abbreviation="TX",
    tax_type="none",
)
