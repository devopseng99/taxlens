"""Withholding analyzer — gap analysis and W-4 recommendations."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WithholdingInput:
    """Current withholding situation."""
    filing_status: str = "single"
    annual_wages: float = 0.0
    federal_withheld_ytd: float = 0.0
    pay_periods_per_year: int = 26       # biweekly default
    pay_periods_elapsed: int = 0         # how many paychecks received so far
    current_w4_extra: float = 0.0        # extra withholding per pay period
    num_dependents: int = 0
    other_income: float = 0.0            # interest, dividends, etc.
    deductions_above_standard: float = 0.0  # itemized - standard (if positive)
    estimated_payments: float = 0.0      # quarterly estimated payments made
    target_refund: float = 0.0           # desired refund amount (0 = break even)


@dataclass
class WithholdingResult:
    """Analysis result with W-4 recommendations."""
    projected_tax: float = 0.0
    projected_withholding: float = 0.0
    projected_estimated: float = 0.0
    projected_total_payments: float = 0.0
    gap: float = 0.0                     # positive = underpaid, negative = overpaid
    gap_description: str = ""
    at_risk_of_penalty: bool = False
    safe_harbor_amount: float = 0.0

    # W-4 recommendation
    recommended_extra_per_period: float = 0.0
    remaining_periods: int = 0
    adjustment_description: str = ""

    # Target refund mode
    target_refund: float = 0.0
    target_withholding: float = 0.0      # total withholding needed for target

    # Breakdown
    effective_rate: float = 0.0
    marginal_rate: float = 0.0


def analyze_withholding(inp: WithholdingInput) -> WithholdingResult:
    """Analyze withholding gap and recommend W-4 adjustments."""
    from tax_engine import (
        PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
        compute_tax,
    )
    from tax_config import get_year_config

    cfg = get_year_config(2025)
    result = WithholdingResult()
    result.target_refund = inp.target_refund

    # Compute projected tax liability
    filer = PersonInfo(first_name="Projection", last_name="User")
    deductions = Deductions()
    if inp.deductions_above_standard > 0:
        deductions.salt = min(inp.deductions_above_standard, 10000)
        remainder = inp.deductions_above_standard - deductions.salt
        if remainder > 0:
            deductions.mortgage_interest = remainder

    additional = AdditionalIncome(
        other_interest=inp.other_income * 0.5,
        ordinary_dividends=inp.other_income * 0.5,
    )

    tax_result = compute_tax(
        filing_status=inp.filing_status,
        filer=filer,
        w2s=[W2Income(wages=inp.annual_wages, federal_withheld=0)],
        deductions=deductions,
        additional=additional,
        payments=Payments(),
    )

    result.projected_tax = tax_result.line_24_total_tax
    result.effective_rate = (
        result.projected_tax / inp.annual_wages if inp.annual_wages > 0 else 0
    )

    # Marginal rate from brackets — format is (upper_limit, rate)
    brackets = cfg.FEDERAL_BRACKETS.get(inp.filing_status, cfg.FEDERAL_BRACKETS["single"])
    result.marginal_rate = brackets[0][1]  # lowest bracket default
    for upper_limit, rate in brackets:
        if tax_result.line_15_taxable_income <= upper_limit:
            result.marginal_rate = rate
            break

    # Project withholding for full year
    if inp.pay_periods_elapsed > 0 and inp.pay_periods_per_year > 0:
        per_period_withholding = inp.federal_withheld_ytd / inp.pay_periods_elapsed
        result.projected_withholding = per_period_withholding * inp.pay_periods_per_year
    else:
        result.projected_withholding = inp.federal_withheld_ytd

    result.projected_estimated = inp.estimated_payments
    result.projected_total_payments = (
        result.projected_withholding + result.projected_estimated
    )

    # Gap: positive = underpaid
    result.gap = result.projected_tax - result.projected_total_payments
    if result.gap > 100:
        result.gap_description = (
            f"Underpaid by ${result.gap:,.0f}. You may owe at filing."
        )
    elif result.gap < -100:
        result.gap_description = (
            f"Overpaid by ${abs(result.gap):,.0f}. You're on track for a refund."
        )
    else:
        result.gap_description = "Withholding is approximately on target."

    # Safe harbor: 100% of prior year tax (we use current as proxy)
    # or 110% if AGI > $150k
    agi_threshold = 150000 if inp.filing_status == "mfj" else 75000
    safe_harbor_pct = 1.10 if inp.annual_wages > agi_threshold else 1.00
    result.safe_harbor_amount = result.projected_tax * safe_harbor_pct
    result.at_risk_of_penalty = (
        result.projected_total_payments < min(
            result.projected_tax * 0.90,
            result.safe_harbor_amount,
        )
        and result.gap > 1000
    )

    # Remaining periods
    result.remaining_periods = max(
        1, inp.pay_periods_per_year - inp.pay_periods_elapsed
    )

    # Calculate needed withholding for target refund
    needed_total = result.projected_tax + inp.target_refund
    result.target_withholding = needed_total

    shortfall = needed_total - result.projected_total_payments
    if shortfall > 0:
        result.recommended_extra_per_period = round(
            shortfall / result.remaining_periods, 2
        )
        result.adjustment_description = (
            f"Add ${result.recommended_extra_per_period:,.2f} extra withholding "
            f"per pay period for the remaining {result.remaining_periods} periods "
            f"to {'reach your target ${:,.0f} refund'.format(inp.target_refund) if inp.target_refund > 0 else 'break even at filing'}."
        )
    elif shortfall < -100:
        excess_per_period = round(abs(shortfall) / result.remaining_periods, 2)
        result.recommended_extra_per_period = 0
        result.adjustment_description = (
            f"You can reduce extra withholding by ~${excess_per_period:,.2f} per "
            f"pay period. Current pace produces a ~${abs(shortfall):,.0f} refund "
            f"{'(vs your target ${:,.0f})'.format(inp.target_refund) if inp.target_refund > 0 else 'beyond break-even'}."
        )
    else:
        result.recommended_extra_per_period = 0
        result.adjustment_description = (
            "No W-4 adjustment needed — withholding is on track."
        )

    return result
