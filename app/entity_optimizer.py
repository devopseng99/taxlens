"""Entity Type Optimization Engine — Compare sole prop vs S-corp vs C-corp.

Computes total tax burden under each entity structure for a given business
income profile, then recommends the optimal entity type with savings breakdown.
"""

from dataclasses import dataclass, field
from tax_config import (
    get_year_config, SE_TAX_RATE, SE_INCOME_FACTOR, SE_SS_RATE, SE_MEDICARE_RATE,
    SS_RATE, MEDICARE_RATE, ADDITIONAL_MEDICARE_RATE, QBI_DEDUCTION_RATE, TAX_YEAR,
)
from tax_engine import compute_bracket_tax

# C-corp flat rate (IRC §11(b), post-TCJA)
C_CORP_RATE = 0.21

# Qualified dividend rates (same as LTCG)
QUALIFIED_DIV_RATE_0 = 0.00
QUALIFIED_DIV_RATE_15 = 0.15
QUALIFIED_DIV_RATE_20 = 0.20


@dataclass
class EntityScenario:
    """Tax computation result for one entity type."""
    entity_type: str                       # "sole_prop", "s_corp", "c_corp"
    label: str = ""                        # Human-readable label
    # Income splits
    business_income: float = 0.0           # Gross business net profit
    reasonable_compensation: float = 0.0   # W-2 salary (S-corp only)
    distributions: float = 0.0            # Pass-through distributions
    # Tax components
    income_tax: float = 0.0               # Federal income tax on personal return
    se_tax: float = 0.0                   # Self-employment tax (sole prop) or FICA (S-corp)
    fica_employer: float = 0.0            # Employer-side FICA (S-corp — deductible by entity)
    fica_employee: float = 0.0            # Employee-side FICA (S-corp — withheld from W-2)
    corporate_tax: float = 0.0            # C-corp entity-level tax
    dividend_tax: float = 0.0             # Tax on C-corp dividend distributions
    qbi_deduction: float = 0.0           # §199A QBI deduction
    additional_medicare: float = 0.0      # 0.9% additional Medicare tax
    # Totals
    total_tax: float = 0.0               # Combined entity + personal tax
    effective_rate: float = 0.0           # total_tax / business_income


@dataclass
class EntityComparison:
    """Full comparison across entity types."""
    business_income: float
    filing_status: str
    other_income: float
    scenarios: list[EntityScenario] = field(default_factory=list)
    recommended: str = ""                  # Best entity type
    savings_vs_sole_prop: float = 0.0     # How much recommended saves vs sole prop
    reasonable_comp_range: dict = field(default_factory=dict)  # min/max/recommended


def _compute_se_tax(net_profit: float, ss_wage_base: float) -> tuple[float, float]:
    """Compute self-employment tax on Schedule C net profit.

    Returns (se_tax, se_deduction) — the 50% above-the-line deduction.
    """
    se_income = net_profit * SE_INCOME_FACTOR  # 92.35% of net profit
    if se_income <= 0:
        return 0.0, 0.0
    ss_portion = min(se_income, ss_wage_base) * SE_SS_RATE  # 12.4%
    medicare_portion = se_income * SE_MEDICARE_RATE           # 2.9%
    se_tax = ss_portion + medicare_portion
    se_deduction = se_tax * 0.5  # 50% is above-the-line deduction
    return round(se_tax, 2), round(se_deduction, 2)


def _compute_fica(wages: float, ss_wage_base: float) -> tuple[float, float]:
    """Compute employer + employee FICA on W-2 wages.

    Returns (employer_fica, employee_fica).
    """
    ss_wages = min(wages, ss_wage_base)
    employer = ss_wages * SS_RATE + wages * MEDICARE_RATE          # 6.2% + 1.45%
    employee = ss_wages * SS_RATE + wages * MEDICARE_RATE          # 6.2% + 1.45%
    return round(employer, 2), round(employee, 2)


def _reasonable_comp_range(business_income: float) -> dict:
    """Estimate reasonable compensation range for S-corp.

    IRS expects "reasonable" W-2 salary before distributions. Rule of thumb:
    - Minimum: ~40% of net profit (IRS audit floor for most industries)
    - Maximum: 70% (aggressive, but defensible for service businesses)
    - Recommended: 50-60% (safe middle ground)
    """
    if business_income <= 0:
        return {"min": 0, "max": 0, "recommended": 0}
    min_comp = round(business_income * 0.40, 2)
    max_comp = round(business_income * 0.70, 2)
    recommended = round(business_income * 0.50, 2)
    return {"min": min_comp, "max": max_comp, "recommended": recommended}


