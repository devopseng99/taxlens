"""Massachusetts state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Massachusetts",
    abbreviation="MA",
    tax_type="flat",
    form_name="MA-1",
    rate=0.05,
    personal_exemption=4_400,  # single; MFJ = 8800
    # MA has a 4% surtax on income over $1M (Millionaire Tax, effective 2023)
    surtax_rate=0.04,
    surtax_threshold=1_000_000,
    ptet_available=True,
    ptet_entity_types={"s_corp", "partnership"},
)
