"""Virginia state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Virginia",
    abbreviation="VA",
    tax_type="graduated",
    form_name="VA-760",
    personal_exemption=930,
    standard_deduction={
        "single": 8_000,
        "mfj": 16_000,
        "hoh": 8_000,
        "mfs": 8_000,
    },
    brackets={
        "single": [
            (3_000, 0.02),
            (5_000, 0.03),
            (17_000, 0.05),
            (float("inf"), 0.0575),
        ],
        "mfj": [
            (3_000, 0.02),
            (5_000, 0.03),
            (17_000, 0.05),
            (float("inf"), 0.0575),
        ],
        "hoh": [
            (3_000, 0.02),
            (5_000, 0.03),
            (17_000, 0.05),
            (float("inf"), 0.0575),
        ],
        "mfs": [
            (3_000, 0.02),
            (5_000, 0.03),
            (17_000, 0.05),
            (float("inf"), 0.0575),
        ],
    },
    reciprocal_states={"DC", "KY", "MD", "PA", "WV"},
    ptet_available=True,
    ptet_entity_types={"s_corp", "partnership"},
)
