"""Multi-state tax computation engine.

Supports:
- Flat-rate states (IL, PA, NC)
- Graduated-bracket states (CA, NY, NJ, GA, OH)
- No-tax states (TX, FL, AK, etc.)
- Multi-state workers: nonresident returns + resident return with credits
- Reciprocal agreements
"""

from __future__ import annotations

from typing import Optional

from state_configs import (
    StateConfig,
    StateTaxResult,
    NO_TAX_STATES,
    get_state_config,
)
from tax_config import MFJ


def compute_bracket_tax(taxable_income: float, brackets: list) -> float:
    """Compute tax from graduated brackets. Each bracket: (upper_limit, rate)."""
    tax = 0.0
    prev = 0.0
    for upper, rate in brackets:
        if taxable_income <= 0:
            break
        span = min(taxable_income, upper) - prev
        if span > 0:
            tax += span * rate
        prev = upper
        if taxable_income <= upper:
            break
    return tax


def compute_state_tax(
    state_code: str,
    filing_status: str,
    federal_agi: float,
    state_withholding: float = 0.0,
    estimated_payments: float = 0.0,
    num_exemptions: int = 1,
    return_type: str = "resident",
    allocated_income: Optional[float] = None,
    allocation_pct: float = 1.0,
    credit_for_other_states: float = 0.0,
) -> StateTaxResult:
    """Compute state income tax for a single state.

    Args:
        state_code: Two-letter state abbreviation (e.g., "IL", "CA")
        filing_status: Federal filing status ("single", "mfj", "hoh", "mfs")
        federal_agi: Federal adjusted gross income
        state_withholding: State tax withheld from W-2s
        estimated_payments: Estimated state tax payments made
        num_exemptions: Number of personal exemptions (filer + spouse + dependents)
        return_type: "resident" or "nonresident"
        allocated_income: For nonresident returns, the income sourced to this state
        allocation_pct: Fraction of income allocated to this state (0.0-1.0)
        credit_for_other_states: Credit for taxes paid to other states (resident returns)
    """
    state_code = state_code.upper()
    result = StateTaxResult(state_code=state_code, return_type=return_type)

    # No-tax states
    if state_code in NO_TAX_STATES:
        return result

    config = get_state_config(state_code)
    if config is None:
        return result

    result.state_name = config.name
    result.form_name = config.form_name
    result.federal_agi = federal_agi

    # Determine taxable base
    if return_type == "nonresident" and allocated_income is not None:
        base_income = allocated_income
        result.allocated_income = allocated_income
        result.allocation_pct = allocation_pct
    else:
        base_income = federal_agi

    result.base_income = base_income

    # Exemptions
    exemption_amount = config.personal_exemption * num_exemptions
    result.exemptions = exemption_amount

    # Standard deduction (if state uses it)
    std_ded = config.standard_deduction.get(filing_status, 0.0)
    result.standard_deduction_amount = std_ded

    # Taxable income
    taxable = max(0, base_income - exemption_amount - std_ded)
    result.taxable_income = taxable

    # Compute tax based on model
    if config.tax_type == "flat":
        result.tax = round(taxable * config.rate, 2)
    elif config.tax_type == "graduated":
        brackets = config.brackets.get(filing_status, [])
        if not brackets:
            # Fallback to single brackets if filing status not found
            brackets = config.brackets.get("single", [])
        result.tax = round(compute_bracket_tax(taxable, brackets), 2)
    else:
        result.tax = 0.0

    # Surtax (e.g., CA Mental Health Tax)
    if config.surtax_rate > 0 and taxable > config.surtax_threshold:
        result.surtax = round((taxable - config.surtax_threshold) * config.surtax_rate, 2)

    result.total_tax = result.tax + result.surtax

    # Payments and credits
    result.withholding = state_withholding
    result.estimated_payments = estimated_payments
    result.credit_for_other_states = credit_for_other_states

    total_payments = state_withholding + estimated_payments + credit_for_other_states
    diff = total_payments - result.total_tax
    if diff >= 0:
        result.refund = round(diff, 2)
        result.owed = 0.0
    else:
        result.refund = 0.0
        result.owed = round(abs(diff), 2)

    return result


