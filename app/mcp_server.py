"""TaxLens MCP Server — expose tax computation engine as MCP tools.

Mounted on the FastAPI app at /mcp via StreamableHTTP.
Any MCP-capable client (Claude Desktop, Claude Code, custom agents)
can call these tools natively.
"""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from tax_engine import (
    PersonInfo, W2Income, CapitalTransaction, BusinessIncome, Deductions,
    AdditionalIncome, DividendIncome, Payments, TaxResult, Dependent,
    EducationExpense, DependentCareExpense, RetirementContribution,
    RentalProperty, HSAContribution, EnergyImprovement, K1Income, CryptoTransaction,
    DepreciableAsset, RetirementDistribution, IRAContribution, SocialSecurityBenefit,
    UnemploymentCompensation, GamblingIncome, ForeignTaxCredit,
    compute_tax,
)
from tax_config import get_year_config, SUPPORTED_TAX_YEARS
from state_configs import get_state_config, NO_TAX_STATES

STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))

# Initialize MCP server
mcp = FastMCP(
    name="TaxLens",
    instructions=(
        "TaxLens is a tax computation engine for US federal + state taxes (tax years 2024 and 2025). "
        "Use compute_tax_scenario to calculate taxes for any scenario — supports structured dependents "
        "(with DOB for age-based credit eligibility), education expenses (AOTC/LLC), dependent care "
        "expenses (CDCC), retirement contributions (Saver's Credit), multi-state filing, and penalty "
        "estimation via prior_year_tax/prior_year_agi. Use compare_scenarios to compare filing "
        "strategies side-by-side. Use get_tax_config to look up brackets, deductions, and credit "
        "limits for a specific tax year and filing status. Use list_states to see supported states. "
        "Set tax_year=2024 for prior year returns."
    ),
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api").split("//")[1].split("/")[0],
            "localhost", "127.0.0.1",
        ],
        allowed_origins=[
            os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api").rsplit("/api", 1)[0],
            os.getenv("TAXLENS_LANDING_URL", "https://taxlens.istayintek.com"),
        ],
    ),
)


