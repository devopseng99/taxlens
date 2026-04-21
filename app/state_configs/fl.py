"""Florida state tax configuration — 2025 tax year.

Florida has no state income tax.
"""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Florida",
    abbreviation="FL",
    tax_type="none",
)
