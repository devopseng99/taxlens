"""Tax projection engine — multi-year tax planning + Roth conversion optimizer.

Projects tax liability across 3 years (2024-2026) using inflation-adjusted
constants. Includes Roth conversion optimizer to find optimal conversion
amount within a target tax bracket.
"""

from dataclasses import dataclass, field
from typing import Optional

from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    TaxResult, compute_tax,
)
from tax_config import get_year_config, FILING_STATUSES


# ---------------------------------------------------------------------------
# CPI-U Inflation Adjustment
# ---------------------------------------------------------------------------
CPI_U_2026_FACTOR = 1.028  # ~2.8% projected inflation


def inflate(value: float, factor: float = CPI_U_2026_FACTOR) -> float:
    """Apply inflation adjustment, rounded to nearest $50 (IRS convention)."""
    inflated = value * factor
    return round(inflated / 50) * 50


# ---------------------------------------------------------------------------
# Rate Helpers
# ---------------------------------------------------------------------------
def _effective_rate(total_tax: float, total_income: float) -> float:
    """Compute effective tax rate."""
    if total_income <= 0:
        return 0.0
    return total_tax / total_income


def _marginal_rate(taxable_income: float, filing_status: str, tax_year: int = 2025) -> float:
    """Compute marginal tax rate from brackets."""
    c = get_year_config(min(tax_year, 2025))
    brackets = c.FEDERAL_BRACKETS.get(filing_status, c.FEDERAL_BRACKETS["single"])
    rate = 0.10
    for threshold, bracket_rate in brackets:
        if taxable_income <= threshold:
            rate = bracket_rate
            break
        rate = bracket_rate
    return rate


# ---------------------------------------------------------------------------
# 2026 Projected Constants
# ---------------------------------------------------------------------------
def get_2026_projected_constants() -> dict:
    """Return projected 2026 tax constants based on CPI-U inflation."""
    c2025 = get_year_config(2025)
    return {
        "tax_year": 2026,
        "standard_deduction_single": inflate(c2025.STANDARD_DEDUCTION["single"]),
        "standard_deduction_mfj": inflate(c2025.STANDARD_DEDUCTION["mfj"]),
        "standard_deduction_hoh": inflate(c2025.STANDARD_DEDUCTION["hoh"]),
        "ss_wage_base": inflate(c2025.SS_WAGE_BASE, 1.035),
        "eitc_max_0_children": inflate(c2025.EITC_MAX_CREDIT[0]),
        "ctc_per_child": c2025.CTC_PER_CHILD,
        "ira_contribution_limit": inflate(c2025.IRA_CONTRIBUTION_LIMIT),
        "salt_cap": c2025.SALT_CAP,
        "amt_exemption_single": inflate(c2025.AMT_EXEMPTION["single"]),
        "cpi_u_factor": CPI_U_2026_FACTOR,
        "note": "Projected using CPI-U chained methodology. Subject to IRS Rev. Proc. updates.",
    }


# ---------------------------------------------------------------------------
# Multi-Year Projection
# ---------------------------------------------------------------------------
@dataclass
class ProjectionScenario:
    wages: float = 0.0
    federal_withheld: float = 0.0
    interest_income: float = 0.0
    dividend_income: float = 0.0
    mortgage_interest: float = 0.0
    property_tax: float = 0.0
    charitable: float = 0.0
    num_dependents: int = 0
    filing_status: str = "single"
    income_growth_rate: float = 0.03


@dataclass
class YearProjection:
    tax_year: int = 0
    total_income: float = 0.0
    agi: float = 0.0
    taxable_income: float = 0.0
    total_tax: float = 0.0
    effective_rate: float = 0.0
    marginal_rate: float = 0.0
    refund_or_owed: float = 0.0
    is_projected: bool = False


def project_tax_liability(
    base: ProjectionScenario,
    years: int = 3,
    start_year: int = 2024,
) -> list[YearProjection]:
    """Project tax liability across multiple years."""
    results = []
    growth = base.income_growth_rate

    for i in range(years):
        year = start_year + i
        growth_factor = (1 + growth) ** i

        wages = base.wages * growth_factor
        withheld = base.federal_withheld * growth_factor
        interest = base.interest_income * growth_factor
        dividends = base.dividend_income * growth_factor

        compute_year = min(year, 2025)

        filer = PersonInfo(first_name="Projection", last_name=str(year))
        result = compute_tax(
            filing_status=base.filing_status,
            filer=filer,
            w2s=[W2Income(wages=wages, federal_withheld=withheld)],
            deductions=Deductions(
                mortgage_interest=base.mortgage_interest,
                property_tax=base.property_tax,
                charitable_cash=base.charitable,
            ),
            additional=AdditionalIncome(
                other_interest=interest,
                ordinary_dividends=dividends,
            ),
            payments=Payments(),
            num_dependents=base.num_dependents,
            tax_year=compute_year,
        )

        eff = _effective_rate(result.line_24_total_tax, result.line_9_total_income)
        marg = _marginal_rate(result.line_15_taxable_income, base.filing_status, compute_year)

        proj = YearProjection(
            tax_year=year,
            total_income=round(result.line_9_total_income, 2),
            agi=round(result.line_11_agi, 2),
            taxable_income=round(result.line_15_taxable_income, 2),
            total_tax=round(result.line_24_total_tax, 2),
            effective_rate=round(eff * 100, 2),
            marginal_rate=round(marg * 100, 2),
            refund_or_owed=round(result.line_34_overpaid - result.line_37_owed, 2),
            is_projected=(year > 2025),
        )
        results.append(proj)

    return results