# ---------------------------------------------------------------------------
# Helper: build engine inputs from simplified MCP tool params
# ---------------------------------------------------------------------------
def _build_inputs(
    filing_status: str,
    wages: float = 0,
    federal_withheld: float = 0,
    interest: float = 0,
    ordinary_dividends: float = 0,
    qualified_dividends: float = 0,
    short_term_gains: float = 0,
    long_term_gains: float = 0,
    business_income: float = 0,
    business_expenses: float = 0,
    mortgage_interest: float = 0,
    property_tax: float = 0,
    state_tax_paid: float = 0,
    charitable: float = 0,
    charitable_noncash: float = 0,
    medical_expenses: float = 0,
    student_loan_interest: float = 0,
    other_income: float = 0,
    num_dependents: int = 0,
    dependents: list[dict] | None = None,
    residence_state: str = "IL",
    work_states: list[str] | None = None,
    days_worked_by_state: dict[str, int] | None = None,
    estimated_federal: float = 0,
    estimated_state: float = 0,
    additional_withholding: float = 0,
    education_expenses: list[dict] | None = None,
    dependent_care_expenses: list[dict] | None = None,
    retirement_contributions: list[dict] | None = None,
    rental_properties: list[dict] | None = None,
    hsa_contributions: list[dict] | None = None,
    energy_improvements: list[dict] | None = None,
    k1_incomes: list[dict] | None = None,
    crypto_transactions: list[dict] | None = None,
    depreciable_assets: list[dict] | None = None,
    retirement_distributions: list[dict] | None = None,
    ira_contributions: list[dict] | None = None,
    social_security_benefits: list[dict] | None = None,
    unemployment_benefits: list[dict] | None = None,
    gambling_income: list[dict] | None = None,
    gambling_losses: float = 0,
    foreign_tax_credits: list[dict] | None = None,
    educator_expenses: float = 0,
    alimony_paid: float = 0,
    alimony_received: float = 0,
    capital_loss_carryover: float = 0,
    filer_age_65_plus: bool = False,
    filer_is_blind: bool = False,
    spouse_age_65_plus: bool = False,
    spouse_is_blind: bool = False,
    filer_active_plan_participant: bool = False,
    spouse_active_plan_participant: bool = False,
    prior_year_tax: float = 0,
    prior_year_agi: float = 0,
    tax_year: int = 2025,
) -> dict:
    """Convert simplified params to engine-ready inputs."""
    filer = PersonInfo(first_name="MCP", last_name="User")
    w2s = []
    if wages > 0:
        w2s.append(W2Income(wages=wages, federal_withheld=federal_withheld,
                            ss_wages=wages, medicare_wages=wages))

    cap_txns = []
    if short_term_gains != 0:
        cap_txns.append(CapitalTransaction(
            description="Short-term gains/losses",
            proceeds=max(short_term_gains, 0),
            cost_basis=max(-short_term_gains, 0),
            is_long_term=False,
        ))
    if long_term_gains != 0:
        cap_txns.append(CapitalTransaction(
            description="Long-term gains/losses",
            proceeds=max(long_term_gains, 0),
            cost_basis=max(-long_term_gains, 0),
            is_long_term=True,
        ))

    additional = AdditionalIncome(
        other_interest=interest,
        ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends,
        capital_transactions=cap_txns,
        other_income=other_income,
    )

    businesses = []
    if business_income > 0:
        businesses.append(BusinessIncome(
            business_name="Self-Employment",
            gross_receipts=business_income,
            other_expenses=business_expenses,
        ))

    deductions = Deductions(
        mortgage_interest=mortgage_interest,
        property_tax=property_tax,
        state_income_tax_paid=state_tax_paid,
        charitable_cash=charitable,
        charitable_noncash=charitable_noncash,
        medical_expenses=medical_expenses,
        student_loan_interest=student_loan_interest,
    )

    payments = Payments(
        estimated_federal=estimated_federal,
        estimated_state=estimated_state,
    )

    # Build structured dependents from dicts
    dep_list = None
    if dependents:
        dep_list = [
            Dependent(
                first_name=d.get("first_name", ""),
                last_name=d.get("last_name", ""),
                date_of_birth=d.get("date_of_birth", ""),
                relationship=d.get("relationship", ""),
                months_lived_with=d.get("months_lived_with", 12),
                is_disabled=d.get("is_disabled", False),
                is_student=d.get("is_student", False),
            )
            for d in dependents
        ]

    # Build education expenses
    edu_list = None
    if education_expenses:
        edu_list = [
            EducationExpense(
                student_name=e.get("student_name", ""),
                qualified_expenses=e.get("qualified_expenses", 0),
                credit_type=e.get("credit_type", "aotc"),
            )
            for e in education_expenses
        ]

    # Build dependent care expenses
    care_list = None
    if dependent_care_expenses:
        care_list = [
            DependentCareExpense(
                dependent_name=d.get("dependent_name", ""),
                care_expenses=d.get("care_expenses", 0),
            )
            for d in dependent_care_expenses
        ]

    # Build retirement contributions
    ret_list = None
    if retirement_contributions:
        ret_list = [
            RetirementContribution(
                contributor=r.get("contributor", "filer"),
                contribution_amount=r.get("contribution_amount", 0),
            )
            for r in retirement_contributions
        ]

    # Build rental properties
    rental_list = None
    if rental_properties:
        rental_list = [
            RentalProperty(
                property_address=r.get("property_address", ""),
                rental_days=r.get("rental_days", 365),
                personal_use_days=r.get("personal_use_days", 0),
                gross_rents=r.get("gross_rents", 0),
                advertising=r.get("advertising", 0),
                auto_travel=r.get("auto_travel", 0),
                cleaning_maintenance=r.get("cleaning_maintenance", 0),
                commissions=r.get("commissions", 0),
                insurance=r.get("insurance", 0),
                legal_professional=r.get("legal_professional", 0),
                management_fees=r.get("management_fees", 0),
                mortgage_interest=r.get("mortgage_interest", 0),
                repairs=r.get("repairs", 0),
                supplies=r.get("supplies", 0),
                taxes=r.get("taxes", 0),
                utilities=r.get("utilities", 0),
                depreciation=r.get("depreciation", 0),
                other_expenses=r.get("other_expenses", 0),
            )
            for r in rental_properties
        ]

    # Build HSA contributions
    hsa_list = None
    if hsa_contributions:
        hsa_list = [
            HSAContribution(
                contributor=h.get("contributor", "filer"),
                contribution_amount=h.get("contribution_amount", 0),
                employer_contributions=h.get("employer_contributions", 0),
                coverage_type=h.get("coverage_type", "self"),
                age_55_plus=h.get("age_55_plus", False),
            )
            for h in hsa_contributions
        ]

    # Build energy improvements
    energy_list = None
    if energy_improvements:
        energy_list = [
            EnergyImprovement(**{k: e.get(k, 0) for k in [
                "solar_electric", "solar_water_heating", "small_wind",
                "geothermal_heat_pump", "battery_storage", "fuel_cell",
                "insulation", "windows_skylights", "exterior_doors",
                "heat_pump", "biomass_stove", "energy_audit",
            ]})
            for e in energy_improvements
        ]

    # Build crypto transactions
    crypto_list = None
    if crypto_transactions:
        crypto_list = [
            CryptoTransaction(
                asset_name=ct.get("asset_name", ""),
                date_acquired=ct.get("date_acquired", ""),
                date_sold=ct.get("date_sold", ""),
                proceeds=ct.get("proceeds", 0),
                cost_basis=ct.get("cost_basis", 0),
                is_long_term=ct.get("is_long_term", False),
                exchange=ct.get("exchange", ""),
                basis_method=ct.get("basis_method", "fifo"),
                wash_sale_loss_disallowed=ct.get("wash_sale_loss_disallowed", 0),
            )
            for ct in crypto_transactions
        ]

    # Build depreciable assets
    asset_list = None
    if depreciable_assets:
        asset_list = [
            DepreciableAsset(
                description=a.get("description", ""),
                cost=a.get("cost", 0),
                date_placed_in_service=a.get("date_placed_in_service", ""),
                macrs_class=a.get("macrs_class", 5),
                asset_use=a.get("asset_use", "business"),
                business_use_pct=a.get("business_use_pct", 100.0),
                section_179_elected=a.get("section_179_elected", 0),
                bonus_depreciation=a.get("bonus_depreciation", True),
                recovery_year=a.get("recovery_year", 1),
            )
            for a in depreciable_assets
        ]

    # Build K-1 incomes
    k1_list = None
    if k1_incomes:
        k1_list = [
            K1Income(
                entity_name=k.get("entity_name", ""),
                entity_ein=k.get("entity_ein", ""),
                entity_type=k.get("entity_type", "partnership"),
                ordinary_income=k.get("ordinary_income", 0),
                rental_income=k.get("rental_income", 0),
                interest_income=k.get("interest_income", 0),
                dividend_income=k.get("dividend_income", 0),
                qualified_dividends=k.get("qualified_dividends", 0),
                short_term_gain=k.get("short_term_gain", 0),
                long_term_gain=k.get("long_term_gain", 0),
                section_1231_gain=k.get("section_1231_gain", 0),
                guaranteed_payments=k.get("guaranteed_payments", 0),
                section_199a_income=k.get("section_199a_income", 0),
                distributions=k.get("distributions", 0),
                tax_exempt_income=k.get("tax_exempt_income", 0),
            )
            for k in k1_incomes
        ]

    # Build retirement distributions
    ret_dist_list = None
    if retirement_distributions:
        ret_dist_list = [
            RetirementDistribution(
                payer_name=r.get("payer_name", ""),
                gross_distribution=r.get("gross_distribution", 0),
                taxable_amount=r.get("taxable_amount", 0),
                taxable_amount_not_determined=r.get("taxable_amount_not_determined", False),
                federal_withheld=r.get("federal_withheld", 0),
                distribution_code=r.get("distribution_code", "7"),
                is_ira=r.get("is_ira", False),
                is_roth=r.get("is_roth", False),
                is_early=r.get("is_early", False),
            )
            for r in retirement_distributions
        ]

    # Build IRA contributions
    ira_list = None
    if ira_contributions:
        ira_list = [
            IRAContribution(
                contributor=i.get("contributor", "filer"),
                contribution_amount=i.get("contribution_amount", 0),
                age_50_plus=i.get("age_50_plus", False),
            )
            for i in ira_contributions
        ]

    # Build Social Security benefits
    ss_list = None
    if social_security_benefits:
        ss_list = [
            SocialSecurityBenefit(
                recipient=s.get("recipient", "filer"),
                gross_benefits=s.get("gross_benefits", 0),
                federal_withheld=s.get("federal_withheld", 0),
            )
            for s in social_security_benefits
        ]

    # Build unemployment benefits
    unemp_list = None
    if unemployment_benefits:
        unemp_list = [
            UnemploymentCompensation(
                state=u.get("state", ""),
                compensation=u.get("compensation", 0),
                federal_withheld=u.get("federal_withheld", 0),
                state_withheld=u.get("state_withheld", 0),
            )
            for u in unemployment_benefits
        ]

    # Build gambling income
    gamb_list = None
    if gambling_income:
        gamb_list = [
            GamblingIncome(
                payer_name=g.get("payer_name", ""),
                winnings=g.get("winnings", 0),
                federal_withheld=g.get("federal_withheld", 0),
                type_of_wager=g.get("type_of_wager", ""),
            )
            for g in gambling_income
        ]

    # Build foreign tax credits
    ftc_list = None
    if foreign_tax_credits:
        ftc_list = [
            ForeignTaxCredit(
                country=f.get("country", ""),
                foreign_source_income=f.get("foreign_source_income", 0),
                foreign_tax_paid=f.get("foreign_tax_paid", 0),
            )
            for f in foreign_tax_credits
        ]

    return dict(
        filing_status=filing_status,
        filer=filer,
        w2s=w2s,
        additional=additional,
        deductions=deductions,
        payments=payments,
        num_dependents=num_dependents,
        dependents=dep_list,
        businesses=businesses,
        residence_state=residence_state,
        work_states=work_states,
        days_worked_by_state=days_worked_by_state,
        additional_withholding=additional_withholding,
        education_expenses=edu_list,
        dependent_care_expenses=care_list,
        retirement_contributions=ret_list,
        rental_properties=rental_list,
        hsa_contributions=hsa_list,
        energy_improvements=energy_list,
        k1_incomes=k1_list,
        crypto_transactions=crypto_list,
        depreciable_assets=asset_list,
        retirement_distributions=ret_dist_list,
        ira_contributions=ira_list,
        social_security_benefits=ss_list,
        unemployment_benefits=unemp_list,
        gambling_income=gamb_list,
        gambling_losses=gambling_losses,
        foreign_tax_credits=ftc_list,
        educator_expenses=educator_expenses,
        alimony_paid=alimony_paid,
        alimony_received=alimony_received,
        capital_loss_carryover=capital_loss_carryover,
        filer_age_65_plus=filer_age_65_plus,
        filer_is_blind=filer_is_blind,
        spouse_age_65_plus=spouse_age_65_plus,
        spouse_is_blind=spouse_is_blind,
        filer_active_plan_participant=filer_active_plan_participant,
        spouse_active_plan_participant=spouse_active_plan_participant,
        prior_year_tax=prior_year_tax,
        prior_year_agi=prior_year_agi,
        tax_year=tax_year,
    )


