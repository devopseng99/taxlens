"""Minnesota state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Minnesota",
    abbreviation="MN",
    tax_type="graduated",
    form_name="MN-M1",
    standard_deduction={
        "single": 14_575,
        "mfj": 29_150,
        "hoh": 21_900,
        "mfs": 14_575,
    },
    brackets={
        "single": [
            (31_690, 0.0535),
            (104_090, 0.0680),
            (193_240, 0.0785),
            (float("inf"), 0.0985),
        ],
        "mfj": [
            (46_330, 0.0535),
            (184_040, 0.0680),
            (321_450, 0.0785),
            (float("inf"), 0.0985),
        ],
        "hoh": [
            (39_010, 0.0535),
            (155_780, 0.0680),
            (257_350, 0.0785),
            (float("inf"), 0.0985),
        ],
        "mfs": [
            (23_165, 0.0535),
            (92_020, 0.0680),
            (160_725, 0.0785),
            (float("inf"), 0.0985),
        ],
    },
    reciprocal_states={"MI", "ND"},
)