def compare_entities(
    business_income: float,
    filing_status: str = "single",
    other_income: float = 0.0,
    reasonable_compensation: float | None = None,
    is_sstb: bool = False,
    tax_year: int = TAX_YEAR,
) -> EntityComparison:
    """Compare sole prop, S-corp, and C-corp for a given business income.

    Args:
        business_income: Net business profit (Schedule C equivalent).
        filing_status: "single", "mfj", "hoh", "mfs".
        other_income: Other non-business income (W-2 wages, interest, etc.) for bracket positioning.
        reasonable_compensation: S-corp W-2 salary. If None, uses 50% of business income.
        is_sstb: Specified Service Trade or Business (limits QBI for high earners).
        tax_year: Tax year (2024, 2025, or 2026).

    Returns:
        EntityComparison with scenarios and recommendation.
    """
    c = get_year_config(tax_year)
    brackets = c.FEDERAL_BRACKETS[filing_status]
    ss_wage_base = c.SS_WAGE_BASE
    std_deduction = c.STANDARD_DEDUCTION[filing_status]

    # Reasonable compensation for S-corp
    comp_range = _reasonable_comp_range(business_income)
    if reasonable_compensation is None:
        reasonable_compensation = comp_range["recommended"]
    reasonable_compensation = min(reasonable_compensation, business_income)
    s_corp_distributions = max(0, business_income - reasonable_compensation)

    result = EntityComparison(
        business_income=business_income,
        filing_status=filing_status,
        other_income=other_income,
        reasonable_comp_range=comp_range,
    )

    # ===== SOLE PROPRIETORSHIP =====
    sole = EntityScenario(entity_type="sole_prop", label="Sole Proprietorship",
                          business_income=business_income)
    se_tax, se_deduction = _compute_se_tax(business_income, ss_wage_base)
    sole.se_tax = se_tax

    # AGI = other_income + business_income - SE deduction
    sole_agi = other_income + business_income - se_deduction
    # QBI deduction (simplified — 20% of QBI, not SSTB limited here for comparison)
    qbi_rate = c.QBI_DEDUCTION_RATE if hasattr(c, 'QBI_DEDUCTION_RATE') else QBI_DEDUCTION_RATE
    if qbi_rate > 0:
        qbi_base = business_income  # Simplified: full net profit is QBI
        sole.qbi_deduction = round(qbi_base * qbi_rate, 2)

    sole_taxable = max(0, sole_agi - std_deduction - sole.qbi_deduction)
    sole.income_tax = round(compute_bracket_tax(sole_taxable, brackets), 2)

    # Additional Medicare on SE income above threshold
    amt_threshold = c.ADDITIONAL_MEDICARE_THRESHOLD[filing_status]
    se_medicare_wages = business_income * SE_INCOME_FACTOR
    total_medicare_wages = other_income + se_medicare_wages
    if total_medicare_wages > amt_threshold:
        sole.additional_medicare = round(
            (total_medicare_wages - amt_threshold) * ADDITIONAL_MEDICARE_RATE, 2)

    sole.total_tax = round(sole.income_tax + sole.se_tax + sole.additional_medicare, 2)
    sole.effective_rate = round(sole.total_tax / business_income * 100, 2) if business_income > 0 else 0
    result.scenarios.append(sole)

    # ===== S-CORPORATION =====
    s_corp = EntityScenario(entity_type="s_corp", label="S-Corporation",
                            business_income=business_income,
                            reasonable_compensation=reasonable_compensation,
                            distributions=s_corp_distributions)

    # FICA on reasonable compensation only (not distributions)
    employer_fica, employee_fica = _compute_fica(reasonable_compensation, ss_wage_base)
    s_corp.fica_employer = employer_fica
    s_corp.fica_employee = employee_fica

    # Entity deducts employer FICA from profit (reduces pass-through income)
    entity_profit_after_fica = business_income - reasonable_compensation - employer_fica

    # Personal return: W-2 wages + pass-through distributions
    s_corp_agi = other_income + reasonable_compensation + entity_profit_after_fica
    # QBI on pass-through portion (distributions, not W-2)
    if qbi_rate > 0:
        qbi_base_s = max(0, entity_profit_after_fica)
        s_corp.qbi_deduction = round(qbi_base_s * qbi_rate, 2)

    s_corp_taxable = max(0, s_corp_agi - std_deduction - s_corp.qbi_deduction)
    s_corp.income_tax = round(compute_bracket_tax(s_corp_taxable, brackets), 2)

    # Additional Medicare on W-2 wages only
    total_s_corp_wages = other_income + reasonable_compensation
    if total_s_corp_wages > amt_threshold:
        s_corp.additional_medicare = round(
            (total_s_corp_wages - amt_threshold) * ADDITIONAL_MEDICARE_RATE, 2)

    # Total: income tax + employee FICA + employer FICA + additional Medicare
    s_corp.total_tax = round(
        s_corp.income_tax + s_corp.fica_employer + s_corp.fica_employee
        + s_corp.additional_medicare, 2)
    s_corp.effective_rate = round(s_corp.total_tax / business_income * 100, 2) if business_income > 0 else 0
    result.scenarios.append(s_corp)

    # ===== C-CORPORATION =====
    c_corp = EntityScenario(entity_type="c_corp", label="C-Corporation",
                            business_income=business_income,
                            reasonable_compensation=reasonable_compensation)

    # C-corp pays corporate tax on profit after salary + employer FICA
    c_employer_fica, c_employee_fica = _compute_fica(reasonable_compensation, ss_wage_base)
    c_corp.fica_employer = c_employer_fica
    c_corp.fica_employee = c_employee_fica

    c_corp_profit = max(0, business_income - reasonable_compensation - c_employer_fica)
    c_corp.corporate_tax = round(c_corp_profit * C_CORP_RATE, 2)

    # After-tax profit distributed as qualified dividends
    after_tax_profit = c_corp_profit - c_corp.corporate_tax
    c_corp.distributions = round(after_tax_profit, 2)

    # Personal return: W-2 wages + qualified dividends
    c_corp_agi = other_income + reasonable_compensation + after_tax_profit
    c_corp_taxable = max(0, c_corp_agi - std_deduction)  # No QBI for C-corp
    # Ordinary income tax (excluding dividends taxed preferentially)
    ordinary_taxable = max(0, c_corp_taxable - after_tax_profit)
    c_corp.income_tax = round(compute_bracket_tax(ordinary_taxable, brackets), 2)

    # Qualified dividend tax at preferential rate (simplified: 15% for most)
    if after_tax_profit > 0:
        c_corp.dividend_tax = round(after_tax_profit * QUALIFIED_DIV_RATE_15, 2)

    # Additional Medicare on W-2 only
    total_c_corp_wages = other_income + reasonable_compensation
    if total_c_corp_wages > amt_threshold:
        c_corp.additional_medicare = round(
            (total_c_corp_wages - amt_threshold) * ADDITIONAL_MEDICARE_RATE, 2)

    c_corp.total_tax = round(
        c_corp.income_tax + c_corp.corporate_tax + c_corp.dividend_tax
        + c_corp.fica_employer + c_corp.fica_employee
        + c_corp.additional_medicare, 2)
    c_corp.effective_rate = round(c_corp.total_tax / business_income * 100, 2) if business_income > 0 else 0
    result.scenarios.append(c_corp)

    # ===== RECOMMENDATION =====
    best = min(result.scenarios, key=lambda s: s.total_tax)
    result.recommended = best.entity_type
    result.savings_vs_sole_prop = round(sole.total_tax - best.total_tax, 2)

    return result


def comparison_to_dict(comp: EntityComparison) -> dict:
    """Serialize EntityComparison for API/MCP output."""
    return {
        "business_income": comp.business_income,
        "filing_status": comp.filing_status,
        "other_income": comp.other_income,
        "recommended": comp.recommended,
        "savings_vs_sole_prop": comp.savings_vs_sole_prop,
        "reasonable_comp_range": comp.reasonable_comp_range,
        "scenarios": [
            {
                "entity_type": s.entity_type,
                "label": s.label,
                "business_income": s.business_income,
                "reasonable_compensation": round(s.reasonable_compensation, 2),
                "distributions": round(s.distributions, 2),
                "income_tax": s.income_tax,
                "se_tax": s.se_tax,
                "fica_employer": s.fica_employer,
                "fica_employee": s.fica_employee,
                "corporate_tax": s.corporate_tax,
                "dividend_tax": s.dividend_tax,
                "qbi_deduction": s.qbi_deduction,
                "additional_medicare": s.additional_medicare,
                "total_tax": s.total_tax,
                "effective_rate": s.effective_rate,
            }
            for s in comp.scenarios
        ],
    }