def _result_to_dict(result: TaxResult) -> dict:
    """Convert TaxResult to a clean dict for MCP response."""
    return result.to_summary()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def compute_tax_scenario(
    filing_status: str,
    wages: float = 0,
    federal_withheld: float = 0,
    interest: float = 0,
    ordinary_dividends: float = 0,
    qualified_dividends: float = 0,
    short_term_gains: float = 0,
    long_term_gains: float = 0,
    business_income: float = 0,
    business_expenses: float = 0,
    mortgage_interest: float = 0,
    property_tax: float = 0,
    state_tax_paid: float = 0,
    charitable: float = 0,
    charitable_noncash: float = 0,
    medical_expenses: float = 0,
    student_loan_interest: float = 0,
    other_income: float = 0,
    num_dependents: int = 0,
    dependents: list[dict] | None = None,
    residence_state: str = "IL",
    work_states: list[str] | None = None,
    days_worked_by_state: dict[str, int] | None = None,
    estimated_federal: float = 0,
    estimated_state: float = 0,
    additional_withholding: float = 0,
    education_expenses: list[dict] | None = None,
    dependent_care_expenses: list[dict] | None = None,
    retirement_contributions: list[dict] | None = None,
    rental_properties: list[dict] | None = None,
    hsa_contributions: list[dict] | None = None,
    energy_improvements: list[dict] | None = None,
    k1_incomes: list[dict] | None = None,
    crypto_transactions: list[dict] | None = None,
    depreciable_assets: list[dict] | None = None,
    retirement_distributions: list[dict] | None = None,
    ira_contributions: list[dict] | None = None,
    social_security_benefits: list[dict] | None = None,
    unemployment_benefits: list[dict] | None = None,
    gambling_income: list[dict] | None = None,
    gambling_losses: float = 0,
    foreign_tax_credits: list[dict] | None = None,
    educator_expenses: float = 0,
    alimony_paid: float = 0,
    alimony_received: float = 0,
    capital_loss_carryover: float = 0,
    filer_age_65_plus: bool = False,
    filer_is_blind: bool = False,
    spouse_age_65_plus: bool = False,
    spouse_is_blind: bool = False,
    filer_active_plan_participant: bool = False,
    spouse_active_plan_participant: bool = False,
    prior_year_tax: float = 0,
    prior_year_agi: float = 0,
    tax_year: int = 2025,
) -> str:
    """Compute federal + state taxes for a given scenario.

    Args:
        filing_status: "single", "mfj" (married filing jointly), "mfs" (married filing separately), or "hoh" (head of household)
        wages: Total W-2 wages
        federal_withheld: Federal income tax withheld from W-2
        interest: Taxable interest income (1099-INT)
        ordinary_dividends: Total ordinary dividends (1099-DIV Box 1a)
        qualified_dividends: Qualified dividends (1099-DIV Box 1b) — taxed at preferential rates
        short_term_gains: Net short-term capital gains (negative for losses)
        long_term_gains: Net long-term capital gains (negative for losses)
        business_income: Gross self-employment / 1099-NEC income
        business_expenses: Total business expenses (deducted from business_income)
        mortgage_interest: Mortgage interest paid (1098 Box 1)
        property_tax: Real estate property tax paid
        state_tax_paid: State income tax paid (for SALT deduction)
        charitable: Cash charitable contributions
        charitable_noncash: Non-cash charitable contributions (clothing, goods, etc.)
        medical_expenses: Unreimbursed medical expenses (deductible above 7.5% AGI)
        student_loan_interest: Student loan interest paid (above-the-line deduction, max $2,500)
        other_income: Other taxable income (prizes, gambling, etc.)
        num_dependents: Number of qualifying children (backward compat — prefer 'dependents' list)
        dependents: Structured dependent records for accurate credit eligibility.
        residence_state: Two-letter state code where filer lives (e.g., "CA", "TX", "IL")
        work_states: Additional states where income was earned
        days_worked_by_state: Manual allocation of work days per state
        estimated_federal: Estimated federal tax payments already made
        estimated_state: Estimated state tax payments already made
        additional_withholding: Additional federal withholding from 1099s
        education_expenses: Per-student education expenses for AOTC/LLC credits.
        dependent_care_expenses: Child/dependent care expenses for CDCC (Form 2441).
        retirement_contributions: Retirement savings for Saver's Credit (Form 8880).
        rental_properties: Rental real estate (Schedule E).
        hsa_contributions: HSA contributions (Form 8889, above-the-line deduction).
        energy_improvements: Residential energy credits (Form 5695).
        k1_incomes: Schedule K-1 passthrough income from partnerships/S-corps/trusts.
        crypto_transactions: Digital asset transactions for Form 8949.
        depreciable_assets: Business/rental assets for depreciation (Form 4562). Each dict: {"description", "cost", "date_placed_in_service" (YYYY-MM-DD), "macrs_class" (3/5/7/15/27/39), "asset_use" ("business"/"rental"), "business_use_pct" (0-100), "section_179_elected", "bonus_depreciation" (bool), "recovery_year" (1-based)}. Section 179 limit: $1,250,000 (2025). Bonus: 40% (2025). Real property (27/39-year) not eligible for Section 179 or bonus.
        retirement_distributions: Form 1099-R retirement distributions. Each dict: {"payer_name", "gross_distribution", "taxable_amount", "taxable_amount_not_determined" (bool), "federal_withheld", "distribution_code" ("1"=early, "7"=normal, "G"=rollover), "is_ira" (bool, True=IRA lines 4a/4b, False=pension lines 5a/5b), "is_roth" (bool), "is_early" (bool)}. Roth and rollover distributions are non-taxable. Early distributions (code "1") incur 10% penalty.
        ira_contributions: Traditional IRA contributions for above-the-line deduction. Each dict: {"contributor" ("filer"/"spouse"), "contribution_amount", "age_50_plus" (bool)}. Limit: $7,000 ($8,000 if 50+).
        social_security_benefits: SSA-1099 Social Security benefits. Each dict: {"recipient" ("filer"/"spouse"), "gross_benefits", "federal_withheld"}. Taxable 0-85% based on provisional income (IRC §86). Single: base $25K/upper $34K. MFJ: base $32K/upper $44K.
        unemployment_benefits: Form 1099-G unemployment compensation. Each dict: {"state", "compensation", "federal_withheld", "state_withheld"}. Fully taxable.
        gambling_income: Form W-2G gambling winnings. Each dict: {"payer_name", "winnings", "federal_withheld", "type_of_wager"}. All winnings are taxable income.
        gambling_losses: Total gambling losses (limited to gambling winnings per IRC §165(d)). Offset against winnings.
        foreign_tax_credits: Foreign tax credits (Form 1116 simplified). Each dict: {"country", "foreign_source_income", "foreign_tax_paid"}. Nonrefundable credit limited by taxable income ratio.
        educator_expenses: K-12 teacher qualified expenses (above-the-line, max $300, $600 MFJ both educators).
        alimony_paid: Alimony paid under pre-2019 divorce agreement (above-the-line deduction).
        alimony_received: Alimony received under pre-2019 divorce agreement (taxable income).
        capital_loss_carryover: Prior-year capital loss carryover from Schedule D (IRC §1211). Applied as additional short-term loss.
        filer_age_65_plus: True if filer is 65+ at end of tax year (additional standard deduction).
        filer_is_blind: True if filer is legally blind (additional standard deduction).
        spouse_age_65_plus: True if spouse is 65+ (MFJ/MFS only).
        spouse_is_blind: True if spouse is legally blind (MFJ/MFS only).
        filer_active_plan_participant: True if filer is covered by employer retirement plan (W-2 Box 13). Triggers IRA deduction phaseout per IRC §219(g).
        spouse_active_plan_participant: True if spouse is covered by employer plan (MFJ only). Different phaseout range than filer.
        prior_year_tax: Prior year total tax (for Form 2210 penalty safe harbor).
        prior_year_agi: Prior year AGI (for Form 2210 high-income 110% threshold).
        tax_year: Tax year (2024 or 2025, default 2025)

    Returns:
        JSON with full tax computation: income, AGI, deductions, federal tax, credits, state tax, refund/owed, penalty
    """
    inputs = _build_inputs(
        filing_status=filing_status, wages=wages, federal_withheld=federal_withheld,
        interest=interest, ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends, short_term_gains=short_term_gains,
        long_term_gains=long_term_gains, business_income=business_income,
        business_expenses=business_expenses, mortgage_interest=mortgage_interest,
        property_tax=property_tax, state_tax_paid=state_tax_paid,
        charitable=charitable, charitable_noncash=charitable_noncash,
        medical_expenses=medical_expenses, student_loan_interest=student_loan_interest,
        other_income=other_income, num_dependents=num_dependents,
        dependents=dependents, residence_state=residence_state,
        work_states=work_states, days_worked_by_state=days_worked_by_state,
        estimated_federal=estimated_federal, estimated_state=estimated_state,
        additional_withholding=additional_withholding,
        education_expenses=education_expenses,
        dependent_care_expenses=dependent_care_expenses,
        retirement_contributions=retirement_contributions,
        rental_properties=rental_properties,
        hsa_contributions=hsa_contributions,
        energy_improvements=energy_improvements,
        k1_incomes=k1_incomes,
        crypto_transactions=crypto_transactions,
        depreciable_assets=depreciable_assets,
        retirement_distributions=retirement_distributions,
        ira_contributions=ira_contributions,
        social_security_benefits=social_security_benefits,
        unemployment_benefits=unemployment_benefits,
        gambling_income=gambling_income,
        gambling_losses=gambling_losses,
        foreign_tax_credits=foreign_tax_credits,
        educator_expenses=educator_expenses,
        alimony_paid=alimony_paid,
        alimony_received=alimony_received,
        capital_loss_carryover=capital_loss_carryover,
        filer_age_65_plus=filer_age_65_plus,
        filer_is_blind=filer_is_blind,
        spouse_age_65_plus=spouse_age_65_plus,
        spouse_is_blind=spouse_is_blind,
        filer_active_plan_participant=filer_active_plan_participant,
        spouse_active_plan_participant=spouse_active_plan_participant,
        prior_year_tax=prior_year_tax, prior_year_agi=prior_year_agi,
        tax_year=tax_year,
    )
    result = compute_tax(**inputs)
    return json.dumps(_result_to_dict(result), indent=2, default=str)


