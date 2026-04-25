"""Wisconsin state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Wisconsin",
    abbreviation="WI",
    tax_type="graduated",
    form_name="WI-1",
    standard_deduction={
        "single": 12_760,
        "mfj": 23_620,
        "hoh": 16_740,
        "mfs": 11_810,
    },
    personal_exemption=700,
    brackets={
        "single": [
            (14_320, 0.0354),
            (28_640, 0.0465),
            (315_310, 0.0530),
            (float("inf"), 0.0765),
        ],
        "mfj": [
            (19_090, 0.0354),
            (38_190, 0.0465),
            (420_420, 0.0530),
            (float("inf"), 0.0765),
        ],
        "hoh": [
            (14_320, 0.0354),
            (28_640, 0.0465),
            (315_310, 0.0530),
            (float("inf"), 0.0765),
        ],
        "mfs": [
            (9_545, 0.0354),
            (19_090, 0.0465),
            (210_210, 0.0530),
            (float("inf"), 0.0765),
        ],
    },
    reciprocal_states={"IL", "IN", "KY", "MI"},
)
