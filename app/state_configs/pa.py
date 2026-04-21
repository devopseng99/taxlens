"""Pennsylvania state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Pennsylvania",
    abbreviation="PA",
    tax_type="flat",
    form_name="PA-40",
    rate=0.0307,
    # PA has no personal exemption and no standard deduction
    reciprocal_states={"IN", "MD", "NJ", "OH", "VA", "WV"},
)