@mcp.tool()
def compare_scenarios(
    scenarios: list[dict],
) -> str:
    """Compare 2+ tax filing scenarios side-by-side.

    Each scenario dict should have the same parameters as compute_tax_scenario.
    Example: [{"filing_status": "single", "wages": 95000}, {"filing_status": "mfj", "wages": 95000}]

    Returns a comparison table with key differences highlighted.
    """
    results = []
    for i, scenario in enumerate(scenarios):
        label = scenario.pop("label", f"Scenario {i + 1}")
        inputs = _build_inputs(**scenario)
        result = compute_tax(**inputs)
        summary = _result_to_dict(result)
        summary["scenario_label"] = label
        results.append(summary)

    # Build comparison
    comparison = {
        "scenarios": results,
        "comparison": {},
    }

    if len(results) >= 2:
        keys = ["total_income", "agi", "deduction_type", "deduction_amount",
                "taxable_income", "federal_tax", "net_refund", "se_tax", "state_taxes"]
        for key in keys:
            vals = [r.get(key) for r in results]
            comparison["comparison"][key] = {
                r.get("scenario_label", f"S{i}"): v for i, (r, v) in enumerate(zip(results, vals))
            }

        # Highlight best option
        refunds = [(r.get("scenario_label"), r.get("net_refund", 0)) for r in results]
        best = max(refunds, key=lambda x: x[1])
        comparison["recommendation"] = f"{best[0]} saves the most (net refund: ${best[1]:,.2f})"

    return json.dumps(comparison, indent=2, default=str)