# ---------------------------------------------------------------------------
# Roth Conversion Optimizer
# ---------------------------------------------------------------------------
@dataclass
class RothConversionResult:
    optimal_conversion: float = 0.0
    tax_on_conversion: float = 0.0
    marginal_rate_at_conversion: float = 0.0
    stays_in_bracket: bool = True
    target_bracket_top: float = 0.0
    total_tax_without_conversion: float = 0.0
    total_tax_with_conversion: float = 0.0


def optimize_roth_conversion(
    wages: float,
    federal_withheld: float = 0.0,
    other_income: float = 0.0,
    filing_status: str = "single",
    target_bracket_rate: float = 0.22,
    max_conversion: float = 500000.0,
) -> RothConversionResult:
    """Find optimal Roth conversion amount to stay within a target bracket."""
    filer = PersonInfo(first_name="Roth", last_name="Optimizer")

    # Compute base tax (no conversion)
    base_result = compute_tax(
        filing_status=filing_status, filer=filer,
        w2s=[W2Income(wages=wages, federal_withheld=federal_withheld)],
        deductions=Deductions(),
        additional=AdditionalIncome(other_interest=other_income),
        payments=Payments(),
    )

    # Check if already above target bracket
    base_marginal = _marginal_rate(base_result.line_15_taxable_income, filing_status)
    if base_marginal > target_bracket_rate:
        # Already above target, no conversion possible
        c = get_year_config(2025)
        brackets = c.FEDERAL_BRACKETS.get(filing_status, c.FEDERAL_BRACKETS["single"])
        target_top = 0.0
        for threshold, rate in brackets:
            if abs(rate - target_bracket_rate) < 0.001:
                target_top = threshold
                break

        return RothConversionResult(
            optimal_conversion=0,
            tax_on_conversion=0,
            marginal_rate_at_conversion=round(base_marginal * 100, 2),
            stays_in_bracket=False,
            target_bracket_top=target_top,
            total_tax_without_conversion=round(base_result.line_24_total_tax, 2),
            total_tax_with_conversion=round(base_result.line_24_total_tax, 2),
        )

    # Binary search for optimal conversion
    lo, hi = 0.0, max_conversion
    best_conversion = 0.0

    for _ in range(50):
        mid = (lo + hi) / 2
        if mid < 1:
            break

        result = compute_tax(
            filing_status=filing_status, filer=filer,
            w2s=[W2Income(wages=wages, federal_withheld=federal_withheld)],
            deductions=Deductions(),
            additional=AdditionalIncome(other_interest=other_income + mid),
            payments=Payments(),
        )

        marg = _marginal_rate(result.line_15_taxable_income, filing_status)
        if marg <= target_bracket_rate:
            best_conversion = mid
            lo = mid
        else:
            hi = mid

    # Compute final result
    if best_conversion > 0:
        final_result = compute_tax(
            filing_status=filing_status, filer=filer,
            w2s=[W2Income(wages=wages, federal_withheld=federal_withheld)],
            deductions=Deductions(),
            additional=AdditionalIncome(other_interest=other_income + best_conversion),
            payments=Payments(),
        )
        final_marginal = _marginal_rate(final_result.line_15_taxable_income, filing_status)
    else:
        final_result = base_result
        final_marginal = base_marginal

    # Get bracket top
    c = get_year_config(2025)
    brackets = c.FEDERAL_BRACKETS.get(filing_status, c.FEDERAL_BRACKETS["single"])
    target_top = 0.0
    for threshold, rate in brackets:
        if abs(rate - target_bracket_rate) < 0.001:
            target_top = threshold
            break

    return RothConversionResult(
        optimal_conversion=round(best_conversion, 2),
        tax_on_conversion=round(final_result.line_24_total_tax - base_result.line_24_total_tax, 2),
        marginal_rate_at_conversion=round(final_marginal * 100, 2),
        stays_in_bracket=(final_marginal <= target_bracket_rate),
        target_bracket_top=target_top,
        total_tax_without_conversion=round(base_result.line_24_total_tax, 2),
        total_tax_with_conversion=round(final_result.line_24_total_tax, 2),
    )
