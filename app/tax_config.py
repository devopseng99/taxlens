"""Federal & Illinois tax constants — multi-year support (2024 + 2025).

2024 constants: IRS Rev. Proc. 2023-34 (filed in 2025)
2025 constants: IRS Rev. Proc. 2024-40 (filed in 2026)
"""

from dataclasses import dataclass, field
from types import SimpleNamespace

TAX_YEAR = 2025  # Default tax year
SUPPORTED_TAX_YEARS = {2024, 2025}

# ---------------------------------------------------------------------------
# Filing statuses (constant across years)
# ---------------------------------------------------------------------------
SINGLE = "single"
MFJ = "mfj"           # Married Filing Jointly
HOH = "hoh"           # Head of Household
MFS = "mfs"           # Married Filing Separately (limited support)

FILING_STATUSES = {SINGLE, MFJ, HOH, MFS}

# ---------------------------------------------------------------------------
# Rates that do NOT change between years (statutory, not inflation-adjusted)
# ---------------------------------------------------------------------------
SS_RATE = 0.062
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
NIIT_RATE = 0.038
SE_TAX_RATE = 0.153
SE_INCOME_FACTOR = 0.9235
SE_SS_RATE = 0.124
SE_MEDICARE_RATE = 0.029
QBI_DEDUCTION_RATE = 0.20
AMT_RATE_LOW = 0.26
AMT_RATE_HIGH = 0.28
AOTC_MAX = 2_500
AOTC_REFUNDABLE_RATE = 0.40
LLC_MAX = 2_000
LLC_EXPENSE_RATE = 0.20
CDCC_MAX_RATE = 0.35
CDCC_MIN_RATE = 0.20
CDCC_RATE_STEP_AGI = 2_000
CDCC_RATE_START_AGI = 15_000
CDCC_MAX_EXPENSES_ONE = 3_000
CDCC_MAX_EXPENSES_TWO = 6_000
SAVERS_MAX_CONTRIBUTION = 2_000
CTC_PER_CHILD = 2_000
CTC_PHASEOUT_RATE = 50
ESTIMATED_TAX_PENALTY_THRESHOLD = 1_000
ESTIMATED_TAX_SAFE_HARBOR_PCT = 0.90
ESTIMATED_TAX_PRIOR_YEAR_PCT = 1.00
ESTIMATED_TAX_PRIOR_YEAR_HIGH_AGI = 1.10
SALT_CAP = 10_000
SALT_CAP_MFS = 5_000
STUDENT_LOAN_INTEREST_MAX = 2_500
MEDICAL_AGI_THRESHOLD = 0.075
HSA_CATCHUP = 1_000                  # Age 55+ catch-up (statutory, not indexed)
RENTAL_LOSS_LIMIT = 25_000           # Passive activity loss limit (statutory)
RENTAL_LOSS_PHASEOUT_START = 100_000 # AGI where $25K allowance starts phasing out
RENTAL_LOSS_PHASEOUT_END = 150_000   # AGI where allowance is fully phased out

# These thresholds are statutory (set by ACA/law), not inflation-adjusted
ADDITIONAL_MEDICARE_THRESHOLD = {
    SINGLE: 200_000, MFJ: 250_000, HOH: 200_000, MFS: 125_000,
}
NIIT_THRESHOLD = {
    SINGLE: 200_000, MFJ: 250_000, HOH: 200_000, MFS: 125_000,
}
CTC_PHASEOUT_START = {
    SINGLE: 200_000, MFJ: 400_000, HOH: 200_000, MFS: 200_000,
}
ESTIMATED_TAX_HIGH_AGI_THRESHOLD = {
    SINGLE: 150_000, MFJ: 150_000, HOH: 150_000, MFS: 75_000,
}
# Education credit phaseout ranges (AOTC — statutory, not inflation-adjusted)
EDUCATION_CREDIT_PHASEOUT = {
    SINGLE: (80_000, 90_000),
    MFJ:    (160_000, 180_000),
    HOH:    (80_000, 90_000),
    MFS:    (0, 0),
}


