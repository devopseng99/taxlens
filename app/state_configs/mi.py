"""Michigan state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Michigan",
    abbreviation="MI",
    tax_type="flat",
    form_name="MI-1040",
    rate=0.0425,
    personal_exemption=5_400,
    reciprocal_states={"IL", "IN", "KY", "MN", "OH", "WI"},
)