@mcp.tool()
def estimate_impact(
    base_scenario: dict,
    change_description: str,
    changes: dict,
) -> str:
    """Estimate the tax impact of a change (e.g., "What if I earn $10K more?").

    Args:
        base_scenario: Current tax situation (same params as compute_tax_scenario)
        change_description: Human-readable description of the change
        changes: Dict of param changes to apply on top of base (e.g., {"wages": 105000})

    Returns:
        Base result, modified result, and the delta between them.
    """
    base_inputs = _build_inputs(**base_scenario)
    base_result = compute_tax(**base_inputs)
    base_summary = _result_to_dict(base_result)

    modified_scenario = {**base_scenario, **changes}
    mod_inputs = _build_inputs(**modified_scenario)
    mod_result = compute_tax(**mod_inputs)
    mod_summary = _result_to_dict(mod_result)

    # Compute deltas
    delta_keys = ["total_income", "agi", "taxable_income", "federal_tax",
                  "net_refund", "se_tax", "niit", "additional_medicare_tax"]
    deltas = {}
    for key in delta_keys:
        base_val = base_summary.get(key, 0) or 0
        mod_val = mod_summary.get(key, 0) or 0
        deltas[key] = round(mod_val - base_val, 2)

    return json.dumps({
        "change": change_description,
        "base": base_summary,
        "modified": mod_summary,
        "deltas": deltas,
        "effective_marginal_rate": (
            round(deltas.get("federal_tax", 0) / max(deltas.get("total_income", 1), 1) * 100, 1)
        ),
    }, indent=2, default=str)