# ============================================================================
# Year-specific inflation-adjusted constants
# ============================================================================

_YEAR_2024 = {
    # Federal brackets — IRS Rev. Proc. 2023-34
    "FEDERAL_BRACKETS": {
        SINGLE: [
            (11_600, 0.10), (47_150, 0.12), (100_525, 0.22),
            (191_950, 0.24), (243_725, 0.32), (609_350, 0.35),
            (float("inf"), 0.37),
        ],
        MFJ: [
            (23_200, 0.10), (94_300, 0.12), (201_050, 0.22),
            (383_900, 0.24), (487_450, 0.32), (731_200, 0.35),
            (float("inf"), 0.37),
        ],
        HOH: [
            (16_550, 0.10), (63_100, 0.12), (100_525, 0.22),
            (191_950, 0.24), (243_700, 0.32), (609_350, 0.35),
            (float("inf"), 0.37),
        ],
        MFS: [
            (11_600, 0.10), (47_150, 0.12), (100_525, 0.22),
            (191_950, 0.24), (243_725, 0.32), (365_600, 0.35),
            (float("inf"), 0.37),
        ],
    },
    "STANDARD_DEDUCTION": {SINGLE: 14_600, MFJ: 29_200, HOH: 21_900, MFS: 14_600},
    "LTCG_BRACKETS": {
        SINGLE: [(47_025, 0.00), (518_900, 0.15), (float("inf"), 0.20)],
        MFJ:    [(94_050, 0.00), (583_750, 0.15), (float("inf"), 0.20)],
        HOH:    [(63_000, 0.00), (551_350, 0.15), (float("inf"), 0.20)],
        MFS:    [(47_025, 0.00), (291_850, 0.15), (float("inf"), 0.20)],
    },
    "SS_WAGE_BASE": 168_600,
    "CTC_REFUNDABLE_MAX": 1_700,
    # AMT — Rev. Proc. 2023-34
    "AMT_EXEMPTION": {SINGLE: 85_700, MFJ: 133_300, HOH: 85_700, MFS: 66_650},
    "AMT_PHASEOUT_START": {SINGLE: 609_350, MFJ: 1_218_700, HOH: 609_350, MFS: 609_350},
    "AMT_RATE_BREAK": {SINGLE: 232_600, MFJ: 232_600, HOH: 232_600, MFS: 116_300},
    # QBI — Rev. Proc. 2023-34
    "QBI_TAXABLE_INCOME_LIMIT": {SINGLE: 182_100, MFJ: 364_200, HOH: 182_100, MFS: 182_100},
    "QBI_PHASEOUT_RANGE": {SINGLE: 50_000, MFJ: 100_000, HOH: 50_000, MFS: 50_000},
    # EITC — Rev. Proc. 2023-34
    "EITC_MAX_CREDIT": {0: 632, 1: 4_213, 2: 6_960, 3: 7_830},
    "EITC_PHASE_IN_RATE": {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45},
    "EITC_PHASE_OUT_RATE": {0: 0.0765, 1: 0.1598, 2: 0.2106, 3: 0.2106},
    "EITC_EARNED_INCOME_AMOUNT": {0: 8_260, 1: 12_390, 2: 17_400, 3: 17_400},
    "EITC_PHASEOUT_START": {
        SINGLE: {0: 10_330, 1: 21_560, 2: 21_560, 3: 21_560},
        HOH:    {0: 10_330, 1: 21_560, 2: 21_560, 3: 21_560},
        MFJ:    {0: 17_250, 1: 28_480, 2: 28_480, 3: 28_480},
        MFS:    {0: 10_330, 1: 21_560, 2: 21_560, 3: 21_560},
    },
    "EITC_INVESTMENT_INCOME_LIMIT": 11_600,
    # Saver's — Rev. Proc. 2023-34
    "SAVERS_AGI_TIERS": {
        SINGLE: (23_000, 25_000, 36_500),
        HOH:    (34_500, 37_500, 54_750),
        MFJ:    (46_000, 50_000, 73_000),
        MFS:    (23_000, 25_000, 36_500),
    },
    # HSA — Rev. Proc. 2023-34
    "HSA_LIMIT_SELF": 4_150,
    "HSA_LIMIT_FAMILY": 8_300,
    # HDHP requirements (informational, for Form 8889) — Rev. Proc. 2023-34
    "HDHP_MIN_DEDUCTIBLE_SELF": 1_600,
    "HDHP_MIN_DEDUCTIBLE_FAMILY": 3_200,
    "HDHP_MAX_OOP_SELF": 8_050,
    "HDHP_MAX_OOP_FAMILY": 16_100,
    # Estimated tax penalty rate (IRS sets quarterly)
    "ESTIMATED_TAX_PENALTY_RATE": 0.08,
    # Illinois
    "IL_FLAT_RATE": 0.0495,
    "IL_PERSONAL_EXEMPTION": 2_625,
}

