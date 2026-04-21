"""California state tax configuration — 2025 tax year."""

from state_configs import StateConfig

STATE_CONFIG = StateConfig(
    name="California",
    abbreviation="CA",
    tax_type="graduated",
    form_name="CA-540",
    personal_exemption=144,         # Per-person credit (actually a credit, modeled as exemption)
    standard_deduction={
        "single": 5_540,
        "mfj": 11_080,
        "hoh": 11_080,
        "mfs": 5_540,
    },
    brackets={
        "single": [
            (10_756, 0.01),
            (25_499, 0.02),
            (40_245, 0.04),
            (55_866, 0.06),
            (70_612, 0.08),
            (360_659, 0.093),
            (432_787, 0.103),
            (721_314, 0.113),
            (1_000_000, 0.123),
            (float("inf"), 0.133),
        ],
        "mfj": [
            (21_512, 0.01),
            (50_998, 0.02),
            (80_490, 0.04),
            (111_732, 0.06),
            (141_224, 0.08),
            (721_318, 0.093),
            (865_574, 0.103),
            (1_000_000, 0.113),
            (1_442_628, 0.123),
            (float("inf"), 0.133),
        ],
        "hoh": [
            (21_527, 0.01),
            (51_000, 0.02),
            (65_744, 0.04),
            (81_364, 0.06),
            (96_111, 0.08),
            (490_493, 0.093),
            (588_593, 0.103),
            (980_987, 0.113),
            (1_000_000, 0.123),
            (float("inf"), 0.133),
        ],
        "mfs": [
            (10_756, 0.01),
            (25_499, 0.02),
            (40_245, 0.04),
            (55_866, 0.06),
            (70_612, 0.08),
            (360_659, 0.093),
            (432_787, 0.103),
            (721_314, 0.113),
            (1_000_000, 0.123),
            (float("inf"), 0.133),
        ],
    },
    surtax_rate=0.01,               # Mental Health Services Tax
    surtax_threshold=1_000_000,     # On income > $1M
)
