"""North Carolina state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="North Carolina",
    abbreviation="NC",
    tax_type="flat",
    form_name="D-400",
    rate=0.045,
    standard_deduction={
        "single": 12_750,
        "mfj": 25_500,
        "hoh": 19_125,
        "mfs": 12_750,
    },
    ptet_available=True,
    ptet_entity_types={"s_corp", "partnership"},
)
