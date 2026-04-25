"""Audit risk scoring — statistical comparison against IRS norms.

Compares a completed TaxResult against IRS Statistics of Income (SOI)
averages by AGI bracket. Flags items that deviate significantly from
norms, giving filers a heads-up on what might trigger closer scrutiny.

DISCLAIMER: This is an educational tool, NOT audit prediction. The IRS
uses the DIF (Discriminant Information Function) score which is secret.
These are general heuristics based on public SOI data.
"""

from __future__ import annotations
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# IRS SOI norms by AGI bracket (simplified from IRS SOI Table 2.1, 2022)
# Values are approximate % of AGI or absolute thresholds
# ---------------------------------------------------------------------------
AGI_BRACKETS = [
    (25_000, "under_25k"),
    (50_000, "25k_50k"),
    (100_000, "50k_100k"),
    (200_000, "100k_200k"),
    (500_000, "200k_500k"),
    (1_000_000, "500k_1m"),
    (float("inf"), "over_1m"),
]

# Charitable giving as % of AGI — IRS norms by bracket
CHARITABLE_NORMS = {
    "under_25k": 0.08,    # ~8% of AGI (higher % at low income)
    "25k_50k": 0.04,
    "50k_100k": 0.03,
    "100k_200k": 0.035,
    "200k_500k": 0.04,
    "500k_1m": 0.05,
    "over_1m": 0.06,
}

# Schedule C: net profit margin norms (business expenses as % of gross)
SCHED_C_EXPENSE_RATIO_HIGH = 0.85   # Expense ratio > 85% is unusual
SCHED_C_LOSS_FLAG_YEARS = 3         # 3+ years of losses triggers hobby loss rule

# Home office deduction thresholds
HOME_OFFICE_PCT_HIGH = 0.30  # >30% of home used = unusual

# Overall audit rate multipliers (approximate, from IRS Data Book)
BASE_AUDIT_RATE = {
    "under_25k": 0.004,     # 0.4% — lower, but EITC audits are high
    "25k_50k": 0.002,       # 0.2%
    "50k_100k": 0.003,      # 0.3%
    "100k_200k": 0.004,     # 0.4%
    "200k_500k": 0.007,     # 0.7%
    "500k_1m": 0.011,       # 1.1%
    "over_1m": 0.023,       # 2.3% — highest audit rate
}


def _get_bracket(agi: float) -> str:
    for upper, name in AGI_BRACKETS:
        if agi <= upper:
            return name
    return "over_1m"


@dataclass
class RiskFlag:
    """A single audit risk indicator."""
    category: str        # e.g., "charitable", "schedule_c", "home_office"
    severity: str        # "low", "medium", "high"
    description: str     # Human-readable explanation
    your_value: str      # What the filer reported
    norm_value: str      # What's typical


@dataclass
class PassingCheck:
    """A check that passed (within normal range)."""
    category: str        # Same categories as RiskFlag
    description: str     # Human-readable explanation
    your_value: str      # What the filer reported
    norm_value: str      # What's typical (for context)


@dataclass
class AuditRiskReport:
    """Complete audit risk assessment for a tax return."""
    agi_bracket: str
    base_audit_rate_pct: float
    overall_risk: str       # "low", "medium", "high"
    risk_score: int          # 0-100
    flags: list[RiskFlag] = field(default_factory=list)
    passing_checks: list[PassingCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agi_bracket": self.agi_bracket,
            "base_audit_rate_pct": self.base_audit_rate_pct,
            "overall_risk": self.overall_risk,
            "risk_score": self.risk_score,
            "num_flags": len(self.flags),
            "flags": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "description": f.description,
                    "your_value": f.your_value,
                    "norm_value": f.norm_value,
                }
                for f in self.flags
            ],
            "num_passing": len(self.passing_checks),
            "passing_checks": [
                {
                    "category": p.category,
                    "description": p.description,
                    "your_value": p.your_value,
                    "norm_value": p.norm_value,
                }
                for p in self.passing_checks
            ],
        }


