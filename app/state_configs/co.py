"""Colorado state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Colorado",
    abbreviation="CO",
    tax_type="flat",
    form_name="CO-104",
    rate=0.044,  # 4.4% flat rate (reduced from 4.55% in 2024)
    # CO uses federal taxable income as starting point (no separate standard deduction)
)