@mcp.tool()
def optimize_deductions(
    filing_status: str,
    wages: float = 0,
    federal_withheld: float = 0,
    interest: float = 0,
    ordinary_dividends: float = 0,
    qualified_dividends: float = 0,
    mortgage_interest: float = 0,
    property_tax: float = 0,
    state_tax_paid: float = 0,
    charitable: float = 0,
    charitable_noncash: float = 0,
    medical_expenses: float = 0,
    student_loan_interest: float = 0,
    num_dependents: int = 0,
    residence_state: str = "IL",
    tax_year: int = 2025,
) -> str:
    """Compare itemized vs standard deduction and recommend the better option.

    Args:
        filing_status: "single", "mfj", "mfs", or "hoh"
        wages: Total W-2 wages
        federal_withheld: Federal income tax withheld
        interest: Taxable interest income
        ordinary_dividends: Total ordinary dividends
        qualified_dividends: Qualified dividends
        mortgage_interest: Mortgage interest paid
        property_tax: Real estate property tax paid
        state_tax_paid: State income tax paid
        charitable: Cash charitable contributions
        charitable_noncash: Non-cash charitable contributions
        medical_expenses: Unreimbursed medical expenses
        student_loan_interest: Student loan interest paid
        num_dependents: Number of qualifying children
        residence_state: Two-letter state code
        tax_year: Tax year (2024 or 2025, default 2025)

    Returns both computation paths and the savings from the optimal choice.
    """
    # Compute with itemized (engine auto-picks best, but we want to show both)
    base = _build_inputs(
        filing_status=filing_status, wages=wages, federal_withheld=federal_withheld,
        interest=interest, ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends, mortgage_interest=mortgage_interest,
        property_tax=property_tax, state_tax_paid=state_tax_paid,
        charitable=charitable, charitable_noncash=charitable_noncash,
        medical_expenses=medical_expenses, student_loan_interest=student_loan_interest,
        num_dependents=num_dependents, residence_state=residence_state,
        tax_year=tax_year,
    )

    result = compute_tax(**base)
    summary = _result_to_dict(result)

    # Compute with zero itemized deductions to force standard
    no_itemized = _build_inputs(
        filing_status=filing_status, wages=wages, federal_withheld=federal_withheld,
        interest=interest, ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends,
        num_dependents=num_dependents, residence_state=residence_state,
        tax_year=tax_year,
    )
    std_result = compute_tax(**no_itemized)
    std_summary = _result_to_dict(std_result)

    itemized_total = (mortgage_interest + min(property_tax + state_tax_paid, 10000)
                      + charitable + charitable_noncash)
    std_amount = std_summary["deduction_amount"]

    return json.dumps({
        "optimal_choice": summary["deduction_type"],
        "optimal_deduction": summary["deduction_amount"],
        "optimal_tax": summary["federal_tax"],
        "standard_deduction": std_amount,
        "itemized_total": round(itemized_total, 2),
        "itemized_breakdown": {
            "mortgage_interest": mortgage_interest,
            "salt_capped": min(property_tax + state_tax_paid, 10000),
            "salt_uncapped": round(property_tax + state_tax_paid, 2),
            "charitable_cash": charitable,
            "charitable_noncash": charitable_noncash,
            "medical_expenses": medical_expenses,
        },
        "savings_from_optimal": round(abs(summary["federal_tax"] - std_summary["federal_tax"]), 2),
        "recommendation": (
            f"{'Itemize' if summary['deduction_type'] == 'itemized' else 'Take standard deduction'} "
            f"— saves ${abs(summary['federal_tax'] - std_summary['federal_tax']):,.2f} in federal tax"
        ),
    }, indent=2, default=str)