def assess_audit_risk(result) -> AuditRiskReport:
    """Analyze a TaxResult for audit risk indicators.

    Args:
        result: A TaxResult from compute_tax()

    Returns:
        AuditRiskReport with risk score and flagged items
    """
    agi = result.line_11_agi
    bracket = _get_bracket(agi)
    flags: list[RiskFlag] = []
    passing: list[PassingCheck] = []
    score = 0

    # --- 1. Charitable contributions vs AGI ---
    charitable = result.sched_a_charitable
    if agi > 0 and charitable > 0:
        ratio = charitable / agi
        norm = CHARITABLE_NORMS.get(bracket, 0.04)
        if ratio > norm * 3:
            flags.append(RiskFlag(
                category="charitable",
                severity="high",
                description="Charitable contributions are more than 3x the average for your income bracket",
                your_value=f"{ratio:.1%} of AGI (${charitable:,.0f})",
                norm_value=f"~{norm:.1%} of AGI typical",
            ))
            score += 25
        elif ratio > norm * 2:
            flags.append(RiskFlag(
                category="charitable",
                severity="medium",
                description="Charitable contributions are higher than typical for your income bracket",
                your_value=f"{ratio:.1%} of AGI (${charitable:,.0f})",
                norm_value=f"~{norm:.1%} of AGI typical",
            ))
            score += 10
        else:
            passing.append(PassingCheck(
                category="charitable",
                description="Charitable contributions are within normal range for your income bracket",
                your_value=f"{ratio:.1%} of AGI (${charitable:,.0f})",
                norm_value=f"~{norm:.1%} of AGI typical",
            ))
    elif charitable == 0 and result.deduction_type == "itemized":
        passing.append(PassingCheck(
            category="charitable",
            description="No charitable deductions claimed",
            your_value="$0",
            norm_value="N/A",
        ))

    # --- 2. Schedule C profit margin ---
    sched_c_checked = False
    for biz in getattr(result, 'sched_c_businesses', []):
        if isinstance(biz, dict):
            gross = biz.get("gross_receipts", 0)
            expenses = biz.get("expenses", 0)
            net = biz.get("net_profit", 0)
        else:
            gross = getattr(biz, 'gross_receipts', 0)
            expenses = getattr(biz, 'total_expenses', 0)
            net = getattr(biz, 'net_profit', 0)

        if gross > 0:
            sched_c_checked = True
            expense_ratio = expenses / gross
            if expense_ratio > SCHED_C_EXPENSE_RATIO_HIGH:
                flags.append(RiskFlag(
                    category="schedule_c",
                    severity="medium",
                    description=f"Business expense ratio is very high ({expense_ratio:.0%} of gross receipts)",
                    your_value=f"${expenses:,.0f} expenses / ${gross:,.0f} gross = {expense_ratio:.0%}",
                    norm_value=f"Typical expense ratio is under {SCHED_C_EXPENSE_RATIO_HIGH:.0%}",
                ))
                score += 15
            else:
                passing.append(PassingCheck(
                    category="schedule_c",
                    description="Business expense ratio is within normal range",
                    your_value=f"${expenses:,.0f} expenses / ${gross:,.0f} gross = {expense_ratio:.0%}",
                    norm_value=f"Typical expense ratio is under {SCHED_C_EXPENSE_RATIO_HIGH:.0%}",
                ))

            if net < 0:
                flags.append(RiskFlag(
                    category="schedule_c",
                    severity="medium",
                    description="Business reported a net loss — repeated losses may trigger hobby loss rules",
                    your_value=f"Net loss: ${abs(net):,.0f}",
                    norm_value="IRS scrutinizes businesses with 3+ years of losses in 5 years",
                ))
                score += 10
            else:
                passing.append(PassingCheck(
                    category="schedule_c",
                    description="Business is profitable",
                    your_value=f"Net profit: ${net:,.0f}",
                    norm_value="Profitable businesses attract less scrutiny",
                ))

    # --- 3. Home office deduction ---
    home_office_checked = False
    for biz in getattr(result, 'sched_c_businesses', []):
        if isinstance(biz, dict):
            home_sqft = biz.get("home_office_sqft", 0)
            total_sqft = biz.get("home_total_sqft", 0)
        else:
            home_sqft = getattr(biz, 'home_office_sqft', 0)
            total_sqft = getattr(biz, 'home_total_sqft', 0)

        if total_sqft > 0 and home_sqft > 0:
            home_office_checked = True
            pct = home_sqft / total_sqft
            if pct > HOME_OFFICE_PCT_HIGH:
                flags.append(RiskFlag(
                    category="home_office",
                    severity="medium",
                    description=f"Home office is {pct:.0%} of total home — unusually large",
                    your_value=f"{home_sqft:.0f} sq ft / {total_sqft:.0f} sq ft = {pct:.0%}",
                    norm_value=f"Typical is under {HOME_OFFICE_PCT_HIGH:.0%}",
                ))
                score += 10
            else:
                passing.append(PassingCheck(
                    category="home_office",
                    description="Home office percentage is within normal range",
                    your_value=f"{home_sqft:.0f} sq ft / {total_sqft:.0f} sq ft = {pct:.0%}",
                    norm_value=f"Typical is under {HOME_OFFICE_PCT_HIGH:.0%}",
                ))

    # --- 4. Large rental losses ---
    rental_loss = -result.sched_e_net_income if result.sched_e_net_income < 0 else 0
    if rental_loss > 0 and agi > 0:
        loss_ratio = rental_loss / agi
        if loss_ratio > 0.25:
            flags.append(RiskFlag(
                category="rental_loss",
                severity="medium",
                description="Rental loss is large relative to income",
                your_value=f"${rental_loss:,.0f} loss ({loss_ratio:.0%} of AGI)",
                norm_value="Large rental losses attract scrutiny, especially with high AGI",
            ))
            score += 10
        else:
            passing.append(PassingCheck(
                category="rental_loss",
                description="Rental loss is within acceptable range relative to income",
                your_value=f"${rental_loss:,.0f} loss ({loss_ratio:.0%} of AGI)",
                norm_value="Losses under 25% of AGI are typical",
            ))
    elif result.sched_e_net_income >= 0 and result.sched_e_net_income > 0:
        passing.append(PassingCheck(
            category="rental_loss",
            description="Rental income is positive (no loss)",
            your_value=f"Net rental income: ${result.sched_e_net_income:,.0f}",
            norm_value="Positive rental income does not attract scrutiny",
        ))

    # --- 5. High EITC with other income ---
    if result.eitc > 0 and agi > 0:
        # EITC claims have historically high audit rates
        if result.sched_c_total_profit > 0:
            flags.append(RiskFlag(
                category="eitc",
                severity="low",
                description="EITC claimed with self-employment income — this combination has elevated audit rates",
                your_value=f"EITC: ${result.eitc:,.0f}, SE income: ${result.sched_c_total_profit:,.0f}",
                norm_value="EITC+SE is the most audited combination in lower income brackets",
            ))
            score += 8
        else:
            passing.append(PassingCheck(
                category="eitc",
                description="EITC claimed without self-employment income — lower audit risk",
                your_value=f"EITC: ${result.eitc:,.0f}",
                norm_value="EITC without SE income has lower audit rates",
            ))

    # --- 6. Large cash charitable (non-receipted risk) ---
    if charitable > 500 and result.deduction_type == "itemized":
        if agi > 0 and charitable / agi > 0.10:
            # Already flagged above in ratio check, but add noncash warning
            noncash = getattr(result, 'sched_a_charitable', 0) - getattr(result, 'sched_a_charitable', 0)
            # Check noncash specifically from deductions
            pass  # Covered by ratio check above

    # --- 7. Very high AGI bracket ---
    if bracket in ("500k_1m", "over_1m"):
        flags.append(RiskFlag(
            category="income_level",
            severity="low",
            description="High-income returns have higher base audit rates",
            your_value=f"AGI: ${agi:,.0f}",
            norm_value=f"Base audit rate for {bracket}: {BASE_AUDIT_RATE[bracket]:.1%}",
        ))
        score += 5
    else:
        passing.append(PassingCheck(
            category="income_level",
            description="Income level has a normal base audit rate",
            your_value=f"AGI: ${agi:,.0f} ({bracket})",
            norm_value=f"Base audit rate: {BASE_AUDIT_RATE[bracket]:.1%}",
        ))

    # --- 8. Itemized deductions significantly above standard ---
    if result.deduction_type == "itemized":
        std = result.standard_deduction
        if result.itemized_total > std * 2:
            flags.append(RiskFlag(
                category="itemized_deductions",
                severity="low",
                description="Itemized deductions are more than double the standard deduction",
                your_value=f"${result.itemized_total:,.0f} itemized vs ${std:,.0f} standard",
                norm_value="Large itemized deductions may warrant documentation review",
            ))
            score += 5
        else:
            passing.append(PassingCheck(
                category="itemized_deductions",
                description="Itemized deductions are within reasonable range",
                your_value=f"${result.itemized_total:,.0f} itemized vs ${std:,.0f} standard",
                norm_value="Under 2x standard deduction is typical",
            ))
    else:
        passing.append(PassingCheck(
            category="itemized_deductions",
            description="Using standard deduction (no itemized scrutiny)",
            your_value=f"Standard deduction: ${result.standard_deduction:,.0f}",
            norm_value="Standard deduction does not attract scrutiny",
        ))

    # --- Compute overall risk ---
    score = min(score, 100)
    if score >= 40:
        overall = "high"
    elif score >= 20:
        overall = "medium"
    else:
        overall = "low"

    return AuditRiskReport(
        agi_bracket=bracket,
        base_audit_rate_pct=round(BASE_AUDIT_RATE.get(bracket, 0.003) * 100, 2),
        overall_risk=overall,
        risk_score=score,
        flags=flags,
        passing_checks=passing,
    )