def compute_all_state_returns(
    residence_state: str,
    work_states: list[str],
    filing_status: str,
    federal_agi: float,
    w2_state_wages: dict[str, float],
    w2_state_withheld: dict[str, float],
    estimated_state_payments: float = 0.0,
    num_exemptions: int = 1,
    days_worked_by_state: dict[str, int] | None = None,
    total_wages: float = 0.0,
) -> list[StateTaxResult]:
    """Compute all state returns for a multi-state worker.

    Order: nonresident returns first, then resident return with credits.

    Args:
        residence_state: State where filer lives
        work_states: Additional states where filer earned income (besides residence)
        filing_status: Federal filing status
        federal_agi: Federal AGI
        w2_state_wages: {state_code: total_wages} from W-2 state boxes
        w2_state_withheld: {state_code: total_withheld} from W-2 state boxes
        estimated_state_payments: Estimated payments (applied to resident state only)
        num_exemptions: Personal exemptions count
        days_worked_by_state: Optional manual allocation {state: days}
        total_wages: Total W-2 wages (for days-worked allocation fallback)
    """
    residence_state = residence_state.upper()
    results = []
    nonresident_taxes_paid = 0.0

    # Get residence state config for reciprocal check
    res_config = get_state_config(residence_state)

    # --- Step 1: Nonresident returns for work states ---
    for work_state in work_states:
        work_state = work_state.upper()

        # Skip if same as residence
        if work_state == residence_state:
            continue

        # Skip no-tax states
        if work_state in NO_TAX_STATES:
            continue

        # Check reciprocal agreement
        if res_config and work_state in res_config.reciprocal_states:
            # Reciprocal: no nonresident return needed
            continue

        # Determine allocated income for this state
        allocated_income = w2_state_wages.get(work_state, 0.0)

        # Days-worked fallback if no W-2 state wages
        if allocated_income == 0.0 and days_worked_by_state and total_wages > 0:
            days_in_state = days_worked_by_state.get(work_state, 0)
            total_days = sum(days_worked_by_state.values())
            if total_days > 0:
                allocation_pct = days_in_state / total_days
                allocated_income = total_wages * allocation_pct

        if allocated_income <= 0:
            continue

        allocation_pct = allocated_income / federal_agi if federal_agi > 0 else 0.0

        nr_result = compute_state_tax(
            state_code=work_state,
            filing_status=filing_status,
            federal_agi=federal_agi,
            state_withholding=w2_state_withheld.get(work_state, 0.0),
            num_exemptions=num_exemptions,
            return_type="nonresident",
            allocated_income=allocated_income,
            allocation_pct=allocation_pct,
        )
        results.append(nr_result)
        nonresident_taxes_paid += nr_result.total_tax

    # --- Step 2: Resident return (with credit for taxes paid elsewhere) ---
    if residence_state not in NO_TAX_STATES:
        # Credit = lesser of (tax paid to other state) or (resident tax * allocation %)
        # We'll compute the resident tax first, then apply credit
        res_result = compute_state_tax(
            state_code=residence_state,
            filing_status=filing_status,
            federal_agi=federal_agi,
            state_withholding=w2_state_withheld.get(residence_state, 0.0),
            estimated_payments=estimated_state_payments,
            num_exemptions=num_exemptions,
            return_type="resident",
        )

        # Apply credit for taxes paid to other states
        if nonresident_taxes_paid > 0 and res_result.total_tax > 0:
            # Credit capped at the lesser of:
            # 1. Actual tax paid to other states
            # 2. Resident state's tax on the same income
            other_state_income = sum(
                r.allocated_income for r in results if r.return_type == "nonresident"
            )
            if federal_agi > 0:
                income_ratio = other_state_income / federal_agi
            else:
                income_ratio = 0.0
            max_credit = res_result.total_tax * income_ratio
            credit = min(nonresident_taxes_paid, max_credit)
            res_result.credit_for_other_states = round(credit, 2)

            # Recalculate refund/owed with credit
            total_payments = (
                res_result.withholding
                + res_result.estimated_payments
                + res_result.credit_for_other_states
            )
            diff = total_payments - res_result.total_tax
            if diff >= 0:
                res_result.refund = round(diff, 2)
                res_result.owed = 0.0
            else:
                res_result.refund = 0.0
                res_result.owed = round(abs(diff), 2)

        results.append(res_result)

    return results
