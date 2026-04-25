"""Maryland state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Maryland",
    abbreviation="MD",
    tax_type="graduated",
    form_name="MD-502",
    standard_deduction={
        "single": 2_550,   # MD: 15% of AGI, min $1,800, max $2,550
        "mfj": 5_150,      # MD: 15% of AGI, min $3,650, max $5,150
        "hoh": 5_150,
        "mfs": 2_550,
    },
    personal_exemption=3_200,
    brackets={
        "single": [
            (1_000, 0.02),
            (2_000, 0.03),
            (3_000, 0.04),
            (100_000, 0.0475),
            (125_000, 0.05),
            (150_000, 0.0525),
            (250_000, 0.055),
            (float("inf"), 0.0575),
        ],
        "mfj": [
            (1_000, 0.02),
            (2_000, 0.03),
            (3_000, 0.04),
            (150_000, 0.0475),
            (175_000, 0.05),
            (225_000, 0.0525),
            (300_000, 0.055),
            (float("inf"), 0.0575),
        ],
        "hoh": [
            (1_000, 0.02),
            (2_000, 0.03),
            (3_000, 0.04),
            (150_000, 0.0475),
            (175_000, 0.05),
            (225_000, 0.0525),
            (300_000, 0.055),
            (float("inf"), 0.0575),
        ],
        "mfs": [
            (1_000, 0.02),
            (2_000, 0.03),
            (3_000, 0.04),
            (100_000, 0.0475),
            (125_000, 0.05),
            (150_000, 0.0525),
            (250_000, 0.055),
            (float("inf"), 0.0575),
        ],
    },
    reciprocal_states={"DC", "PA", "VA", "WV"},
    has_local_tax=True,  # County piggyback tax
)
