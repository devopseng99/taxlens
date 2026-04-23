"""2025 Federal & Illinois tax constants — filed in 2026."""

TAX_YEAR = 2025

# ---------------------------------------------------------------------------
# Filing statuses
# ---------------------------------------------------------------------------
SINGLE = "single"
MFJ = "mfj"           # Married Filing Jointly
HOH = "hoh"           # Head of Household
MFS = "mfs"           # Married Filing Separately (limited support)

FILING_STATUSES = {SINGLE, MFJ, HOH, MFS}

# ---------------------------------------------------------------------------
# Federal income tax brackets (ordinary income)
# Source: IRS Rev. Proc. 2024-40
# ---------------------------------------------------------------------------
FEDERAL_BRACKETS = {
    SINGLE: [
        (11_925,   0.10),
        (48_475,   0.12),
        (103_350,  0.22),
        (197_300,  0.24),
        (250_525,  0.32),
        (626_350,  0.35),
        (float("inf"), 0.37),
    ],
    MFJ: [
        (23_850,   0.10),
        (96_950,   0.12),
        (206_700,  0.22),
        (394_600,  0.24),
        (501_050,  0.32),
        (751_600,  0.35),
        (float("inf"), 0.37),
    ],
    HOH: [
        (17_000,   0.10),
        (64_850,   0.12),
        (103_350,  0.22),
        (197_300,  0.24),
        (250_500,  0.32),
        (626_350,  0.35),
        (float("inf"), 0.37),
    ],
    MFS: [
        (11_925,   0.10),
        (48_475,   0.12),
        (103_350,  0.22),
        (197_300,  0.24),
        (250_525,  0.32),
        (375_800,  0.35),
        (float("inf"), 0.37),
    ],
}

# ---------------------------------------------------------------------------
# Standard deduction
# ---------------------------------------------------------------------------
STANDARD_DEDUCTION = {
    SINGLE: 15_000,
    MFJ:    30_000,
    HOH:    22_500,
    MFS:    15_000,
}

# ---------------------------------------------------------------------------
# Long-term capital gains brackets (0% / 15% / 20%)
# ---------------------------------------------------------------------------
LTCG_BRACKETS = {
    SINGLE: [
        (48_350,  0.00),
        (533_400, 0.15),
        (float("inf"), 0.20),
    ],
    MFJ: [
        (96_700,  0.00),
        (600_050, 0.15),
        (float("inf"), 0.20),
    ],
    HOH: [
        (64_750,  0.00),
        (566_700, 0.15),
        (float("inf"), 0.20),
    ],
    MFS: [
        (48_350,  0.00),
        (300_000, 0.15),
        (float("inf"), 0.20),
    ],
}

# ---------------------------------------------------------------------------
# FICA
# ---------------------------------------------------------------------------
SS_WAGE_BASE = 176_100
SS_RATE = 0.062
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLD = {
    SINGLE: 200_000,
    MFJ:    250_000,
    HOH:    200_000,
    MFS:    125_000,
}

# ---------------------------------------------------------------------------
# Net Investment Income Tax (NIIT)
# ---------------------------------------------------------------------------
NIIT_RATE = 0.038
NIIT_THRESHOLD = {
    SINGLE: 200_000,
    MFJ:    250_000,
    HOH:    200_000,
    MFS:    125_000,
}

# ---------------------------------------------------------------------------
# Deduction limits
# ---------------------------------------------------------------------------
SALT_CAP = 10_000            # State & local tax deduction cap
SALT_CAP_MFS = 5_000
STUDENT_LOAN_INTEREST_MAX = 2_500
MEDICAL_AGI_THRESHOLD = 0.075  # 7.5% of AGI floor

# ---------------------------------------------------------------------------
# Child Tax Credit (2025)
# ---------------------------------------------------------------------------
CTC_PER_CHILD = 2_000
CTC_REFUNDABLE_MAX = 1_700   # Additional Child Tax Credit
CTC_PHASEOUT_START = {
    SINGLE: 200_000,
    MFJ:    400_000,
    HOH:    200_000,
    MFS:    200_000,
}
CTC_PHASEOUT_RATE = 50  # $50 reduction per $1,000 over threshold

# ---------------------------------------------------------------------------
# Self-Employment Tax (Schedule SE)
# ---------------------------------------------------------------------------
SE_TAX_RATE = 0.153            # 12.4% SS + 2.9% Medicare
SE_INCOME_FACTOR = 0.9235      # 92.35% of net SE income is taxable
SE_SS_RATE = 0.124
SE_MEDICARE_RATE = 0.029
# SS wage base shared with FICA (SS_WAGE_BASE above)

# ---------------------------------------------------------------------------
# Qualified Business Income (QBI) Deduction — Section 199A
# ---------------------------------------------------------------------------
QBI_DEDUCTION_RATE = 0.20      # 20% of QBI
QBI_TAXABLE_INCOME_LIMIT = {   # Below this, full 20% with no phase-out
    SINGLE: 191_950,
    MFJ:    383_900,
    HOH:    191_950,
    MFS:    191_950,
}
QBI_PHASEOUT_RANGE = {         # Phase-out occurs over this range above the limit
    SINGLE: 50_000,
    MFJ:    100_000,
    HOH:    50_000,
    MFS:    50_000,
}

# ---------------------------------------------------------------------------
# Alternative Minimum Tax (AMT) — Form 6251 (2025)
# Source: IRS Rev. Proc. 2024-40
# ---------------------------------------------------------------------------
AMT_EXEMPTION = {
    SINGLE: 88_100,
    MFJ:    137_000,
    HOH:    88_100,
    MFS:    68_500,
}
AMT_PHASEOUT_START = {
    SINGLE: 626_350,
    MFJ:    1_252_700,
    HOH:    626_350,
    MFS:    626_350,
}
AMT_RATE_LOW = 0.26       # 26% on first $239,100 ($119,550 MFS)
AMT_RATE_HIGH = 0.28      # 28% on excess
AMT_RATE_BREAK = {
    SINGLE: 239_100,
    MFJ:    239_100,
    HOH:    239_100,
    MFS:    119_550,
}

# ---------------------------------------------------------------------------
# Education Credits — Form 8863 (2025)
# Source: IRS Rev. Proc. 2024-40
# ---------------------------------------------------------------------------
AOTC_MAX = 2_500                    # American Opportunity (100% of $2K + 25% of next $2K)
AOTC_REFUNDABLE_RATE = 0.40         # 40% of AOTC is refundable
LLC_MAX = 2_000                     # Lifetime Learning Credit (20% of $10K expenses)
LLC_EXPENSE_RATE = 0.20
EDUCATION_CREDIT_PHASEOUT = {       # MAGI phaseout ranges
    SINGLE: (80_000, 90_000),
    MFJ:    (160_000, 180_000),
    HOH:    (80_000, 90_000),
    MFS:    (0, 0),                 # MFS: cannot claim education credits
}

# ---------------------------------------------------------------------------
# Illinois State Tax (2025)
# ---------------------------------------------------------------------------
IL_FLAT_RATE = 0.0495
IL_PERSONAL_EXEMPTION = 2_775  # Per person
