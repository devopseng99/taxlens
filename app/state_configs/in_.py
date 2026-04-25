"""Indiana state tax configuration — 2025 tax year.

Note: File is in_.py (not in.py) because 'in' is a Python keyword.
The __init__.py get_state_config() imports via state code, so this must be
registered manually or via alias.
"""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Indiana",
    abbreviation="IN",
    tax_type="flat",
    form_name="IN-IT40",
    rate=0.0305,  # 3.05% flat rate (reduced from 3.15% in 2024)
    personal_exemption=1_000,
    reciprocal_states={"KY", "MI", "OH", "PA", "WI"},
    has_local_tax=True,  # County income tax (varies by county)
    ptet_available=True,
    ptet_entity_types={"s_corp", "partnership"},
)