_YEAR_2025 = {
    # Federal brackets — IRS Rev. Proc. 2024-40
    "FEDERAL_BRACKETS": {
        SINGLE: [
            (11_925, 0.10), (48_475, 0.12), (103_350, 0.22),
            (197_300, 0.24), (250_525, 0.32), (626_350, 0.35),
            (float("inf"), 0.37),
        ],
        MFJ: [
            (23_850, 0.10), (96_950, 0.12), (206_700, 0.22),
            (394_600, 0.24), (501_050, 0.32), (751_600, 0.35),
            (float("inf"), 0.37),
        ],
        HOH: [
            (17_000, 0.10), (64_850, 0.12), (103_350, 0.22),
            (197_300, 0.24), (250_500, 0.32), (626_350, 0.35),
            (float("inf"), 0.37),
        ],
        MFS: [
            (11_925, 0.10), (48_475, 0.12), (103_350, 0.22),
            (197_300, 0.24), (250_525, 0.32), (375_800, 0.35),
            (float("inf"), 0.37),
        ],
    },
    "STANDARD_DEDUCTION": {SINGLE: 15_000, MFJ: 30_000, HOH: 22_500, MFS: 15_000},
    "LTCG_BRACKETS": {
        SINGLE: [(48_350, 0.00), (533_400, 0.15), (float("inf"), 0.20)],
        MFJ:    [(96_700, 0.00), (600_050, 0.15), (float("inf"), 0.20)],
        HOH:    [(64_750, 0.00), (566_700, 0.15), (float("inf"), 0.20)],
        MFS:    [(48_350, 0.00), (300_000, 0.15), (float("inf"), 0.20)],
    },
    "SS_WAGE_BASE": 176_100,
    "CTC_REFUNDABLE_MAX": 1_700,
    # AMT — Rev. Proc. 2024-40
    "AMT_EXEMPTION": {SINGLE: 88_100, MFJ: 137_000, HOH: 88_100, MFS: 68_500},
    "AMT_PHASEOUT_START": {SINGLE: 626_350, MFJ: 1_252_700, HOH: 626_350, MFS: 626_350},
    "AMT_RATE_BREAK": {SINGLE: 239_100, MFJ: 239_100, HOH: 239_100, MFS: 119_550},
    # QBI — Rev. Proc. 2024-40
    "QBI_TAXABLE_INCOME_LIMIT": {SINGLE: 191_950, MFJ: 383_900, HOH: 191_950, MFS: 191_950},
    "QBI_PHASEOUT_RANGE": {SINGLE: 50_000, MFJ: 100_000, HOH: 50_000, MFS: 50_000},
    # EITC — Rev. Proc. 2024-40
    "EITC_MAX_CREDIT": {0: 649, 1: 4_328, 2: 7_152, 3: 8_046},
    "EITC_PHASE_IN_RATE": {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45},
    "EITC_PHASE_OUT_RATE": {0: 0.0765, 1: 0.1598, 2: 0.2106, 3: 0.2106},
    "EITC_EARNED_INCOME_AMOUNT": {0: 8_490, 1: 12_730, 2: 17_880, 3: 17_880},
    "EITC_PHASEOUT_START": {
        SINGLE: {0: 10_620, 1: 22_080, 2: 22_080, 3: 22_080},
        HOH:    {0: 10_620, 1: 22_080, 2: 22_080, 3: 22_080},
        MFJ:    {0: 17_740, 1: 29_200, 2: 29_200, 3: 29_200},
        MFS:    {0: 10_620, 1: 22_080, 2: 22_080, 3: 22_080},
    },
    "EITC_INVESTMENT_INCOME_LIMIT": 11_600,
    # Saver's — Rev. Proc. 2024-40
    "SAVERS_AGI_TIERS": {
        SINGLE: (23_750, 25_750, 36_500),
        HOH:    (35_625, 38_625, 54_750),
        MFJ:    (47_500, 51_500, 73_000),
        MFS:    (23_750, 25_750, 36_500),
    },
    # HSA — Rev. Proc. 2024-40
    "HSA_LIMIT_SELF": 4_300,
    "HSA_LIMIT_FAMILY": 8_550,
    # HDHP requirements (informational, for Form 8889) — Rev. Proc. 2024-40
    "HDHP_MIN_DEDUCTIBLE_SELF": 1_650,
    "HDHP_MIN_DEDUCTIBLE_FAMILY": 3_300,
    "HDHP_MAX_OOP_SELF": 8_300,
    "HDHP_MAX_OOP_FAMILY": 16_600,
    # Estimated tax penalty rate
    "ESTIMATED_TAX_PENALTY_RATE": 0.08,
    # Illinois
    "IL_FLAT_RATE": 0.0495,
    "IL_PERSONAL_EXEMPTION": 2_775,
}

