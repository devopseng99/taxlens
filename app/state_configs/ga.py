"""Georgia state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Georgia",
    abbreviation="GA",
    tax_type="graduated",
    form_name="GA-500",
    standard_deduction={
        "single": 12_000,
        "mfj": 24_000,
        "hoh": 18_000,
        "mfs": 12_000,
    },
    personal_exemption=2_700,
    brackets={
        "single": [
            (750, 0.01),
            (2_250, 0.02),
            (3_750, 0.03),
            (5_250, 0.04),
            (7_000, 0.05),
            (float("inf"), 0.0549),
        ],
        "mfj": [
            (1_000, 0.01),
            (3_000, 0.02),
            (5_000, 0.03),
            (7_000, 0.04),
            (10_000, 0.05),
            (float("inf"), 0.0549),
        ],
        "hoh": [
            (1_000, 0.01),
            (3_000, 0.02),
            (5_000, 0.03),
            (7_000, 0.04),
            (10_000, 0.05),
            (float("inf"), 0.0549),
        ],
        "mfs": [
            (500, 0.01),
            (1_500, 0.02),
            (2_500, 0.03),
            (3_500, 0.04),
            (5_000, 0.05),
            (float("inf"), 0.0549),
        ],
    },
    ptet_available=True,
    ptet_entity_types={"s_corp", "partnership"},
)
