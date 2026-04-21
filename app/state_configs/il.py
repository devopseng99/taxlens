"""Illinois state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Illinois",
    abbreviation="IL",
    tax_type="flat",
    form_name="IL-1040",
    rate=0.0495,
    personal_exemption=2_775,       # Per person (filer + spouse + dependents)
    reciprocal_states={"IA", "KY", "MI", "WI"},
)