_YEAR_CONFIGS = {2024: _YEAR_2024, 2025: _YEAR_2025}


def get_year_config(tax_year: int = 2025) -> SimpleNamespace:
    """Get all tax constants for a given tax year.

    Returns a SimpleNamespace with all year-varying constants as attributes,
    plus all fixed-rate constants for convenience.
    """
    if tax_year not in _YEAR_CONFIGS:
        raise ValueError(f"Unsupported tax year: {tax_year}. Supported: {sorted(_YEAR_CONFIGS.keys())}")

    cfg = _YEAR_CONFIGS[tax_year]
    ns = SimpleNamespace(**cfg)

    # Add fixed-rate constants (same for all years)
    ns.SS_RATE = SS_RATE
    ns.MEDICARE_RATE = MEDICARE_RATE
    ns.ADDITIONAL_MEDICARE_RATE = ADDITIONAL_MEDICARE_RATE
    ns.ADDITIONAL_MEDICARE_THRESHOLD = ADDITIONAL_MEDICARE_THRESHOLD
    ns.NIIT_RATE = NIIT_RATE
    ns.NIIT_THRESHOLD = NIIT_THRESHOLD
    ns.SE_TAX_RATE = SE_TAX_RATE
    ns.SE_INCOME_FACTOR = SE_INCOME_FACTOR
    ns.SE_SS_RATE = SE_SS_RATE
    ns.SE_MEDICARE_RATE = SE_MEDICARE_RATE
    ns.QBI_DEDUCTION_RATE = QBI_DEDUCTION_RATE
    ns.AMT_RATE_LOW = AMT_RATE_LOW
    ns.AMT_RATE_HIGH = AMT_RATE_HIGH
    ns.AOTC_MAX = AOTC_MAX
    ns.AOTC_REFUNDABLE_RATE = AOTC_REFUNDABLE_RATE
    ns.LLC_MAX = LLC_MAX
    ns.LLC_EXPENSE_RATE = LLC_EXPENSE_RATE
    ns.EDUCATION_CREDIT_PHASEOUT = EDUCATION_CREDIT_PHASEOUT
    ns.CDCC_MAX_RATE = CDCC_MAX_RATE
    ns.CDCC_MIN_RATE = CDCC_MIN_RATE
    ns.CDCC_RATE_STEP_AGI = CDCC_RATE_STEP_AGI
    ns.CDCC_RATE_START_AGI = CDCC_RATE_START_AGI
    ns.CDCC_MAX_EXPENSES_ONE = CDCC_MAX_EXPENSES_ONE
    ns.CDCC_MAX_EXPENSES_TWO = CDCC_MAX_EXPENSES_TWO
    ns.SAVERS_MAX_CONTRIBUTION = SAVERS_MAX_CONTRIBUTION
    ns.CTC_PER_CHILD = CTC_PER_CHILD
    ns.CTC_PHASEOUT_START = CTC_PHASEOUT_START
    ns.CTC_PHASEOUT_RATE = CTC_PHASEOUT_RATE
    ns.ESTIMATED_TAX_PENALTY_THRESHOLD = ESTIMATED_TAX_PENALTY_THRESHOLD
    ns.ESTIMATED_TAX_SAFE_HARBOR_PCT = ESTIMATED_TAX_SAFE_HARBOR_PCT
    ns.ESTIMATED_TAX_PRIOR_YEAR_PCT = ESTIMATED_TAX_PRIOR_YEAR_PCT
    ns.ESTIMATED_TAX_PRIOR_YEAR_HIGH_AGI = ESTIMATED_TAX_PRIOR_YEAR_HIGH_AGI
    ns.ESTIMATED_TAX_HIGH_AGI_THRESHOLD = ESTIMATED_TAX_HIGH_AGI_THRESHOLD
    ns.SALT_CAP = SALT_CAP
    ns.SALT_CAP_MFS = SALT_CAP_MFS
    ns.STUDENT_LOAN_INTEREST_MAX = STUDENT_LOAN_INTEREST_MAX
    ns.MEDICAL_AGI_THRESHOLD = MEDICAL_AGI_THRESHOLD
    ns.HSA_CATCHUP = HSA_CATCHUP
    ns.RENTAL_LOSS_LIMIT = RENTAL_LOSS_LIMIT
    ns.RENTAL_LOSS_PHASEOUT_START = RENTAL_LOSS_PHASEOUT_START
    ns.RENTAL_LOSS_PHASEOUT_END = RENTAL_LOSS_PHASEOUT_END

    return ns