@mcp.tool()
def assess_audit_risk_tool(
    filing_status: str,
    wages: float = 0,
    federal_withheld: float = 0,
    interest: float = 0,
    ordinary_dividends: float = 0,
    qualified_dividends: float = 0,
    short_term_gains: float = 0,
    long_term_gains: float = 0,
    business_income: float = 0,
    business_expenses: float = 0,
    mortgage_interest: float = 0,
    property_tax: float = 0,
    state_tax_paid: float = 0,
    charitable: float = 0,
    charitable_noncash: float = 0,
    medical_expenses: float = 0,
    student_loan_interest: float = 0,
    other_income: float = 0,
    num_dependents: int = 0,
    dependents: list[dict] | None = None,
    residence_state: str = "IL",
    rental_properties: list[dict] | None = None,
    hsa_contributions: list[dict] | None = None,
    tax_year: int = 2025,
) -> str:
    """Assess audit risk for a tax scenario based on IRS statistical norms.

    Computes the tax return and then compares key metrics (charitable giving,
    business expense ratios, home office %, rental losses, EITC+SE combinations)
    against IRS Statistics of Income averages for the filer's AGI bracket.

    Returns a risk score (0-100), overall risk level (low/medium/high), and
    specific flags with explanations and norm comparisons.

    NOTE: This is educational — not a prediction. The IRS DIF score is secret.

    Args:
        (Same parameters as compute_tax_scenario — provide the full tax scenario)

    Returns:
        JSON with risk_score, overall_risk, flags array, and base_audit_rate for income bracket
    """
    from audit_risk import assess_audit_risk
    inputs = _build_inputs(
        filing_status=filing_status, wages=wages, federal_withheld=federal_withheld,
        interest=interest, ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends, short_term_gains=short_term_gains,
        long_term_gains=long_term_gains, business_income=business_income,
        business_expenses=business_expenses, mortgage_interest=mortgage_interest,
        property_tax=property_tax, state_tax_paid=state_tax_paid,
        charitable=charitable, charitable_noncash=charitable_noncash,
        medical_expenses=medical_expenses, student_loan_interest=student_loan_interest,
        other_income=other_income, num_dependents=num_dependents,
        dependents=dependents, residence_state=residence_state,
        rental_properties=rental_properties, hsa_contributions=hsa_contributions,
        tax_year=tax_year,
    )
    result = compute_tax(**inputs)
    report = assess_audit_risk(result)
    return json.dumps(report.to_dict(), indent=2, default=str)


@mcp.tool()
def get_tax_config(
    tax_year: int = 2025,
    filing_status: str = "single",
) -> str:
    """Look up tax brackets, standard deduction, credit limits, and other constants for a tax year.

    Useful for agents to understand the tax rules before computing scenarios.

    Args:
        tax_year: Tax year (2024 or 2025)
        filing_status: Filing status for bracket/deduction lookup ("single", "mfj", "mfs", "hoh")

    Returns:
        JSON with brackets, deductions, credit limits, SS/Medicare rates, AMT thresholds
    """
    c = get_year_config(tax_year)

    brackets = c.FEDERAL_BRACKETS.get(filing_status, c.FEDERAL_BRACKETS["single"])
    bracket_info = [{"up_to": b[0], "rate": f"{b[1]*100:.0f}%"} for b in brackets]

    return json.dumps({
        "tax_year": tax_year,
        "filing_status": filing_status,
        "supported_years": sorted(SUPPORTED_TAX_YEARS),
        "federal_brackets": bracket_info,
        "standard_deduction": c.STANDARD_DEDUCTION.get(filing_status, c.STANDARD_DEDUCTION["single"]),
        "payroll": {
            "ss_wage_base": c.SS_WAGE_BASE,
            "ss_rate": c.SS_RATE,
            "medicare_rate": c.MEDICARE_RATE,
            "additional_medicare_threshold": c.ADDITIONAL_MEDICARE_THRESHOLD.get(filing_status),
            "additional_medicare_rate": c.ADDITIONAL_MEDICARE_RATE,
        },
        "credits": {
            "ctc_per_child": c.CTC_PER_CHILD,
            "ctc_phaseout_start": c.CTC_PHASEOUT_START.get(filing_status),
            "aotc_max": c.AOTC_MAX,
            "llc_max": c.LLC_MAX,
            "eitc_max_credit": {str(k): v for k, v in c.EITC_MAX_CREDIT.items()},
            "savers_credit_max_contribution": c.SAVERS_MAX_CONTRIBUTION,
            "cdcc_max_expenses_one": c.CDCC_MAX_EXPENSES_ONE,
            "cdcc_max_expenses_two": c.CDCC_MAX_EXPENSES_TWO,
        },
        "amt": {
            "exemption": c.AMT_EXEMPTION.get(filing_status),
            "phaseout_start": c.AMT_PHASEOUT_START.get(filing_status),
        },
        "niit": {
            "rate": c.NIIT_RATE,
            "threshold": c.NIIT_THRESHOLD.get(filing_status),
        },
        "qbi": {
            "rate": c.QBI_DEDUCTION_RATE,
            "taxable_income_limit": c.QBI_TAXABLE_INCOME_LIMIT.get(filing_status),
        },
        "salt_cap": c.SALT_CAP,
        "hsa": {
            "limit_self": c.HSA_LIMIT_SELF,
            "limit_family": c.HSA_LIMIT_FAMILY,
            "catchup_55_plus": c.HSA_CATCHUP,
            "hdhp_min_deductible_self": c.HDHP_MIN_DEDUCTIBLE_SELF,
            "hdhp_min_deductible_family": c.HDHP_MIN_DEDUCTIBLE_FAMILY,
            "hdhp_max_oop_self": c.HDHP_MAX_OOP_SELF,
            "hdhp_max_oop_family": c.HDHP_MAX_OOP_FAMILY,
        },
        "rental": {
            "passive_loss_limit": c.RENTAL_LOSS_LIMIT,
            "phaseout_start_agi": c.RENTAL_LOSS_PHASEOUT_START,
            "phaseout_end_agi": c.RENTAL_LOSS_PHASEOUT_END,
        },
        "penalty": {
            "threshold": c.ESTIMATED_TAX_PENALTY_THRESHOLD,
            "rate": c.ESTIMATED_TAX_PENALTY_RATE,
            "safe_harbor_pct": c.ESTIMATED_TAX_SAFE_HARBOR_PCT,
            "high_agi_prior_year_pct": c.ESTIMATED_TAX_PRIOR_YEAR_HIGH_AGI,
        },
        "depreciation": {
            "section_179_limit": c.SECTION_179_LIMIT,
            "section_179_phaseout_start": c.SECTION_179_PHASEOUT_START,
            "bonus_rate": c.BONUS_DEPRECIATION_RATES.get(tax_year, 0.0),
            "bonus_rates_by_year": c.BONUS_DEPRECIATION_RATES,
            "macrs_classes": sorted(c.MACRS_TABLES.keys()) + [27, 39],
        },
        "retirement": {
            "ira_contribution_limit": c.IRA_CONTRIBUTION_LIMIT,
            "ira_catchup_50_plus": c.IRA_CATCHUP,
            "early_withdrawal_penalty_rate": c.EARLY_WITHDRAWAL_PENALTY_RATE,
        },
        "social_security": {
            "base_threshold": c.SS_TAXABLE_BASE_THRESHOLD.get(filing_status),
            "upper_threshold": c.SS_TAXABLE_UPPER_THRESHOLD.get(filing_status),
            "max_taxable_pct": c.SS_TAXABLE_MAX_PCT,
        },
        "energy_credits": {
            "clean_energy_rate": c.ENERGY_CLEAN_CREDIT_RATE,
            "improvement_rate": c.ENERGY_IMPROVEMENT_CREDIT_RATE,
            "improvement_annual_limit": c.ENERGY_IMPROVEMENT_ANNUAL_LIMIT,
            "improvement_envelope_limit": c.ENERGY_IMPROVEMENT_ENVELOPE_LIMIT,
            "improvement_hp_limit": c.ENERGY_IMPROVEMENT_HP_LIMIT,
        },
    }, indent=2)


