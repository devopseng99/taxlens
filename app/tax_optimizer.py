"""Intelligent tax optimization engine — 15+ strategy analyzer.

Analyzes a taxpayer's situation and recommends actionable strategies
with estimated savings, difficulty, and IRS audit risk.
"""

from dataclasses import dataclass, field
from typing import Optional

from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    TaxResult, compute_tax,
)
from tax_config import get_year_config


@dataclass
class Recommendation:
    """A single tax optimization recommendation."""
    strategy: str = ""
    category: str = ""  # deduction, credit, timing, structure, retirement
    estimated_savings: float = 0.0
    difficulty: str = "easy"  # easy, moderate, complex
    irs_risk: str = "low"  # low, medium, high
    description: str = ""
    action_items: list[str] = field(default_factory=list)
    applicable: bool = True


@dataclass
class OptimizationPlan:
    """Full optimization plan with ranked recommendations."""
    total_potential_savings: float = 0.0
    recommendations: list[Recommendation] = field(default_factory=list)
    current_tax: float = 0.0
    optimized_tax: float = 0.0
    filing_status: str = "single"


def get_optimization_plan(
    wages: float,
    federal_withheld: float = 0.0,
    filing_status: str = "single",
    mortgage_interest: float = 0.0,
    property_tax: float = 0.0,
    state_income_tax: float = 0.0,
    charitable_cash: float = 0.0,
    charitable_noncash: float = 0.0,
    interest_income: float = 0.0,
    dividend_income: float = 0.0,
    business_income: float = 0.0,
    has_hsa: bool = False,
    hsa_contribution: float = 0.0,
    age: int = 35,
    num_dependents: int = 0,
    student_loan_interest: float = 0.0,
    ira_contribution: float = 0.0,
    has_401k: bool = False,
    contribution_401k: float = 0.0,
    rental_income: float = 0.0,
    capital_gains_short: float = 0.0,
    capital_gains_long: float = 0.0,
    capital_losses: float = 0.0,
) -> OptimizationPlan:
    """Analyze taxpayer situation and return optimization recommendations."""

    c = get_year_config(2025)
    filer = PersonInfo(first_name="Optimizer", last_name="Analysis")

    # Compute current tax
    current_result = compute_tax(
        filing_status=filing_status, filer=filer,
        w2s=[W2Income(wages=wages, federal_withheld=federal_withheld)],
        deductions=Deductions(
            mortgage_interest=mortgage_interest,
            property_tax=property_tax,
            state_income_tax_paid=state_income_tax,
            charitable_cash=charitable_cash,
            charitable_noncash=charitable_noncash,
            student_loan_interest=student_loan_interest,
        ),
        additional=AdditionalIncome(
            other_interest=interest_income,
            ordinary_dividends=dividend_income,
        ),
        payments=Payments(),
        num_dependents=num_dependents,
    )

    recommendations = []
    agi = current_result.line_11_agi

    # -----------------------------------------------------------------------
    # 1. Standard vs Itemized Optimization
    # -----------------------------------------------------------------------
    total_itemized = mortgage_interest + min(property_tax + state_income_tax, c.SALT_CAP) + charitable_cash + charitable_noncash
    std_ded = c.STANDARD_DEDUCTION.get(filing_status, c.STANDARD_DEDUCTION["single"])
    if total_itemized < std_ded and total_itemized > 0:
        savings = (std_ded - total_itemized) * 0.22  # Approximate
        recommendations.append(Recommendation(
            strategy="Take Standard Deduction",
            category="deduction",
            estimated_savings=round(savings, 2),
            difficulty="easy",
            irs_risk="low",
            description=f"Standard deduction (${std_ded:,.0f}) exceeds your itemized deductions (${total_itemized:,.0f}).",
            action_items=["Use standard deduction on Form 1040"],
        ))

    # -----------------------------------------------------------------------
    # 2. Charitable Bunching
    # -----------------------------------------------------------------------
    if charitable_cash > 0 and total_itemized < std_ded * 1.2:
        two_year_charitable = charitable_cash * 2
        bunched_itemized = total_itemized - charitable_cash + two_year_charitable
        if bunched_itemized > std_ded:
            savings = (bunched_itemized - std_ded) * 0.22
            recommendations.append(Recommendation(
                strategy="Charitable Bunching",
                category="timing",
                estimated_savings=round(savings, 2),
                difficulty="easy",
                irs_risk="low",
                description="Bundle 2 years of charitable giving into one year to exceed standard deduction.",
                action_items=[
                    "Donate 2 years' worth this year",
                    "Use Donor Advised Fund (DAF) for flexibility",
                    "Take standard deduction in alternate years",
                ],
            ))

    # -----------------------------------------------------------------------
    # 3. HSA Maximization
    # -----------------------------------------------------------------------
    if not has_hsa or hsa_contribution < 4300:  # 2025 self-only limit
        max_hsa = 4300 if filing_status == "single" else 8550
        if age >= 55:
            max_hsa += 1000
        gap = max_hsa - hsa_contribution
        if gap > 0:
            savings = gap * 0.22 + gap * 0.0765  # Income tax + FICA
            recommendations.append(Recommendation(
                strategy="Maximize HSA Contributions",
                category="retirement",
                estimated_savings=round(savings, 2),
                difficulty="easy",
                irs_risk="low",
                description=f"Contribute ${gap:,.0f} more to HSA. Triple tax benefit: deductible, tax-free growth, tax-free withdrawals.",
                action_items=[
                    f"Increase HSA contribution by ${gap:,.0f}",
                    "Invest HSA funds above $1,000 threshold",
                    "Keep receipts for future tax-free reimbursement",
                ],
            ))

    # -----------------------------------------------------------------------
    # 4. IRA Contribution
    # -----------------------------------------------------------------------
    ira_limit = c.IRA_CONTRIBUTION_LIMIT
    if age >= 50:
        ira_limit += 1000
    if ira_contribution < ira_limit:
        gap = ira_limit - ira_contribution
        savings = gap * 0.22
        recommendations.append(Recommendation(
            strategy="Maximize IRA Contribution",
            category="retirement",
            estimated_savings=round(savings, 2),
            difficulty="easy",
            irs_risk="low",
            description=f"Contribute ${gap:,.0f} more to Traditional IRA for above-the-line deduction.",
            action_items=[
                f"Contribute ${gap:,.0f} to Traditional IRA before April 15",
                "Consider Roth IRA if income allows (no deduction but tax-free growth)",
            ],
        ))

    # -----------------------------------------------------------------------
    # 5. 401(k) Optimization
    # -----------------------------------------------------------------------
    limit_401k = 23500  # 2025 limit
    if age >= 50:
        limit_401k += 7500
    if has_401k and contribution_401k < limit_401k:
        gap = limit_401k - contribution_401k
        savings = gap * 0.22
        recommendations.append(Recommendation(
            strategy="Maximize 401(k) Contributions",
            category="retirement",
            estimated_savings=round(savings, 2),
            difficulty="easy",
            irs_risk="low",
            description=f"Increase 401(k) by ${gap:,.0f} to reduce taxable income.",
            action_items=[
                "Increase payroll deferral percentage",
                "Check if employer matches additional contributions",
            ],
        ))

    # -----------------------------------------------------------------------
    # 6. Capital Loss Harvesting
    # -----------------------------------------------------------------------
    net_gains = capital_gains_short + capital_gains_long - capital_losses
    if net_gains > 0 and capital_losses < 3000:
        potential_harvest = min(net_gains + 3000 - capital_losses, net_gains)
        rate = 0.37 if capital_gains_short > 0 else 0.15
        savings = potential_harvest * rate
        recommendations.append(Recommendation(
            strategy="Tax-Loss Harvesting",
            category="timing",
            estimated_savings=round(savings, 2),
            difficulty="moderate",
            irs_risk="low",
            description="Sell losing investments to offset gains. Up to $3,000 excess losses deductible against ordinary income.",
            action_items=[
                "Review portfolio for unrealized losses",
                "Sell positions at a loss before year-end",
                "Avoid wash sale rule (30-day wait)",
                "Reinvest in similar (not identical) securities",
            ],
        ))

    # -----------------------------------------------------------------------
    # 7. Estimated Tax Payment Timing
    # -----------------------------------------------------------------------
    if current_result.quarterly_estimated_tax > 0:
        recommendations.append(Recommendation(
            strategy="Optimize Estimated Tax Timing",
            category="timing",
            estimated_savings=0,
            difficulty="moderate",
            irs_risk="low",
            description="Ensure quarterly payments meet safe harbor (110% of prior year or 90% of current). Avoid underpayment penalties.",
            action_items=[
                "Pay Q1 by April 15, Q2 by June 15, Q3 by Sep 15, Q4 by Jan 15",
                "Use annualized income installment method if income varies",
            ],
        ))

    # -----------------------------------------------------------------------
    # 8. Filing Status Optimization (MFJ vs MFS)
    # -----------------------------------------------------------------------
    if filing_status in ("mfj", "mfs"):
        alt_status = "mfs" if filing_status == "mfj" else "mfj"
        alt_result = compute_tax(
            filing_status=alt_status, filer=filer,
            w2s=[W2Income(wages=wages, federal_withheld=federal_withheld)],
            deductions=Deductions(
                mortgage_interest=mortgage_interest,
                property_tax=property_tax,
                state_income_tax_paid=state_income_tax,
                charitable_cash=charitable_cash,
            ),
            additional=AdditionalIncome(other_interest=interest_income),
            payments=Payments(),
        )
        diff = current_result.line_24_total_tax - alt_result.line_24_total_tax
        if diff > 100:
            recommendations.append(Recommendation(
                strategy=f"Switch to {alt_status.upper()} Filing",
                category="structure",
                estimated_savings=round(diff, 2),
                difficulty="easy",
                irs_risk="low",
                description=f"Filing as {alt_status.upper()} saves ${diff:,.0f} for your situation.",
                action_items=[f"File as {alt_status.upper()} instead of {filing_status.upper()}"],
            ))

    # -----------------------------------------------------------------------
    # 9. QBI Deduction Awareness
    # -----------------------------------------------------------------------
    if business_income > 0:
        qbi_deduction = business_income * 0.20
        recommendations.append(Recommendation(
            strategy="Claim QBI Deduction (Section 199A)",
            category="deduction",
            estimated_savings=round(qbi_deduction * 0.22, 2),
            difficulty="moderate",
            irs_risk="medium",
            description=f"Qualified Business Income deduction: ${qbi_deduction:,.0f} (20% of ${business_income:,.0f}).",
            action_items=[
                "Ensure business qualifies (not specified service if above threshold)",
                "Keep records of business income and expenses",
                "Consider entity structure for W-2 wage optimization",
            ],
        ))

    # -----------------------------------------------------------------------
    # 10. Student Loan Interest
    # -----------------------------------------------------------------------
    if student_loan_interest == 0 and wages < 90000:
        recommendations.append(Recommendation(
            strategy="Claim Student Loan Interest Deduction",
            category="deduction",
            estimated_savings=round(2500 * 0.22, 2),
            difficulty="easy",
            irs_risk="low",
            description="Up to $2,500 above-the-line deduction for student loan interest paid.",
            action_items=["Check Form 1098-E from loan servicer", "Claim on Schedule 1"],
            applicable=False,
        ))

    # -----------------------------------------------------------------------
    # 11. Energy Credits
    # -----------------------------------------------------------------------
    recommendations.append(Recommendation(
        strategy="Residential Energy Credits (Form 5695)",
        category="credit",
        estimated_savings=0,
        difficulty="moderate",
        irs_risk="low",
        description="30% credit on solar, heat pumps, insulation. Up to $3,200/year for efficiency + uncapped for solar.",
        action_items=[
            "Evaluate solar panel installation",
            "Check for eligible heat pump, insulation upgrades",
            "Keep manufacturer certification statements",
        ],
        applicable=False,
    ))

    # -----------------------------------------------------------------------
    # 12. Dependent Care FSA
    # -----------------------------------------------------------------------
    if num_dependents > 0:
        recommendations.append(Recommendation(
            strategy="Dependent Care FSA",
            category="deduction",
            estimated_savings=round(5000 * 0.30, 2),
            difficulty="easy",
            irs_risk="low",
            description="$5,000 pre-tax dependent care FSA saves on income + FICA taxes.",
            action_items=["Enroll during open enrollment", "Track childcare expenses"],
        ))

    # -----------------------------------------------------------------------
    # 13. Roth Conversion Ladder
    # -----------------------------------------------------------------------
    from tax_projector import _marginal_rate
    marg = _marginal_rate(current_result.line_15_taxable_income, filing_status)
    if marg <= 0.22:
        recommendations.append(Recommendation(
            strategy="Roth Conversion Opportunity",
            category="retirement",
            estimated_savings=0,
            difficulty="moderate",
            irs_risk="low",
            description=f"Current marginal rate ({marg*100:.0f}%) is low. Convert Traditional IRA to Roth to lock in this rate.",
            action_items=[
                "Calculate conversion amount to stay in current bracket",
                "Use /roth-optimizer endpoint for optimal amount",
                "Consider multi-year conversion ladder",
            ],
        ))

    # -----------------------------------------------------------------------
    # 14. SALT Workaround (Pass-Through Entity Tax)
    # -----------------------------------------------------------------------
    if state_income_tax + property_tax > c.SALT_CAP and business_income > 0:
        excess_salt = state_income_tax + property_tax - c.SALT_CAP
        savings = excess_salt * marg
        recommendations.append(Recommendation(
            strategy="SALT Cap Workaround (PTE Tax)",
            category="structure",
            estimated_savings=round(savings, 2),
            difficulty="complex",
            irs_risk="medium",
            description="Many states allow pass-through entity (PTE) tax elections that bypass the $10K SALT cap.",
            action_items=[
                "Check if your state offers PTE tax election",
                "Evaluate with a CPA — entity restructuring may be needed",
                "Must make election before tax year begins in some states",
            ],
        ))

    # -----------------------------------------------------------------------
    # 15. Mega Backdoor Roth
    # -----------------------------------------------------------------------
    if has_401k and wages > 150000:
        recommendations.append(Recommendation(
            strategy="Mega Backdoor Roth",
            category="retirement",
            estimated_savings=0,
            difficulty="complex",
            irs_risk="low",
            description="After-tax 401(k) contributions up to $70,000 total limit, immediately converted to Roth.",
            action_items=[
                "Check if employer plan allows after-tax contributions",
                "Verify plan allows in-service Roth conversions",
                "Consult plan administrator for mechanics",
            ],
        ))

    # Filter and sort by savings
    applicable_recs = [r for r in recommendations if r.applicable]
    applicable_recs.sort(key=lambda r: r.estimated_savings, reverse=True)

    total_savings = sum(r.estimated_savings for r in applicable_recs)

    return OptimizationPlan(
        total_potential_savings=round(total_savings, 2),
        recommendations=applicable_recs,
        current_tax=round(current_result.line_24_total_tax, 2),
        optimized_tax=round(current_result.line_24_total_tax - total_savings, 2),
        filing_status=filing_status,
    )