# ---------------------------------------------------------------------------
# Backward compatibility — module-level constants default to 2025
# Existing code that does `from tax_config import *` still works unchanged.
# ---------------------------------------------------------------------------
_default = get_year_config(2025)
FEDERAL_BRACKETS = _default.FEDERAL_BRACKETS
STANDARD_DEDUCTION = _default.STANDARD_DEDUCTION
LTCG_BRACKETS = _default.LTCG_BRACKETS
SS_WAGE_BASE = _default.SS_WAGE_BASE
CTC_REFUNDABLE_MAX = _default.CTC_REFUNDABLE_MAX
AMT_EXEMPTION = _default.AMT_EXEMPTION
AMT_PHASEOUT_START = _default.AMT_PHASEOUT_START
AMT_RATE_BREAK = _default.AMT_RATE_BREAK
QBI_TAXABLE_INCOME_LIMIT = _default.QBI_TAXABLE_INCOME_LIMIT
QBI_PHASEOUT_RANGE = _default.QBI_PHASEOUT_RANGE
EITC_MAX_CREDIT = _default.EITC_MAX_CREDIT
EITC_PHASE_IN_RATE = _default.EITC_PHASE_IN_RATE
EITC_PHASE_OUT_RATE = _default.EITC_PHASE_OUT_RATE
EITC_EARNED_INCOME_AMOUNT = _default.EITC_EARNED_INCOME_AMOUNT
EITC_PHASEOUT_START = _default.EITC_PHASEOUT_START
EITC_INVESTMENT_INCOME_LIMIT = _default.EITC_INVESTMENT_INCOME_LIMIT
SAVERS_AGI_TIERS = _default.SAVERS_AGI_TIERS
ESTIMATED_TAX_PENALTY_RATE = _default.ESTIMATED_TAX_PENALTY_RATE
IL_FLAT_RATE = _default.IL_FLAT_RATE
IL_PERSONAL_EXEMPTION = _default.IL_PERSONAL_EXEMPTION
