"""Ohio state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="Ohio",
    abbreviation="OH",
    tax_type="graduated",
    form_name="IT-1040",
    # Ohio has no standard deduction or personal exemption for state income tax
    # but has a personal exemption credit built into the brackets
    brackets={
        "single": [
            (26_050, 0.0),          # 0% bracket (effectively an exemption)
            (46_100, 0.02765),
            (92_150, 0.03226),
            (115_300, 0.03688),
            (float("inf"), 0.0350),  # Top rate reduced in 2025
        ],
        "mfj": [
            (26_050, 0.0),
            (46_100, 0.02765),
            (92_150, 0.03226),
            (115_300, 0.03688),
            (float("inf"), 0.0350),
        ],
        "hoh": [
            (26_050, 0.0),
            (46_100, 0.02765),
            (92_150, 0.03226),
            (115_300, 0.03688),
            (float("inf"), 0.0350),
        ],
        "mfs": [
            (26_050, 0.0),
            (46_100, 0.02765),
            (92_150, 0.03226),
            (115_300, 0.03688),
            (float("inf"), 0.0350),
        ],
    },
    reciprocal_states={"IN", "KY", "MI", "PA", "WV"},
    has_local_tax=True,             # Ohio municipalities have local income tax
)
