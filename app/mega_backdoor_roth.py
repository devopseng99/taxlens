"""Mega Backdoor Roth Calculator — After-tax 401(k) → Roth conversion planning.

The mega backdoor Roth strategy uses after-tax 401(k) contributions that are
converted to Roth (either in-plan Roth rollover or distribution to Roth IRA).
The §415(c) annual additions limit caps total contributions (employee pre-tax/Roth
+ employer match + after-tax). The remaining space after deferrals and match is
the "mega backdoor" opportunity.
"""

from dataclasses import dataclass
from tax_config import get_year_config, TAX_YEAR


@dataclass
class MegaBackdoorResult:
    """Result of mega backdoor Roth analysis."""
    tax_year: int
    # Limits
    section_415c_limit: float          # Total annual additions limit (§415(c))
    employee_deferral_limit: float     # Pre-tax/Roth 402(g) limit
    catchup_limit: float               # Age 50+ catch-up
    # Inputs
    employee_deferrals: float          # Pre-tax + Roth 401(k) deferrals
    employer_match: float              # Employer matching contributions
    age_50_plus: bool
    # Calculated
    total_limit: float                 # §415(c) + catch-up if eligible
    used_space: float                  # Deferrals + match
    after_tax_space: float             # Remaining §415(c) space for after-tax
    mega_backdoor_amount: float        # Amount available for Roth conversion
    # Projection (10-year tax-free growth comparison)
    projected_roth_value: float = 0.0  # After-tax converted to Roth (tax-free growth)
    projected_taxable_value: float = 0.0  # Same amount in taxable account (growth taxed)
    projected_tax_savings: float = 0.0    # Difference over projection period
    projection_years: int = 10
    projection_return_rate: float = 0.07
    marginal_rate_at_withdrawal: float = 0.24


def compute_mega_backdoor(
    employee_deferrals: float,
    employer_match: float,
    age_50_plus: bool = False,
    marginal_rate: float = 0.24,
    projection_years: int = 10,
    annual_return: float = 0.07,
    tax_year: int = TAX_YEAR,
) -> MegaBackdoorResult:
    """Compute mega backdoor Roth space and projected savings.

    Args:
        employee_deferrals: Total pre-tax + Roth 401(k) deferrals for the year.
        employer_match: Employer matching contributions (vested).
        age_50_plus: True if age 50+ (adds catch-up to §402(g), not §415(c)).
        marginal_rate: Expected marginal tax rate at withdrawal (for projection).
        projection_years: Number of years to project growth.
        annual_return: Expected annual investment return rate.
        tax_year: Tax year (determines IRS limits).
    """
    c = get_year_config(tax_year)

    section_415c = c.SOLO_401K_TOTAL_LIMIT    # §415(c) annual additions limit
    deferral_limit = c.SOLO_401K_EMPLOYEE_LIMIT  # §402(g) elective deferral limit
    catchup = c.SOLO_401K_CATCHUP if age_50_plus else 0

    # §415(c) limit applies to: employee pre-tax/Roth + employer match + after-tax
    # Catch-up contributions do NOT count toward §415(c)
    total_limit = section_415c  # Catch-up is separate from §415(c)

    # Cap deferrals at the 402(g) limit + catch-up
    max_deferrals = deferral_limit + catchup
    effective_deferrals = min(employee_deferrals, max_deferrals)

    # Space used under §415(c): deferrals (excluding catch-up) + employer match
    deferrals_under_415c = min(effective_deferrals, deferral_limit)
    used_space = deferrals_under_415c + employer_match

    # After-tax space = §415(c) limit - used space
    after_tax_space = max(0, total_limit - used_space)
    mega_backdoor_amount = after_tax_space

    result = MegaBackdoorResult(
        tax_year=tax_year,
        section_415c_limit=section_415c,
        employee_deferral_limit=deferral_limit,
        catchup_limit=c.SOLO_401K_CATCHUP,
        employee_deferrals=effective_deferrals,
        employer_match=employer_match,
        age_50_plus=age_50_plus,
        total_limit=total_limit,
        used_space=round(used_space, 2),
        after_tax_space=round(after_tax_space, 2),
        mega_backdoor_amount=round(mega_backdoor_amount, 2),
        projection_years=projection_years,
        projection_return_rate=annual_return,
        marginal_rate_at_withdrawal=marginal_rate,
    )

    # Projection: Roth vs taxable account over N years
    if mega_backdoor_amount > 0:
        # Roth: grows tax-free, withdrawals tax-free
        roth_value = mega_backdoor_amount * ((1 + annual_return) ** projection_years)

        # Taxable: growth taxed annually at LTCG rate (~15%)
        taxable_return = annual_return * (1 - 0.15)  # After-tax annual return
        taxable_value = mega_backdoor_amount * ((1 + taxable_return) ** projection_years)

        # Net taxable: no additional tax on withdrawal (already taxed annually)
        result.projected_roth_value = round(roth_value, 2)
        result.projected_taxable_value = round(taxable_value, 2)
        result.projected_tax_savings = round(roth_value - taxable_value, 2)

    return result


def result_to_dict(r: MegaBackdoorResult) -> dict:
    """Serialize for API/MCP output."""
    return {
        "tax_year": r.tax_year,
        "limits": {
            "section_415c": r.section_415c_limit,
            "employee_deferral_402g": r.employee_deferral_limit,
            "catchup": r.catchup_limit,
        },
        "inputs": {
            "employee_deferrals": r.employee_deferrals,
            "employer_match": r.employer_match,
            "age_50_plus": r.age_50_plus,
        },
        "analysis": {
            "total_limit": r.total_limit,
            "used_space": r.used_space,
            "after_tax_space": r.after_tax_space,
            "mega_backdoor_amount": r.mega_backdoor_amount,
        },
        "projection": {
            "years": r.projection_years,
            "annual_return": r.projection_return_rate,
            "roth_value": r.projected_roth_value,
            "taxable_value": r.projected_taxable_value,
            "tax_savings": r.projected_tax_savings,
            "marginal_rate_at_withdrawal": r.marginal_rate_at_withdrawal,
        } if r.mega_backdoor_amount > 0 else None,
        "recommendation": _recommendation(r),
    }


def _recommendation(r: MegaBackdoorResult) -> str:
    if r.mega_backdoor_amount <= 0:
        return "No after-tax space available. Your deferrals + employer match already fill the §415(c) limit."
    if r.mega_backdoor_amount >= 20_000:
        return (f"Significant opportunity: ${r.mega_backdoor_amount:,.0f} available for mega backdoor Roth. "
                f"Projected {r.projection_years}-year tax savings: ${r.projected_tax_savings:,.0f}.")
    return (f"${r.mega_backdoor_amount:,.0f} available for mega backdoor Roth conversion. "
            f"Verify your plan allows after-tax contributions and in-service distributions.")