@mcp.tool()
def get_draft(username: str, draft_id: str) -> str:
    """Retrieve a previously computed tax draft.

    Args:
        username: TaxLens username
        draft_id: Draft ID from a prior computation
    """
    safe_user = username.replace("/", "_").replace("..", "_")
    draft_dir = STORAGE_ROOT / safe_user / "drafts" / draft_id
    result_file = draft_dir / "result.json"
    if not result_file.exists():
        return json.dumps({"error": f"Draft {draft_id} not found for user {username}"})
    return result_file.read_text()


@mcp.tool()
def list_user_drafts(username: str) -> str:
    """List all tax drafts for a user.

    Args:
        username: TaxLens username
    """
    safe_user = username.replace("/", "_").replace("..", "_")
    drafts_dir = STORAGE_ROOT / safe_user / "drafts"
    if not drafts_dir.exists():
        return json.dumps({"drafts": []})

    drafts = []
    for d in sorted(drafts_dir.iterdir()):
        result_file = d / "result.json"
        if result_file.exists():
            data = json.loads(result_file.read_text())
            drafts.append({
                "draft_id": data.get("draft_id"),
                "filing_status": data.get("filing_status"),
                "filer_name": data.get("filer_name"),
                "total_income": data.get("total_income"),
                "net_refund": data.get("net_refund"),
            })
    return json.dumps({"drafts": drafts}, indent=2)


@mcp.tool()
def list_states() -> str:
    """List all supported states with their tax models and rates."""
    # No-tax state names for display
    _NO_TAX_NAMES = {"TX": "Texas", "FL": "Florida"}

    states_info = []
    for code in ["IL", "CA", "NY", "NJ", "PA", "NC", "GA", "OH", "TX", "FL"]:
        config = get_state_config(code)
        if config:
            info = {
                "code": config.abbreviation,
                "name": config.name,
                "tax_type": config.tax_type,
            }
            if config.tax_type == "flat":
                info["rate"] = f"{config.rate * 100:.2f}%"
            elif config.tax_type == "graduated":
                single_brackets = config.brackets.get("single", [])
                if single_brackets:
                    info["top_rate"] = f"{single_brackets[-1][1] * 100:.1f}%"
                    info["brackets"] = len(single_brackets)
            if config.reciprocal_states:
                info["reciprocal_with"] = sorted(config.reciprocal_states)
            states_info.append(info)
        elif code in NO_TAX_STATES:
            states_info.append({
                "code": code,
                "name": _NO_TAX_NAMES.get(code, code),
                "tax_type": "none",
            })
    return json.dumps({"supported_states": states_info, "count": len(states_info)}, indent=2)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------
@mcp.resource("taxlens://states")
def resource_states() -> str:
    """Supported states and their tax configurations."""
    return list_states()


@mcp.resource("taxlens://config/{tax_year}")
def resource_tax_config(tax_year: str) -> str:
    """Tax configuration for a specific year (brackets, deductions, credits)."""
    return get_tax_config(tax_year=int(tax_year))


@mcp.resource("taxlens://drafts/{username}")
def resource_user_drafts(username: str) -> str:
    """List all tax drafts for a user."""
    return list_user_drafts(username)
