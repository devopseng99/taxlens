"""Arizona state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Arizona",
    abbreviation="AZ",
    tax_type="flat",
    form_name="AZ-140",
    rate=0.025,  # Flat 2.5% effective 2023
    standard_deduction={
        "single": 14_600,
        "mfj": 29_200,
        "hoh": 21_900,
        "mfs": 14_600,
    },
    ptet_available=True,
    ptet_entity_types={"s_corp", "partnership"},
)
