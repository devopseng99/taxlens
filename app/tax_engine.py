"""Tax computation engine — Federal 1040 + multi-state for tax year 2025."""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tax_config import *
from tax_config import get_year_config, SUPPORTED_TAX_YEARS
from state_tax_engine import compute_state_tax, compute_all_state_returns
from state_configs import StateTaxResult, NO_TAX_STATES


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PersonInfo:
    first_name: str = ""
    last_name: str = ""
    ssn: str = "XXX-XX-XXXX"
    address_street: str = ""
    address_city: str = ""
    address_state: str = "IL"
    address_zip: str = ""


@dataclass
class Dependent:
    """Structured dependent record for accurate credit eligibility."""
    first_name: str = ""
    last_name: str = ""
    ssn: str = "XXX-XX-XXXX"
    date_of_birth: str = ""        # YYYY-MM-DD
    relationship: str = ""          # "son", "daughter", "stepchild", "foster", "sibling", "other"
    months_lived_with: int = 12     # Months lived with filer (EITC requires > 6)
    is_disabled: bool = False       # Permanently disabled (age waiver for CTC/EITC)
    is_student: bool = False        # Full-time student (EITC age 19→24)

    def age_at_year_end(self, tax_year: int = 2025) -> int:
        """Calculate age at end of tax year. Returns -1 if DOB not set."""
        if not self.date_of_birth:
            return -1
        try:
            parts = self.date_of_birth.split("-")
            birth_year = int(parts[0])
            birth_month = int(parts[1]) if len(parts) > 1 else 1
            birth_day = int(parts[2]) if len(parts) > 2 else 1
            # Age at Dec 31 of tax year
            age = tax_year - birth_year
            if (birth_month, birth_day) > (12, 31):
                age -= 1
            return max(0, age)
        except (ValueError, IndexError):
            return -1

    def qualifies_ctc(self, tax_year: int = 2025) -> bool:
        """Under 17 at year end (or disabled with no age limit for ODC)."""
        age = self.age_at_year_end(tax_year)
        if age == -1:
            return True  # No DOB = assume qualifies (backward compat)
        return age < 17

    def qualifies_eitc(self, tax_year: int = 2025) -> bool:
        """EITC qualifying child: under 19, or under 24 if student, or any age if disabled."""
        if self.is_disabled:
            return True
        age = self.age_at_year_end(tax_year)
        if age == -1:
            return True  # No DOB = assume qualifies
        if self.is_student:
            return age < 24
        return age < 19

    def qualifies_cdcc(self, tax_year: int = 2025) -> bool:
        """CDCC: under 13 at year end, or disabled (any age)."""
        if self.is_disabled:
            return True
        age = self.age_at_year_end(tax_year)
        if age == -1:
            return True  # No DOB = assume qualifies
        return age < 13


@dataclass
class StateWageInfo:
    """Per-state wage/withholding from a single W-2."""
    state: str = ""                  # Two-letter state code (e.g., "NY", "NJ")
    state_wages: float = 0.0
    state_withheld: float = 0.0
    state_ein: str = ""


@dataclass
class W2Income:
    employer_name: str = ""
    employer_ein: str = ""
    wages: float = 0.0
    federal_withheld: float = 0.0
    ss_wages: float = 0.0
    ss_withheld: float = 0.0
    medicare_wages: float = 0.0
    medicare_withheld: float = 0.0
    state_wages: float = 0.0        # Sum of all states (backward compat)
    state_withheld: float = 0.0     # Sum of all states (backward compat)
    local_wages: float = 0.0
    local_withheld: float = 0.0
    state_wage_infos: list = field(default_factory=list)  # list[StateWageInfo]


@dataclass
class CapitalTransaction:
    description: str = ""
    date_acquired: str = ""
    date_sold: str = ""
    proceeds: float = 0.0
    cost_basis: float = 0.0
    is_long_term: bool = False

    @property
    def gain_loss(self) -> float:
        return self.proceeds - self.cost_basis


@dataclass
class CryptoTransaction:
    """Digital asset transaction for Form 8949 / Schedule D."""
    asset_name: str = ""            # e.g., "BTC", "ETH", "SOL"
    date_acquired: str = ""         # YYYY-MM-DD or "Various"
    date_sold: str = ""             # YYYY-MM-DD
    proceeds: float = 0.0           # Sale price in USD
    cost_basis: float = 0.0         # Acquisition cost in USD
    is_long_term: bool = False      # Held > 1 year
    exchange: str = ""              # e.g., "Coinbase", "Kraken"
    tx_hash: str = ""               # Optional blockchain tx hash
    basis_method: str = "fifo"      # "fifo", "lifo", "hifo", "specific_id"
    wash_sale_loss_disallowed: float = 0.0  # IRS proposed regs 2024

    @property
    def gain_loss(self) -> float:
        return self.proceeds - self.cost_basis

    @property
    def adjusted_gain_loss(self) -> float:
        """Gain/loss after wash sale adjustment."""
        raw = self.gain_loss
        if raw < 0 and self.wash_sale_loss_disallowed > 0:
            return raw + self.wash_sale_loss_disallowed  # Reduce loss by disallowed amount
        return raw

    def to_capital_transaction(self) -> CapitalTransaction:
        """Convert to standard CapitalTransaction for Schedule D."""
        return CapitalTransaction(
            description=f"{self.asset_name} ({self.exchange})" if self.exchange else self.asset_name,
            date_acquired=self.date_acquired,
            date_sold=self.date_sold,
            proceeds=self.proceeds,
            cost_basis=self.cost_basis + self.wash_sale_loss_disallowed,  # Adjust basis for wash sale
            is_long_term=self.is_long_term,
        )


@dataclass
class DepreciableAsset:
    """Form 4562 — Depreciable business/rental asset (MACRS, Section 179, bonus)."""
    description: str = ""              # e.g., "Laptop", "Office furniture", "Rental roof"
    cost: float = 0.0                  # Original cost basis
    date_placed_in_service: str = ""   # YYYY-MM-DD (determines bonus rate and recovery year)
    macrs_class: int = 5               # 3, 5, 7, 15, 27 (residential rental), 39 (nonresidential)
    asset_use: str = "business"        # "business" (Schedule C) or "rental" (Schedule E)
    business_use_pct: float = 100.0    # Business use percentage (0-100)
    section_179_elected: float = 0.0   # Amount elected under Section 179
    bonus_depreciation: bool = True    # Elect bonus depreciation (if eligible)
    recovery_year: int = 1             # Current recovery year (1-based; 1 = placed in service year)

    @property
    def is_real_property(self) -> bool:
        return self.macrs_class in (27, 39)

    def compute_depreciation(self, tax_year: int = 2025) -> float:
        """Compute current-year depreciation for this asset."""
        from tax_config import MACRS_TABLES, BONUS_DEPRECIATION_RATES
        if self.cost <= 0:
            return 0.0

        business_pct = min(self.business_use_pct, 100.0) / 100.0
        depreciable_basis = self.cost * business_pct

        # Section 179 reduces depreciable basis (applied in year 1 only)
        s179 = 0.0
        if self.recovery_year == 1 and self.section_179_elected > 0 and not self.is_real_property:
            s179 = min(self.section_179_elected, depreciable_basis)
            depreciable_basis -= s179

        # Bonus depreciation (year 1 only, not for real property)
        bonus = 0.0
        if self.recovery_year == 1 and self.bonus_depreciation and not self.is_real_property:
            # Determine placed-in-service year for bonus rate
            pis_year = tax_year
            if self.date_placed_in_service:
                try:
                    pis_year = int(self.date_placed_in_service.split("-")[0])
                except (ValueError, IndexError):
                    pis_year = tax_year
            bonus_rate = BONUS_DEPRECIATION_RATES.get(pis_year, 0.0)
            bonus = depreciable_basis * bonus_rate
            depreciable_basis -= bonus

        # MACRS regular depreciation on remaining basis
        macrs_depr = 0.0
        if self.is_real_property:
            # Straight-line for real property
            years = 27.5 if self.macrs_class == 27 else 39.0
            macrs_depr = depreciable_basis / years
        else:
            table = MACRS_TABLES.get(self.macrs_class)
            if table and 0 < self.recovery_year <= len(table):
                macrs_depr = depreciable_basis * table[self.recovery_year - 1]

        return round(s179 + bonus + macrs_depr, 2)


@dataclass
class Deductions:
    mortgage_interest: float = 0.0
    property_tax: float = 0.0
    state_income_tax_paid: float = 0.0
    charitable_cash: float = 0.0
    charitable_noncash: float = 0.0
    medical_expenses: float = 0.0
    student_loan_interest: float = 0.0


@dataclass
class BusinessIncome:
    """Schedule C — Profit or Loss from Business."""
    business_name: str = ""
    business_type: str = ""       # e.g., "Consulting", "Freelance", "Rideshare"
    ein: str = ""
    gross_receipts: float = 0.0
    cost_of_goods_sold: float = 0.0
    # Expenses
    advertising: float = 0.0
    car_expenses: float = 0.0
    insurance: float = 0.0
    office_expense: float = 0.0
    rent: float = 0.0
    supplies: float = 0.0
    utilities: float = 0.0
    home_office_sqft: float = 0.0
    home_total_sqft: float = 0.0
    home_expenses: float = 0.0     # Mortgage interest + utilities + insurance for home
    other_expenses: float = 0.0
    other_expenses_description: str = ""

    @property
    def gross_profit(self) -> float:
        return self.gross_receipts - self.cost_of_goods_sold

    @property
    def total_expenses(self) -> float:
        home_office = 0.0
        if self.home_total_sqft > 0 and self.home_office_sqft > 0:
            home_office = self.home_expenses * (self.home_office_sqft / self.home_total_sqft)
        return (self.advertising + self.car_expenses + self.insurance +
                self.office_expense + self.rent + self.supplies +
                self.utilities + home_office + self.other_expenses)

    @property
    def net_profit(self) -> float:
        return self.gross_profit - self.total_expenses


@dataclass
class DividendIncome:
    """1099-DIV — Dividends and Distributions from a single payer."""
    payer_name: str = ""
    ordinary_dividends: float = 0.0    # Box 1a — taxed as ordinary income
    qualified_dividends: float = 0.0   # Box 1b — preferential 0/15/20% rates
    capital_gain_dist: float = 0.0     # Box 2a — long-term capital gain distributions
    section_199a: float = 0.0          # Box 5 — Section 199A dividends (QBI)
    federal_withheld: float = 0.0      # Box 4


@dataclass
class AdditionalIncome:
    other_interest: float = 0.0
    ordinary_dividends: float = 0.0
    qualified_dividends: float = 0.0
    capital_transactions: list = field(default_factory=list)
    other_income: float = 0.0
    other_income_description: str = ""


@dataclass
class EducationExpense:
    """Per-student education expenses for Form 8863."""
    student_name: str = ""
    qualified_expenses: float = 0.0
    credit_type: str = "aotc"  # "aotc" or "llc"


@dataclass
class DependentCareExpense:
    """Child/dependent care expenses for Form 2441."""
    dependent_name: str = ""
    care_expenses: float = 0.0


@dataclass
class RetirementContribution:
    """Retirement savings contributions for Saver's Credit (Form 8880)."""
    contributor: str = "filer"  # "filer" or "spouse"
    contribution_amount: float = 0.0


@dataclass
class RentalProperty:
    """Schedule E — Supplemental Income from rental real estate."""
    property_address: str = ""
    rental_days: int = 365            # Days rented at fair market value
    personal_use_days: int = 0        # Days of personal use
    gross_rents: float = 0.0          # Gross rental income received
    # Expenses
    advertising: float = 0.0
    auto_travel: float = 0.0
    cleaning_maintenance: float = 0.0
    commissions: float = 0.0
    insurance: float = 0.0
    legal_professional: float = 0.0
    management_fees: float = 0.0
    mortgage_interest: float = 0.0
    repairs: float = 0.0
    supplies: float = 0.0
    taxes: float = 0.0
    utilities: float = 0.0
    depreciation: float = 0.0
    other_expenses: float = 0.0

    @property
    def total_expenses(self) -> float:
        return (self.advertising + self.auto_travel + self.cleaning_maintenance +
                self.commissions + self.insurance + self.legal_professional +
                self.management_fees + self.mortgage_interest + self.repairs +
                self.supplies + self.taxes + self.utilities + self.depreciation +
                self.other_expenses)

    @property
    def net_income(self) -> float:
        return self.gross_rents - self.total_expenses


@dataclass
class HSAContribution:
    """Health Savings Account contribution for above-the-line deduction + Form 8889."""
    contributor: str = "filer"        # "filer" or "spouse"
    contribution_amount: float = 0.0
    employer_contributions: float = 0.0  # Employer (incl. cafeteria/pre-tax) — Form 8889 Line 9
    coverage_type: str = "self"       # "self" or "family"
    age_55_plus: bool = False         # Catch-up eligible ($1,000 extra)


@dataclass
class EnergyImprovement:
    """Form 5695 — Residential energy credits."""
    # §25D: Residential Clean Energy (solar, wind, geothermal, battery storage)
    solar_electric: float = 0.0       # Solar panels cost
    solar_water_heating: float = 0.0  # Solar water heater cost
    small_wind: float = 0.0           # Small wind turbine cost
    geothermal_heat_pump: float = 0.0 # Geothermal heat pump cost
    battery_storage: float = 0.0      # Battery storage ≥3 kWh
    fuel_cell: float = 0.0            # Fuel cell property
    # §25C: Energy Efficient Home Improvement
    insulation: float = 0.0           # Insulation materials
    windows_skylights: float = 0.0    # ENERGY STAR windows/skylights
    exterior_doors: float = 0.0       # ENERGY STAR exterior doors
    heat_pump: float = 0.0            # Heat pump (HVAC or water heater)
    biomass_stove: float = 0.0        # Biomass stove/boiler
    energy_audit: float = 0.0         # Home energy audit (max $150)


@dataclass
class K1Income:
    """Schedule K-1 passthrough income from partnerships, S-corps, or trusts."""
    entity_name: str = ""
    entity_ein: str = ""
    entity_type: str = "partnership"  # "partnership" (1065), "s_corp" (1120S), "trust" (1041)
    ordinary_income: float = 0.0      # Box 1 (1065/1120S) or Box 1 (1041)
    rental_income: float = 0.0        # Box 2 (1065) — net rental real estate
    interest_income: float = 0.0      # Box 5 (1065) / Box 4a (1120S)
    dividend_income: float = 0.0      # Box 6a (1065) / Box 4b (1120S)
    qualified_dividends: float = 0.0  # Box 6b (1065)
    short_term_gain: float = 0.0      # Box 8 (1065) / Box 7 (1120S)
    long_term_gain: float = 0.0       # Box 9a (1065) / Box 8a (1120S)
    section_1231_gain: float = 0.0    # Box 10 (1065) / Box 9 (1120S)
    guaranteed_payments: float = 0.0  # Box 4 (1065) — subject to SE tax for partnerships
    section_199a_income: float = 0.0  # Box 20 Code Z (1065) — QBI for §199A deduction
    distributions: float = 0.0        # Box 19 (1065) — not taxable, reduces basis
    tax_exempt_income: float = 0.0    # Box 18 (1065) — not taxable


@dataclass
class RetirementDistribution:
    """Form 1099-R — Distributions from retirement accounts."""
    payer_name: str = ""
    gross_distribution: float = 0.0      # Box 1
    taxable_amount: float = 0.0          # Box 2a (0 if unknown, use gross)
    taxable_amount_not_determined: bool = False  # Box 2b checkbox
    federal_withheld: float = 0.0        # Box 4
    distribution_code: str = "7"         # Box 7: "1"=early, "7"=normal, "2"=Roth exception, "G"=rollover
    is_roth: bool = False                # Roth IRA/401k (qualified = tax-free)
    is_early: bool = False               # Under age 59½ (10% penalty unless exception)

    @property
    def taxable(self) -> float:
        """Taxable portion of the distribution."""
        if self.is_roth:
            return 0.0  # Qualified Roth distributions are tax-free
        if self.distribution_code in ("G", "H"):
            return 0.0  # Rollover — not taxable
        if self.taxable_amount_not_determined:
            return self.gross_distribution  # Assume fully taxable
        return self.taxable_amount if self.taxable_amount > 0 else self.gross_distribution

    @property
    def early_withdrawal_penalty(self) -> float:
        """10% early withdrawal penalty (under 59½, no exception)."""
        if self.is_early and self.distribution_code == "1":
            return self.taxable * 0.10
        return 0.0


@dataclass
class IRAContribution:
    """Traditional IRA contribution — above-the-line deduction."""
    contributor: str = "filer"       # "filer" or "spouse"
    contribution_amount: float = 0.0
    age_50_plus: bool = False        # $1,000 catch-up contribution


@dataclass
class SocialSecurityBenefit:
    """SSA-1099 — Social Security benefits received."""
    recipient: str = "filer"       # "filer" or "spouse"
    gross_benefits: float = 0.0    # Box 5: net benefits (Box 3 - Box 4 repayments)
    federal_withheld: float = 0.0  # Box 6: voluntary federal tax withholding (Form W-4V)


@dataclass
class Payments:
    estimated_federal: float = 0.0
    estimated_state: float = 0.0


# ---------------------------------------------------------------------------
# Tax computation result
# ---------------------------------------------------------------------------
@dataclass
class TaxResult:
    draft_id: str = ""
    filing_status: str = SINGLE
    tax_year: int = TAX_YEAR

    # Filer info
    filer: Optional[PersonInfo] = None
    spouse: Optional[PersonInfo] = None
    num_dependents: int = 0
    dependents: list = field(default_factory=list)  # list[Dependent]
    num_ctc_children: int = 0      # Under 17 (or disabled)
    num_eitc_children: int = 0     # Under 19/24-student/disabled
    num_cdcc_dependents: int = 0   # Under 13 or disabled

    # --- Form 1040 lines ---
    # Income
    line_1a_wages: float = 0.0           # Total W-2 wages
    line_2a_tax_exempt_interest: float = 0.0
    line_2b_taxable_interest: float = 0.0  # 1099-INT + other
    line_3a_qualified_dividends: float = 0.0
    line_3b_ordinary_dividends: float = 0.0
    line_7_capital_gain_loss: float = 0.0  # From Schedule D
    line_8_other_income: float = 0.0
    line_8a_business_income: float = 0.0  # Schedule C net profit
    line_9_total_income: float = 0.0

    # Adjustments
    line_10_adjustments: float = 0.0     # Student loan interest, etc.
    se_tax_deduction: float = 0.0        # 50% of SE tax (above-the-line)
    line_11_agi: float = 0.0             # Adjusted Gross Income

    # Deductions
    deduction_type: str = "standard"     # "standard" or "itemized"
    standard_deduction: float = 0.0
    itemized_total: float = 0.0
    line_13_deduction: float = 0.0       # The chosen deduction
    line_15_taxable_income: float = 0.0

    # Tax computation
    line_16_tax: float = 0.0             # Ordinary income tax
    capital_gains_tax: float = 0.0       # Preferential rate on LTCG/QD
    se_tax: float = 0.0                  # Self-employment tax (Schedule SE)
    niit: float = 0.0                    # Net Investment Income Tax (3.8%)
    additional_medicare_tax: float = 0.0 # Additional Medicare Tax (0.9%)
    qbi_deduction: float = 0.0           # Section 199A QBI deduction
    amt: float = 0.0                      # Alternative Minimum Tax (Form 6251)
    amt_income: float = 0.0               # AMT taxable income
    amt_exemption: float = 0.0            # AMT exemption amount
    amt_tentative: float = 0.0            # Tentative minimum tax
    line_24_total_tax: float = 0.0

    # Payments & credits
    line_25_federal_withheld: float = 0.0
    line_27_ctc: float = 0.0             # Child Tax Credit
    education_credit: float = 0.0         # AOTC + LLC (nonrefundable portion)
    education_credit_refundable: float = 0.0  # AOTC refundable portion (40%)
    eitc: float = 0.0                     # Earned Income Tax Credit (refundable)
    eitc_earned_income: float = 0.0       # Earned income used for EITC calc
    cdcc: float = 0.0                     # Child and Dependent Care Credit (nonrefundable)
    savers_credit: float = 0.0            # Retirement Savings Credit (nonrefundable)
    estimated_payments: float = 0.0
    line_33_total_payments: float = 0.0

    # Estimated tax penalty
    estimated_tax_penalty: float = 0.0    # Form 2210 penalty
    estimated_tax_required: float = 0.0   # Required annual payment

    # Bottom line
    line_34_overpaid: float = 0.0        # Refund
    line_37_owed: float = 0.0            # Amount owed

    # --- Schedule A (Itemized) ---
    sched_a_medical: float = 0.0
    sched_a_salt: float = 0.0
    sched_a_mortgage_interest: float = 0.0
    sched_a_charitable: float = 0.0
    sched_a_total: float = 0.0

    # --- Schedule B ---
    sched_b_interest_total: float = 0.0
    sched_b_dividends_total: float = 0.0

    # --- Schedule C (Business Income) ---
    sched_c_businesses: list = field(default_factory=list)
    sched_c_total_profit: float = 0.0

    # --- Schedule SE (Self-Employment Tax) ---
    sched_se_net_earnings: float = 0.0
    sched_se_taxable: float = 0.0
    sched_se_ss_tax: float = 0.0
    sched_se_medicare_tax: float = 0.0
    sched_se_total: float = 0.0

    # --- Schedule D ---
    sched_d_short_term_gain: float = 0.0
    sched_d_long_term_gain: float = 0.0
    sched_d_net_gain: float = 0.0

    # --- Schedule E (Rental Income) ---
    sched_e_properties: list = field(default_factory=list)
    sched_e_total_income: float = 0.0
    sched_e_total_expenses: float = 0.0
    sched_e_net_income: float = 0.0

    # --- Crypto / Form 8949 ---
    crypto_short_term_gain: float = 0.0
    crypto_long_term_gain: float = 0.0
    crypto_total_proceeds: float = 0.0
    crypto_total_basis: float = 0.0
    crypto_wash_sale_disallowed: float = 0.0
    crypto_transactions_count: int = 0

    # --- Form 5695 (Energy Credits) ---
    energy_clean_credit: float = 0.0         # §25D residential clean energy
    energy_improvement_credit: float = 0.0   # §25C home improvement
    energy_total_credit: float = 0.0         # Total Form 5695 credit (nonrefundable)

    # --- Schedule K-1 (Passthrough Income) ---
    k1_ordinary_income: float = 0.0
    k1_rental_income: float = 0.0
    k1_interest_income: float = 0.0
    k1_dividend_income: float = 0.0
    k1_capital_gains: float = 0.0
    k1_guaranteed_payments: float = 0.0
    k1_section_199a_income: float = 0.0

    # --- Quarterly Estimated Tax Planner ---
    quarterly_estimated_tax: float = 0.0     # Per-quarter estimated payment
    quarterly_schedule: list = field(default_factory=list)  # 4 quarterly amounts

    # --- Retirement Income / Form 1099-R ---
    retirement_gross_distributions: float = 0.0   # Total 1099-R Box 1
    retirement_taxable_amount: float = 0.0        # Taxable portion → Line 4b/5b
    retirement_federal_withheld: float = 0.0      # 1099-R Box 4 withholding
    retirement_early_penalty: float = 0.0         # 10% early withdrawal penalty
    retirement_distributions_count: int = 0
    ira_deduction: float = 0.0                    # Traditional IRA above-the-line deduction

    # --- Social Security Benefits (SSA-1099) ---
    ss_gross_benefits: float = 0.0           # Total SS benefits received
    ss_taxable_amount: float = 0.0           # Taxable portion (0/50/85%)
    ss_federal_withheld: float = 0.0         # W-4V voluntary withholding
    ss_provisional_income: float = 0.0       # MAGI + 50% of SS for threshold test
    ss_taxable_pct: float = 0.0              # Effective taxable percentage

    # --- Depreciation / Form 4562 ---
    depreciation_total: float = 0.0          # Total depreciation deduction
    depreciation_section_179: float = 0.0    # Section 179 portion
    depreciation_bonus: float = 0.0          # Bonus depreciation portion
    depreciation_macrs: float = 0.0          # Regular MACRS portion
    depreciation_business: float = 0.0       # Amount flowing to Schedule C
    depreciation_rental: float = 0.0         # Amount flowing to Schedule E
    depreciation_assets_count: int = 0       # Number of depreciable assets

    # --- HSA / Form 8889 ---
    hsa_deduction: float = 0.0
    form_8889_contributions: float = 0.0     # Line 2: total personal contributions
    form_8889_employer: float = 0.0          # Line 9: employer contributions
    form_8889_limit: float = 0.0             # Line 7: contribution limit
    form_8889_deduction: float = 0.0         # Line 13: deductible amount
    form_8889_excess: float = 0.0            # Excess contributions (6% excise via Form 5329)

    # --- Illinois IL-1040 ---
    il_line_1_federal_agi: float = 0.0
    il_line_3_additions: float = 0.0
    il_line_7_base_income: float = 0.0
    il_line_9_exemptions: float = 0.0
    il_line_10_taxable: float = 0.0
    il_line_11_tax: float = 0.0
    il_line_18_withheld: float = 0.0
    il_estimated_payments: float = 0.0
    il_refund: float = 0.0
    il_owed: float = 0.0

    # Multi-state
    residence_state: str = "IL"
    state_returns: list = field(default_factory=list)

    # Detail for forms
    w2s: list = field(default_factory=list)
    businesses: list = field(default_factory=list)
    capital_transactions: list = field(default_factory=list)

    # Forms generated
    forms_generated: list = field(default_factory=list)
    pdf_paths: dict = field(default_factory=dict)

    def to_summary(self) -> dict:
        # Build state_taxes array from state_returns
        state_taxes = []
        for sr in self.state_returns:
            state_taxes.append({
                "state": sr.state_code,
                "state_name": sr.state_name,
                "return_type": sr.return_type,
                "tax": round(sr.total_tax, 2),
                "withholding": round(sr.withholding, 2),
                "credit_for_other_states": round(sr.credit_for_other_states, 2),
                "refund": round(sr.refund, 2),
                "owed": round(sr.owed, 2),
            })

        # Total state refunds/owed across all states
        total_state_refund = sum(sr.refund for sr in self.state_returns)
        total_state_owed = sum(sr.owed for sr in self.state_returns)

        summary = {
            "draft_id": self.draft_id,
            "filing_status": self.filing_status,
            "tax_year": self.tax_year,
            "filer_name": f"{self.filer.first_name} {self.filer.last_name}" if self.filer else "",
            "num_dependents": self.num_dependents,
            "num_ctc_children": self.num_ctc_children,
            "num_eitc_children": self.num_eitc_children,
            "dependents": [
                {"name": f"{d.first_name} {d.last_name}", "dob": d.date_of_birth,
                 "relationship": d.relationship, "ctc": d.qualifies_ctc(),
                 "eitc": d.qualifies_eitc(), "cdcc": d.qualifies_cdcc()}
                for d in self.dependents
            ] if self.dependents else [],
            "residence_state": self.residence_state,
            "total_income": round(self.line_9_total_income, 2),
            "agi": round(self.line_11_agi, 2),
            "deduction_type": self.deduction_type,
            "deduction_amount": round(self.line_13_deduction, 2),
            "taxable_income": round(self.line_15_taxable_income, 2),
            "business_income": round(self.sched_c_total_profit, 2),
            "rental_income": round(self.sched_e_net_income, 2),
            "hsa_deduction": round(self.hsa_deduction, 2),
            "form_8889": {
                "personal_contributions": round(self.form_8889_contributions, 2),
                "employer_contributions": round(self.form_8889_employer, 2),
                "contribution_limit": round(self.form_8889_limit, 2),
                "deduction": round(self.form_8889_deduction, 2),
                "excess_contributions": round(self.form_8889_excess, 2),
            } if self.form_8889_contributions > 0 or self.form_8889_employer > 0 else None,
            "se_tax": round(self.se_tax, 2),
            "niit": round(self.niit, 2),
            "additional_medicare_tax": round(self.additional_medicare_tax, 2),
            "qbi_deduction": round(self.qbi_deduction, 2),
            "amt": round(self.amt, 2),
            "education_credit": round(self.education_credit, 2),
            "education_credit_refundable": round(self.education_credit_refundable, 2),
            "eitc": round(self.eitc, 2),
            "cdcc": round(self.cdcc, 2),
            "savers_credit": round(self.savers_credit, 2),
            "crypto": {
                "short_term_gain": round(self.crypto_short_term_gain, 2),
                "long_term_gain": round(self.crypto_long_term_gain, 2),
                "total_proceeds": round(self.crypto_total_proceeds, 2),
                "total_basis": round(self.crypto_total_basis, 2),
                "wash_sale_disallowed": round(self.crypto_wash_sale_disallowed, 2),
                "transactions": self.crypto_transactions_count,
            } if self.crypto_transactions_count > 0 else None,
            "retirement": {
                "gross_distributions": round(self.retirement_gross_distributions, 2),
                "taxable_amount": round(self.retirement_taxable_amount, 2),
                "federal_withheld": round(self.retirement_federal_withheld, 2),
                "early_penalty": round(self.retirement_early_penalty, 2),
                "distributions_count": self.retirement_distributions_count,
                "ira_deduction": round(self.ira_deduction, 2),
            } if self.retirement_distributions_count > 0 or self.ira_deduction > 0 else None,
            "social_security": {
                "gross_benefits": round(self.ss_gross_benefits, 2),
                "taxable_amount": round(self.ss_taxable_amount, 2),
                "taxable_pct": round(self.ss_taxable_pct * 100, 1),
                "provisional_income": round(self.ss_provisional_income, 2),
                "federal_withheld": round(self.ss_federal_withheld, 2),
            } if self.ss_gross_benefits > 0 else None,
            "depreciation": {
                "total": round(self.depreciation_total, 2),
                "section_179": round(self.depreciation_section_179, 2),
                "bonus": round(self.depreciation_bonus, 2),
                "macrs": round(self.depreciation_macrs, 2),
                "business": round(self.depreciation_business, 2),
                "rental": round(self.depreciation_rental, 2),
                "assets": self.depreciation_assets_count,
            } if self.depreciation_assets_count > 0 else None,
            "energy_credit": round(self.energy_total_credit, 2),
            "energy_clean_credit": round(self.energy_clean_credit, 2),
            "energy_improvement_credit": round(self.energy_improvement_credit, 2),
            "k1_ordinary_income": round(self.k1_ordinary_income, 2),
            "k1_rental_income": round(self.k1_rental_income, 2),
            "k1_capital_gains": round(self.k1_capital_gains, 2),
            "k1_guaranteed_payments": round(self.k1_guaranteed_payments, 2),
            "quarterly_estimated_tax": round(self.quarterly_estimated_tax, 2),
            "quarterly_schedule": self.quarterly_schedule if self.quarterly_schedule else None,
            "estimated_tax_penalty": round(self.estimated_tax_penalty, 2),
            "federal_tax": round(self.line_24_total_tax, 2),
            "federal_withholding": round(self.line_25_federal_withheld, 2),
            "federal_refund": round(self.line_34_overpaid, 2),
            "federal_owed": round(self.line_37_owed, 2),
            # Backward compat: IL-specific keys
            "illinois_tax": round(self.il_line_11_tax, 2),
            "illinois_withholding": round(self.il_line_18_withheld, 2),
            "illinois_refund": round(self.il_refund, 2),
            "illinois_owed": round(self.il_owed, 2),
            # New: generic state taxes array
            "state_taxes": state_taxes,
            "net_refund": round(
                self.line_34_overpaid + total_state_refund
                - self.line_37_owed - total_state_owed, 2
            ),
            "forms_generated": self.forms_generated,
        }
        return summary


# ---------------------------------------------------------------------------
# Bracket computation helpers
# ---------------------------------------------------------------------------
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


def compute_ltcg_tax(taxable_income: float, ltcg_amount: float, brackets: list) -> float:
    """Compute preferential capital gains tax.

    taxable_income = total taxable income (determines which bracket the LTCG sits in)
    ltcg_amount = qualified dividends + net long-term capital gains
    """
    if ltcg_amount <= 0:
        return 0.0

    ordinary_income = max(0, taxable_income - ltcg_amount)
    tax = 0.0
    prev = 0.0

    for upper, rate in brackets:
        # How much of the LTCG falls in this bracket?
        bracket_start = max(prev, ordinary_income)
        bracket_end = min(upper, taxable_income)
        taxable_in_bracket = max(0, bracket_end - bracket_start)
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev = upper
        if taxable_income <= upper:
            break

    return tax


# ---------------------------------------------------------------------------
# W-2 OCR data parser
# ---------------------------------------------------------------------------
def parse_w2_from_ocr(ocr_fields: dict) -> W2Income:
    """Convert TaxLens OCR fields to W2Income dataclass."""

    def get_val(name: str) -> str:
        f = ocr_fields.get(name, {})
        v = f.get("value")
        return str(v) if v is not None else ""

    def get_nested(parent: str, child: str) -> str:
        p = ocr_fields.get(parent, {})
        val = p.get("value")
        if not isinstance(val, dict):
            return ""
        c = val.get(child, {})
        return str(c.get("value", "")) if isinstance(c, dict) else ""

    def parse_money(s: str) -> float:
        if not s:
            return 0.0
        cleaned = s.replace("$", "").replace(",", "").replace(" ", "").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0

    # State tax info — extract per-state breakdowns
    state_wages = 0.0
    state_withheld = 0.0
    local_wages = 0.0
    local_withheld = 0.0
    state_wage_infos = []

    state_info = ocr_fields.get("StateTaxInfos", {})
    if state_info.get("type") == "array" and isinstance(state_info.get("value"), list):
        for item in state_info["value"]:
            if isinstance(item, dict):
                val = item.get("value", item)
                if isinstance(val, dict):
                    sw = parse_money(str(val.get("StateWages", {}).get("value", "")))
                    swh = parse_money(str(val.get("StateIncomeTax", {}).get("value", "")))
                    st_code = str(val.get("State", {}).get("value", "")).upper().strip()
                    state_wages += sw
                    state_withheld += swh
                    if st_code:
                        state_wage_infos.append(StateWageInfo(
                            state=st_code, state_wages=sw, state_withheld=swh,
                        ))

    local_info = ocr_fields.get("LocalTaxInfos", {})
    if local_info.get("type") == "array" and isinstance(local_info.get("value"), list):
        for item in local_info["value"]:
            if isinstance(item, dict):
                val = item.get("value", item)
                if isinstance(val, dict):
                    local_wages += parse_money(str(val.get("LocalWages", {}).get("value", "")))
                    local_withheld += parse_money(str(val.get("LocalIncomeTax", {}).get("value", "")))

    return W2Income(
        employer_name=get_nested("Employer", "Name"),
        employer_ein=get_nested("Employer", "IdNumber"),
        wages=parse_money(get_val("WagesTipsAndOtherCompensation")),
        federal_withheld=parse_money(get_val("FederalIncomeTaxWithheld")),
        ss_wages=parse_money(get_val("SocialSecurityWages")),
        ss_withheld=parse_money(get_val("SocialSecurityTaxWithheld")),
        medicare_wages=parse_money(get_val("MedicareWagesAndTips")),
        medicare_withheld=parse_money(get_val("MedicareTaxWithheld")),
        state_wages=state_wages,
        state_withheld=state_withheld,
        local_wages=local_wages,
        local_withheld=local_withheld,
        state_wage_infos=state_wage_infos,
    )


def parse_1099int_from_ocr(ocr_fields: dict) -> float:
    """Extract taxable interest from 1099-INT OCR result."""
    transactions = ocr_fields.get("Transactions", {})
    if transactions.get("type") == "array" and isinstance(transactions.get("value"), list):
        total = 0.0
        for item in transactions["value"]:
            val = item.get("value", item) if isinstance(item, dict) else {}
            if isinstance(val, dict):
                box1 = val.get("Box1", {})
                box1_val = box1.get("value", "") if isinstance(box1, dict) else ""
                cleaned = str(box1_val).replace("$", "").replace(",", "").replace(" ", "").strip()
                try:
                    total += float(cleaned)
                except (ValueError, TypeError):
                    pass
        return total

    # Flat field fallback
    box1 = ocr_fields.get("Box1", {}).get("value", "")
    cleaned = str(box1).replace("$", "").replace(",", "").replace(" ", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _parse_money(s: str) -> float:
    """Parse a dollar string like '$2,450.00' to float."""
    if not s:
        return 0.0
    cleaned = s.replace("$", "").replace(",", "").replace(" ", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _get_field_value(ocr_fields: dict, name: str) -> str:
    """Extract the value string from an Azure DI field."""
    f = ocr_fields.get(name, {})
    v = f.get("value")
    return str(v) if v is not None else ""


def parse_1099div_from_ocr(ocr_fields: dict) -> DividendIncome:
    """Extract dividend income from 1099-DIV OCR result.

    Azure model: prebuilt-tax.us.1099DIV
    Handles both flat field layout and Transactions array format.
    """
    # Try Transactions array format first (some Azure responses wrap in array)
    transactions = ocr_fields.get("Transactions", {})
    if transactions.get("type") == "array" and isinstance(transactions.get("value"), list):
        result = DividendIncome()
        for item in transactions["value"]:
            val = item.get("value", item) if isinstance(item, dict) else {}
            if isinstance(val, dict):
                result.payer_name = result.payer_name or str(val.get("Payer", {}).get("value", ""))
                result.ordinary_dividends += _parse_money(str(val.get("Box1a", {}).get("value", "")))
                result.qualified_dividends += _parse_money(str(val.get("Box1b", {}).get("value", "")))
                result.capital_gain_dist += _parse_money(str(val.get("Box2a", {}).get("value", "")))
                result.federal_withheld += _parse_money(str(val.get("Box4", {}).get("value", "")))
                result.section_199a += _parse_money(str(val.get("Box5", {}).get("value", "")))
        return result

    # Flat field layout
    payer = ocr_fields.get("Payer", {})
    payer_name = ""
    if isinstance(payer.get("value"), dict):
        payer_name = str(payer["value"].get("Name", {}).get("value", ""))
    elif isinstance(payer.get("value"), str):
        payer_name = payer["value"]

    return DividendIncome(
        payer_name=payer_name,
        ordinary_dividends=_parse_money(_get_field_value(ocr_fields, "Box1a")),
        qualified_dividends=_parse_money(_get_field_value(ocr_fields, "Box1b")),
        capital_gain_dist=_parse_money(_get_field_value(ocr_fields, "Box2a")),
        federal_withheld=_parse_money(_get_field_value(ocr_fields, "Box4")),
        section_199a=_parse_money(_get_field_value(ocr_fields, "Box5")),
    )


def parse_1099nec_from_ocr(ocr_fields: dict) -> tuple[BusinessIncome, float]:
    """Extract nonemployee compensation from 1099-NEC OCR result.

    Azure model: prebuilt-tax.us.1099NEC
    Returns (BusinessIncome, federal_withheld).
    """
    # Payer name
    payer = ocr_fields.get("Payer", {})
    payer_name = ""
    if isinstance(payer.get("value"), dict):
        payer_name = str(payer["value"].get("Name", {}).get("value", ""))
    elif isinstance(payer.get("value"), str):
        payer_name = payer["value"]

    nec = _parse_money(_get_field_value(ocr_fields, "Box1"))
    withheld = _parse_money(_get_field_value(ocr_fields, "Box4"))

    biz = BusinessIncome(
        business_name=payer_name or "1099-NEC Income",
        gross_receipts=nec,
    )
    return biz, withheld


def parse_1098_from_ocr(ocr_fields: dict) -> float:
    """Extract mortgage interest from 1098 OCR result.

    Azure model: prebuilt-tax.us.1098
    Returns mortgage interest paid (Box 1).
    """
    # Try direct Box1 field
    val = _parse_money(_get_field_value(ocr_fields, "Box1"))
    if val > 0:
        return val

    # Try MortgageInterest field (some Azure responses use descriptive names)
    val = _parse_money(_get_field_value(ocr_fields, "MortgageInterest"))
    if val > 0:
        return val

    # Try Transactions array fallback
    transactions = ocr_fields.get("Transactions", {})
    if transactions.get("type") == "array" and isinstance(transactions.get("value"), list):
        for item in transactions["value"]:
            v = item.get("value", item) if isinstance(item, dict) else {}
            if isinstance(v, dict):
                box1 = _parse_money(str(v.get("Box1", {}).get("value", "")))
                if box1 > 0:
                    return box1

    return 0.0


def parse_1099b_from_structured(data: list[dict]) -> list[CapitalTransaction]:
    """Parse structured 1099-B transaction data (JSON/CSV import, not OCR).

    Each dict should have: description, date_acquired, date_sold, proceeds,
    cost_basis, is_long_term (bool or "long"/"short" string).
    """
    transactions = []
    for row in data:
        is_lt = row.get("is_long_term", False)
        if isinstance(is_lt, str):
            is_lt = is_lt.lower() in ("true", "long", "yes", "l", "1")

        transactions.append(CapitalTransaction(
            description=str(row.get("description", "Security Sale")),
            date_acquired=str(row.get("date_acquired", "Various")),
            date_sold=str(row.get("date_sold", "2025")),
            proceeds=float(row.get("proceeds", 0)),
            cost_basis=float(row.get("cost_basis", 0)),
            is_long_term=bool(is_lt),
        ))
    return transactions


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------
def compute_tax(
    filing_status: str,
    filer: PersonInfo,
    w2s: list[W2Income],
    additional: AdditionalIncome,
    deductions: Deductions,
    payments: Payments,
    spouse: Optional[PersonInfo] = None,
    num_dependents: int = 0,
    dependents: list[Dependent] | None = None,
    businesses: list[BusinessIncome] | None = None,
    residence_state: str = "IL",
    work_states: list[str] | None = None,
    days_worked_by_state: dict[str, int] | None = None,
    additional_withholding: float = 0.0,
    education_expenses: list[EducationExpense] | None = None,
    dependent_care_expenses: list[DependentCareExpense] | None = None,
    retirement_contributions: list[RetirementContribution] | None = None,
    rental_properties: list[RentalProperty] | None = None,
    hsa_contributions: list[HSAContribution] | None = None,
    energy_improvements: list[EnergyImprovement] | None = None,
    k1_incomes: list[K1Income] | None = None,
    crypto_transactions: list[CryptoTransaction] | None = None,
    depreciable_assets: list[DepreciableAsset] | None = None,
    retirement_distributions: list[RetirementDistribution] | None = None,
    ira_contributions: list[IRAContribution] | None = None,
    social_security_benefits: list[SocialSecurityBenefit] | None = None,
    prior_year_tax: float = 0.0,
    prior_year_agi: float = 0.0,
    tax_year: int = TAX_YEAR,
) -> TaxResult:
    """Compute full federal + state tax return.

    Args:
        tax_year: Tax year for computation (2024 or 2025). Determines which
                  inflation-adjusted constants (brackets, deductions, etc.) are used.
    """

    if filing_status not in FILING_STATUSES:
        raise ValueError(f"Invalid filing status: {filing_status}")
    if tax_year not in SUPPORTED_TAX_YEARS:
        raise ValueError(f"Unsupported tax year: {tax_year}. Supported: {sorted(SUPPORTED_TAX_YEARS)}")

    # Load year-specific constants
    c = get_year_config(tax_year)

    businesses = businesses or []
    dependents = dependents or []

    # Derive dependent counts from structured records (or fall back to integer)
    if dependents:
        num_dependents = len(dependents)
        num_ctc_children = sum(1 for d in dependents if d.qualifies_ctc(tax_year))
        num_eitc_children = sum(1 for d in dependents if d.qualifies_eitc(tax_year))
        num_cdcc_dependents = sum(1 for d in dependents if d.qualifies_cdcc(tax_year))
    else:
        # Backward compat: no structured dependents, use num_dependents for all
        num_ctc_children = num_dependents
        num_eitc_children = num_dependents
        num_cdcc_dependents = 0  # Can't determine without age info

    result = TaxResult(
        draft_id=uuid.uuid4().hex[:12],
        filing_status=filing_status,
        tax_year=tax_year,
        filer=filer,
        spouse=spouse,
        num_dependents=num_dependents,
        dependents=dependents,
        num_ctc_children=num_ctc_children,
        num_eitc_children=num_eitc_children,
        num_cdcc_dependents=num_cdcc_dependents,
        w2s=w2s,
        businesses=businesses,
        capital_transactions=additional.capital_transactions,
    )

    # =======================================================================
    # INCOME (Form 1040 Lines 1-9)
    # =======================================================================

    # Line 1a: Wages from all W-2s
    result.line_1a_wages = sum(w.wages for w in w2s)

    # Line 2b: Taxable interest (1099-INT + other)
    result.line_2b_taxable_interest = additional.other_interest

    # Line 3a/3b: Dividends
    result.line_3a_qualified_dividends = additional.qualified_dividends
    result.line_3b_ordinary_dividends = additional.ordinary_dividends

    # Schedule D: Capital gains
    short_term = sum(t.gain_loss for t in additional.capital_transactions if not t.is_long_term)
    long_term = sum(t.gain_loss for t in additional.capital_transactions if t.is_long_term)
    result.sched_d_short_term_gain = short_term
    result.sched_d_long_term_gain = long_term
    result.sched_d_net_gain = short_term + long_term
    result.line_7_capital_gain_loss = result.sched_d_net_gain

    # Line 8: Other income
    result.line_8_other_income = additional.other_income

    # Schedule C: Business income
    result.sched_c_businesses = []
    for biz in businesses:
        result.sched_c_businesses.append({
            "name": biz.business_name,
            "type": biz.business_type,
            "gross_receipts": biz.gross_receipts,
            "cogs": biz.cost_of_goods_sold,
            "gross_profit": biz.gross_profit,
            "expenses": biz.total_expenses,
            "net_profit": biz.net_profit,
        })
    result.sched_c_total_profit = sum(b.net_profit for b in businesses)
    result.line_8a_business_income = result.sched_c_total_profit

    # Schedule E: Rental income (passive activity)
    rental_properties = rental_properties or []
    if rental_properties:
        for prop in rental_properties:
            result.sched_e_properties.append({
                "address": prop.property_address,
                "rental_days": prop.rental_days,
                "personal_use_days": prop.personal_use_days,
                "gross_rents": prop.gross_rents,
                "total_expenses": prop.total_expenses,
                "net_income": prop.net_income,
            })
        result.sched_e_total_income = sum(p.gross_rents for p in rental_properties)
        result.sched_e_total_expenses = sum(p.total_expenses for p in rental_properties)
        raw_net = sum(p.net_income for p in rental_properties)

        if raw_net >= 0:
            # Net rental income — fully included
            result.sched_e_net_income = raw_net
        else:
            # Net rental loss — passive activity loss rules (IRC §469)
            # Active participation: up to $25K loss allowed, phased out for AGI $100K-$150K
            # Use a preliminary AGI estimate (income before rental loss adjustment)
            prelim_agi = (
                result.line_1a_wages + result.line_2b_taxable_interest
                + result.line_3b_ordinary_dividends + result.line_7_capital_gain_loss
                + result.line_8_other_income + result.line_8a_business_income
            )
            if prelim_agi <= c.RENTAL_LOSS_PHASEOUT_START:
                allowed_loss = min(abs(raw_net), c.RENTAL_LOSS_LIMIT)
            elif prelim_agi >= c.RENTAL_LOSS_PHASEOUT_END:
                allowed_loss = 0.0
            else:
                # Phase out: reduce $25K by 50% of excess over $100K
                reduction = (prelim_agi - c.RENTAL_LOSS_PHASEOUT_START) * 0.50
                allowed_loss = max(0, min(abs(raw_net), c.RENTAL_LOSS_LIMIT - reduction))
            result.sched_e_net_income = -allowed_loss

    # =======================================================================
    # CRYPTO / FORM 8949 — Digital Asset Transactions
    # =======================================================================
    crypto_transactions = crypto_transactions or []
    if crypto_transactions:
        result.crypto_transactions_count = len(crypto_transactions)
        for ct in crypto_transactions:
            result.crypto_total_proceeds += ct.proceeds
            result.crypto_total_basis += ct.cost_basis
            result.crypto_wash_sale_disallowed += ct.wash_sale_loss_disallowed

            adj_gain = ct.adjusted_gain_loss
            if ct.is_long_term:
                result.crypto_long_term_gain += adj_gain
            else:
                result.crypto_short_term_gain += adj_gain

            # Convert to CapitalTransaction for Schedule D
            cap_txn = ct.to_capital_transaction()
            additional.capital_transactions.append(cap_txn)

        # Recompute Schedule D totals with crypto included
        short_term = sum(t.gain_loss for t in additional.capital_transactions if not t.is_long_term)
        long_term = sum(t.gain_loss for t in additional.capital_transactions if t.is_long_term)
        result.sched_d_short_term_gain = short_term
        result.sched_d_long_term_gain = long_term
        result.sched_d_net_gain = short_term + long_term
        result.line_7_capital_gain_loss = result.sched_d_net_gain

    # =======================================================================
    # FORM 1099-R — Retirement Distributions
    # =======================================================================
    retirement_distributions = retirement_distributions or []
    if retirement_distributions:
        result.retirement_distributions_count = len(retirement_distributions)
        for dist in retirement_distributions:
            result.retirement_gross_distributions += dist.gross_distribution
            result.retirement_taxable_amount += dist.taxable
            result.retirement_federal_withheld += dist.federal_withheld
            result.retirement_early_penalty += dist.early_withdrawal_penalty
        # Taxable distributions → Line 4b/5b (treated as other income)
        result.line_8_other_income += result.retirement_taxable_amount
        # Withholding is added in the PAYMENTS section below

    # IRA contributions — above-the-line deduction
    ira_contributions = ira_contributions or []
    if ira_contributions:
        total_ira = 0.0
        for contrib in ira_contributions:
            limit = c.IRA_CONTRIBUTION_LIMIT
            if contrib.age_50_plus:
                limit += c.IRA_CATCHUP
            total_ira += min(contrib.contribution_amount, limit)
        result.ira_deduction = total_ira

    # =======================================================================
    # FORM 4562 — Depreciation (MACRS, Section 179, Bonus)
    # =======================================================================
    depreciable_assets = depreciable_assets or []
    if depreciable_assets:
        result.depreciation_assets_count = len(depreciable_assets)

        # Section 179 limit enforcement (aggregate across all assets)
        total_s179_elected = sum(a.section_179_elected for a in depreciable_assets if not a.is_real_property)
        s179_limit = c.SECTION_179_LIMIT
        s179_phaseout_start = c.SECTION_179_PHASEOUT_START
        total_asset_cost = sum(a.cost * min(a.business_use_pct, 100.0) / 100.0 for a in depreciable_assets)

        # Phaseout: reduce limit dollar-for-dollar above phaseout start
        if total_asset_cost > s179_phaseout_start:
            s179_limit = max(0, s179_limit - (total_asset_cost - s179_phaseout_start))

        # Cap total Section 179 at the limit
        s179_ratio = min(1.0, s179_limit / total_s179_elected) if total_s179_elected > 0 else 1.0

        for asset in depreciable_assets:
            # Scale down Section 179 if over limit
            if s179_ratio < 1.0 and asset.section_179_elected > 0:
                asset.section_179_elected = round(asset.section_179_elected * s179_ratio, 2)

            depr = asset.compute_depreciation(tax_year)

            # Track components
            biz_pct = min(asset.business_use_pct, 100.0) / 100.0
            basis = asset.cost * biz_pct
            s179_part = min(asset.section_179_elected, basis) if asset.recovery_year == 1 and not asset.is_real_property else 0.0
            remaining = basis - s179_part
            bonus_part = 0.0
            if asset.recovery_year == 1 and asset.bonus_depreciation and not asset.is_real_property:
                pis_year = tax_year
                if asset.date_placed_in_service:
                    try:
                        pis_year = int(asset.date_placed_in_service.split("-")[0])
                    except (ValueError, IndexError):
                        pass
                bonus_rate = c.BONUS_DEPRECIATION_RATES.get(pis_year, 0.0)
                bonus_part = remaining * bonus_rate
            macrs_part = depr - s179_part - bonus_part

            result.depreciation_section_179 += s179_part
            result.depreciation_bonus += bonus_part
            result.depreciation_macrs += max(0, macrs_part)
            result.depreciation_total += depr

            if asset.asset_use == "rental":
                result.depreciation_rental += depr
            else:
                result.depreciation_business += depr

        # Business depreciation reduces Schedule C profit
        if result.depreciation_business > 0:
            result.sched_c_total_profit -= result.depreciation_business
            result.line_8a_business_income = result.sched_c_total_profit

        # Rental depreciation reduces Schedule E net income
        if result.depreciation_rental > 0:
            result.sched_e_net_income -= result.depreciation_rental
            result.sched_e_total_expenses += result.depreciation_rental

    # =======================================================================
    # SCHEDULE K-1 — Passthrough Income
    # =======================================================================
    k1_incomes = k1_incomes or []
    if k1_incomes:
        for k1 in k1_incomes:
            result.k1_ordinary_income += k1.ordinary_income
            result.k1_rental_income += k1.rental_income
            result.k1_interest_income += k1.interest_income
            result.k1_dividend_income += k1.dividend_income
            result.k1_capital_gains += (k1.short_term_gain + k1.long_term_gain
                                        + k1.section_1231_gain)
            result.k1_guaranteed_payments += k1.guaranteed_payments
            result.k1_section_199a_income += k1.section_199a_income

        # K-1 income flows to various 1040 lines:
        # Ordinary income + guaranteed payments → Line 8 (other income / business)
        result.line_8_other_income += result.k1_ordinary_income + result.k1_guaranteed_payments
        # Interest → Line 2b
        result.line_2b_taxable_interest += result.k1_interest_income
        # Dividends → Line 3a/3b
        k1_qual_div = sum(k1.qualified_dividends for k1 in k1_incomes)
        result.line_3a_qualified_dividends += k1_qual_div
        result.line_3b_ordinary_dividends += result.k1_dividend_income
        # Capital gains → Schedule D
        k1_st = sum(k1.short_term_gain for k1 in k1_incomes)
        k1_lt = sum(k1.long_term_gain + k1.section_1231_gain for k1 in k1_incomes)
        result.sched_d_short_term_gain += k1_st
        result.sched_d_long_term_gain += k1_lt
        result.sched_d_net_gain += k1_st + k1_lt
        result.line_7_capital_gain_loss = result.sched_d_net_gain
        # Rental income → Schedule E
        result.sched_e_net_income += result.k1_rental_income

    # =======================================================================
    # SOCIAL SECURITY BENEFITS — IRC §86 Taxability
    # =======================================================================
    social_security_benefits = social_security_benefits or []
    if social_security_benefits:
        total_ss = sum(ss.gross_benefits for ss in social_security_benefits)
        ss_withheld = sum(ss.federal_withheld for ss in social_security_benefits)
        result.ss_gross_benefits = total_ss
        result.ss_federal_withheld = ss_withheld

        # Provisional income = other income (before SS) + 50% of SS benefits
        other_income = (
            result.line_1a_wages
            + result.line_2b_taxable_interest
            + result.line_3b_ordinary_dividends
            + result.line_7_capital_gain_loss
            + result.line_8_other_income
            + result.line_8a_business_income
            + result.sched_e_net_income
        )
        provisional = other_income + (total_ss * 0.5)
        result.ss_provisional_income = provisional

        base_threshold = c.SS_TAXABLE_BASE_THRESHOLD.get(filing_status, 25_000)
        upper_threshold = c.SS_TAXABLE_UPPER_THRESHOLD.get(filing_status, 34_000)

        if provisional <= base_threshold:
            # Below base threshold: 0% taxable
            taxable_ss = 0.0
        elif provisional <= upper_threshold:
            # Between base and upper: up to 50% of benefits
            taxable_ss = min(total_ss * 0.5, (provisional - base_threshold) * 0.5)
        else:
            # Above upper threshold: up to 85% of benefits
            # Step 1: 50% amount (capped at the base-to-upper range)
            fifty_pct = min(total_ss * 0.5, (upper_threshold - base_threshold) * 0.5)
            # Step 2: 85% of excess above upper
            eighty_five_pct = (provisional - upper_threshold) * 0.85
            # Total: lesser of (Step1 + Step2) or 85% of total benefits
            taxable_ss = min(fifty_pct + eighty_five_pct, total_ss * c.SS_TAXABLE_MAX_PCT)

        result.ss_taxable_amount = round(taxable_ss, 2)
        result.ss_taxable_pct = round(taxable_ss / total_ss, 4) if total_ss > 0 else 0.0

    # Line 9: Total income (includes taxable SS on line 6b)
    result.line_9_total_income = (
        result.line_1a_wages
        + result.line_2b_taxable_interest
        + result.line_3b_ordinary_dividends
        + result.line_7_capital_gain_loss
        + result.line_8_other_income
        + result.line_8a_business_income
        + result.sched_e_net_income
        + result.ss_taxable_amount
    )

    # =======================================================================
    # SCHEDULE SE — Self-Employment Tax
    # =======================================================================

    # SE income includes Schedule C profit + K-1 partnership guaranteed payments
    se_income = result.sched_c_total_profit + result.k1_guaranteed_payments
    if se_income > 0:
        # Net SE earnings = 92.35% of net profit
        result.sched_se_net_earnings = se_income
        result.sched_se_taxable = result.sched_se_net_earnings * c.SE_INCOME_FACTOR

        # SS portion: 12.4% on earnings up to wage base (minus W-2 SS wages)
        w2_ss_wages = sum(w.ss_wages for w in w2s)
        ss_room = max(0, c.SS_WAGE_BASE - w2_ss_wages)
        ss_taxable = min(result.sched_se_taxable, ss_room)
        result.sched_se_ss_tax = ss_taxable * c.SE_SS_RATE

        # Medicare portion: 2.9% on all SE earnings (no cap)
        result.sched_se_medicare_tax = result.sched_se_taxable * c.SE_MEDICARE_RATE

        result.sched_se_total = result.sched_se_ss_tax + result.sched_se_medicare_tax
        result.se_tax = result.sched_se_total

    # =======================================================================
    # ADJUSTMENTS (Line 10-11)
    # =======================================================================

    adjustments = 0.0
    # Student loan interest deduction (above-the-line, max $2,500)
    adjustments += min(deductions.student_loan_interest, c.STUDENT_LOAN_INTEREST_MAX)
    # 50% of SE tax is deductible above-the-line
    result.se_tax_deduction = result.se_tax * 0.5
    adjustments += result.se_tax_deduction

    # HSA deduction (above-the-line) — IRC §223 / Form 8889
    hsa_contributions = hsa_contributions or []
    if hsa_contributions:
        total_personal = 0.0
        total_employer = 0.0
        total_limit = 0.0
        for hsa in hsa_contributions:
            if hsa.coverage_type == "family":
                limit = c.HSA_LIMIT_FAMILY
            else:
                limit = c.HSA_LIMIT_SELF
            if hsa.age_55_plus:
                limit += c.HSA_CATCHUP
            total_limit += limit
            total_personal += hsa.contribution_amount
            total_employer += hsa.employer_contributions
            # Deductible = personal contributions, capped at (limit - employer)
            deductible_room = max(0, limit - hsa.employer_contributions)
            total_hsa_ded = min(hsa.contribution_amount, deductible_room)
        # Recompute deduction properly across all contributions
        total_deductible = 0.0
        total_excess = 0.0
        for hsa in hsa_contributions:
            if hsa.coverage_type == "family":
                limit = c.HSA_LIMIT_FAMILY
            else:
                limit = c.HSA_LIMIT_SELF
            if hsa.age_55_plus:
                limit += c.HSA_CATCHUP
            room = max(0, limit - hsa.employer_contributions)
            allowed = min(hsa.contribution_amount, room)
            total_deductible += allowed
            # Excess = personal + employer over limit
            total_contrib = hsa.contribution_amount + hsa.employer_contributions
            if total_contrib > limit:
                total_excess += total_contrib - limit
        result.hsa_deduction = total_deductible
        result.form_8889_contributions = total_personal
        result.form_8889_employer = total_employer
        result.form_8889_limit = total_limit
        result.form_8889_deduction = total_deductible
        result.form_8889_excess = total_excess
        adjustments += result.hsa_deduction

    # IRA above-the-line deduction
    if result.ira_deduction > 0:
        adjustments += result.ira_deduction

    result.line_10_adjustments = adjustments

    # Line 11: AGI
    result.line_11_agi = max(0, result.line_9_total_income - result.line_10_adjustments)

    # =======================================================================
    # SCHEDULE A — Itemized Deductions
    # =======================================================================

    # Medical (exceeding 7.5% of AGI)
    medical_floor = result.line_11_agi * c.MEDICAL_AGI_THRESHOLD
    result.sched_a_medical = max(0, deductions.medical_expenses - medical_floor)

    # SALT (capped at $10k or $5k MFS)
    salt_cap = c.SALT_CAP_MFS if filing_status == MFS else c.SALT_CAP
    raw_salt = deductions.property_tax + deductions.state_income_tax_paid
    result.sched_a_salt = min(raw_salt, salt_cap)

    # Mortgage interest
    result.sched_a_mortgage_interest = deductions.mortgage_interest

    # Charitable contributions
    result.sched_a_charitable = deductions.charitable_cash + deductions.charitable_noncash

    result.sched_a_total = (
        result.sched_a_medical
        + result.sched_a_salt
        + result.sched_a_mortgage_interest
        + result.sched_a_charitable
    )
    result.itemized_total = result.sched_a_total

    # =======================================================================
    # DEDUCTION CHOICE (Line 12-14)
    # =======================================================================

    result.standard_deduction = c.STANDARD_DEDUCTION[filing_status]

    if result.itemized_total > result.standard_deduction:
        result.deduction_type = "itemized"
        result.line_13_deduction = result.itemized_total
    else:
        result.deduction_type = "standard"
        result.line_13_deduction = result.standard_deduction

    # =======================================================================
    # TAXABLE INCOME (Line 15)
    # =======================================================================

    # QBI deduction (Section 199A) — 20% of qualified business income
    # Includes Schedule C profit + K-1 §199A income
    total_qbi = result.sched_c_total_profit + result.k1_section_199a_income
    if total_qbi > 0:
        qbi_limit = c.QBI_TAXABLE_INCOME_LIMIT[filing_status]
        qbi_range = c.QBI_PHASEOUT_RANGE[filing_status]
        tentative_taxable = result.line_11_agi - result.line_13_deduction
        full_qbi = total_qbi * c.QBI_DEDUCTION_RATE

        if tentative_taxable <= qbi_limit:
            # Below threshold: full 20% deduction
            result.qbi_deduction = full_qbi
        elif tentative_taxable >= qbi_limit + qbi_range:
            # Above phase-out: limited to greater of 50% W-2 wages or 25% W-2 wages + 2.5% UBIA
            # For Schedule C filers (no W-2 wages from own business), this is typically $0
            # unless they have W-2 employees in their business
            w2_wages_paid = 0.0  # Self-employed Schedule C filers have no W-2 wages to themselves
            result.qbi_deduction = max(w2_wages_paid * 0.50, w2_wages_paid * 0.25)
        else:
            # In phase-out range: reduce excess of full QBI over W-2 limit
            w2_wages_paid = 0.0
            w2_limited = max(w2_wages_paid * 0.50, w2_wages_paid * 0.25)
            excess = max(0, full_qbi - w2_limited)
            phase_fraction = (tentative_taxable - qbi_limit) / qbi_range
            reduction = excess * phase_fraction
            result.qbi_deduction = max(0, full_qbi - reduction)

        # QBI deduction can't exceed taxable income
        result.qbi_deduction = min(result.qbi_deduction, max(0, result.line_11_agi - result.line_13_deduction))

    result.line_15_taxable_income = max(0, result.line_11_agi - result.line_13_deduction - result.qbi_deduction)

    # =======================================================================
    # TAX COMPUTATION (Line 16)
    # =======================================================================

    # Preferential income = qualified dividends + net LTCG (if positive)
    preferential_income = result.line_3a_qualified_dividends + max(0, result.sched_d_long_term_gain)

    if preferential_income > 0 and result.line_15_taxable_income > 0:
        # Split: ordinary income taxed at brackets, preferential at LTCG rates
        ordinary_taxable = max(0, result.line_15_taxable_income - preferential_income)
        ordinary_tax = compute_bracket_tax(ordinary_taxable, c.FEDERAL_BRACKETS[filing_status])

        # LTCG tax on the preferential portion
        cap_gains_tax = compute_ltcg_tax(
            result.line_15_taxable_income,
            min(preferential_income, result.line_15_taxable_income),
            c.LTCG_BRACKETS[filing_status],
        )

        result.line_16_tax = ordinary_tax
        result.capital_gains_tax = cap_gains_tax
    else:
        # All ordinary income
        result.line_16_tax = compute_bracket_tax(
            result.line_15_taxable_income, c.FEDERAL_BRACKETS[filing_status]
        )
        result.capital_gains_tax = 0.0

    # Short-term gains are taxed as ordinary income (already included in brackets above)
    # If there were short-term gains, they're part of taxable_income and taxed at ordinary rates

    # =======================================================================
    # NET INVESTMENT INCOME TAX (NIIT) — 3.8% surtax
    # =======================================================================

    niit_threshold = c.NIIT_THRESHOLD[filing_status]
    if result.line_11_agi > niit_threshold:
        # Net investment income = interest + dividends + capital gains + other investment income
        net_investment_income = (
            result.line_2b_taxable_interest
            + result.line_3b_ordinary_dividends
            + max(0, result.sched_d_net_gain)
        )
        # NIIT is 3.8% on the LESSER of net investment income OR AGI exceeding threshold
        niit_base = min(net_investment_income, result.line_11_agi - niit_threshold)
        result.niit = max(0, niit_base * c.NIIT_RATE)

    # =======================================================================
    # ADDITIONAL MEDICARE TAX — 0.9% on earnings above threshold
    # =======================================================================

    amt_threshold = c.ADDITIONAL_MEDICARE_THRESHOLD[filing_status]
    total_medicare_wages = sum(w.medicare_wages for w in w2s) + result.sched_se_taxable
    if total_medicare_wages > amt_threshold:
        # 0.9% on the excess — W-2 withholding already covers base Medicare
        result.additional_medicare_tax = (total_medicare_wages - amt_threshold) * c.ADDITIONAL_MEDICARE_RATE

    # =======================================================================
    # ALTERNATIVE MINIMUM TAX — Form 6251
    # =======================================================================

    # AMT income starts with taxable income + add-back deductions
    # Simplified: add back SALT deduction (the main AMT adjustment for most filers)
    amt_income = result.line_15_taxable_income + result.sched_a_salt
    result.amt_income = amt_income

    # AMT exemption with phase-out (25% of excess over phaseout start)
    exemption_base = c.AMT_EXEMPTION[filing_status]
    phaseout_start = c.AMT_PHASEOUT_START[filing_status]
    if amt_income > phaseout_start:
        exemption_reduction = (amt_income - phaseout_start) * 0.25
        exemption = max(0, exemption_base - exemption_reduction)
    else:
        exemption = exemption_base
    result.amt_exemption = exemption

    amt_taxable = max(0, amt_income - exemption)
    rate_break = c.AMT_RATE_BREAK[filing_status]
    if amt_taxable <= rate_break:
        tentative_min_tax = amt_taxable * c.AMT_RATE_LOW
    else:
        tentative_min_tax = rate_break * c.AMT_RATE_LOW + (amt_taxable - rate_break) * c.AMT_RATE_HIGH
    result.amt_tentative = tentative_min_tax

    # AMT = excess of tentative minimum tax over regular tax (before credits)
    regular_tax = result.line_16_tax + result.capital_gains_tax
    result.amt = max(0, tentative_min_tax - regular_tax)

    # =======================================================================
    # TOTAL TAX (Line 24)
    # =======================================================================

    result.line_24_total_tax = (
        result.line_16_tax
        + result.capital_gains_tax
        + result.se_tax
        + result.niit
        + result.additional_medicare_tax
        + result.amt
        + result.retirement_early_penalty
    )

    # =======================================================================
    # CREDITS
    # =======================================================================

    # Child Tax Credit (uses num_ctc_children — under 17 or disabled)
    if num_ctc_children > 0:
        ctc_base = num_ctc_children * c.CTC_PER_CHILD
        phaseout_start = c.CTC_PHASEOUT_START[filing_status]
        if result.line_11_agi > phaseout_start:
            reduction = ((result.line_11_agi - phaseout_start) // 1000) * c.CTC_PHASEOUT_RATE
            ctc_base = max(0, ctc_base - reduction)
        result.line_27_ctc = min(ctc_base, result.line_24_total_tax)
        result.line_24_total_tax -= result.line_27_ctc

    # Education Credits — Form 8863 (AOTC + LLC)
    education_expenses = education_expenses or []
    if education_expenses and filing_status != MFS:
        phaseout_range = c.EDUCATION_CREDIT_PHASEOUT[filing_status]
        phaseout_start_ed = phaseout_range[0]
        phaseout_end = phaseout_range[1]

        # Compute phaseout fraction
        if result.line_11_agi >= phaseout_end:
            ed_phaseout_frac = 0.0
        elif result.line_11_agi <= phaseout_start_ed:
            ed_phaseout_frac = 1.0
        else:
            ed_phaseout_frac = 1.0 - (result.line_11_agi - phaseout_start_ed) / (phaseout_end - phaseout_start_ed)

        total_aotc = 0.0
        total_llc = 0.0
        for exp in education_expenses:
            if exp.credit_type == "aotc":
                # AOTC: 100% of first $2,000 + 25% of next $2,000
                raw = min(exp.qualified_expenses, 2000) + max(0, min(exp.qualified_expenses - 2000, 2000)) * 0.25
                total_aotc += min(raw, c.AOTC_MAX)
            else:
                # LLC: 20% of up to $10,000 expenses
                total_llc += min(exp.qualified_expenses * c.LLC_EXPENSE_RATE, c.LLC_MAX)

        total_aotc *= ed_phaseout_frac
        total_llc *= ed_phaseout_frac

        # AOTC refundable portion (40%)
        result.education_credit_refundable = total_aotc * c.AOTC_REFUNDABLE_RATE
        nonrefundable_aotc = total_aotc - result.education_credit_refundable

        # Nonrefundable credits capped at tax liability
        nonrefundable_ed = min(nonrefundable_aotc + total_llc, result.line_24_total_tax)
        result.education_credit = nonrefundable_ed
        result.line_24_total_tax -= nonrefundable_ed

    # =======================================================================
    # CHILD AND DEPENDENT CARE CREDIT (CDCC) — Form 2441
    # =======================================================================

    dependent_care_expenses = dependent_care_expenses or []
    if dependent_care_expenses and result.line_24_total_tax > 0:
        num_care_dependents = len(dependent_care_expenses)
        expense_limit = c.CDCC_MAX_EXPENSES_TWO if num_care_dependents >= 2 else c.CDCC_MAX_EXPENSES_ONE
        total_care_expenses = sum(e.care_expenses for e in dependent_care_expenses)
        qualifying_expenses = min(total_care_expenses, expense_limit)

        # Expenses can't exceed earned income
        cdcc_earned = result.line_1a_wages + max(0, result.sched_se_taxable)
        qualifying_expenses = min(qualifying_expenses, cdcc_earned)

        # AGI-based credit rate: 35% at $15K AGI, decreasing 1% per $2K, floor 20%
        if result.line_11_agi <= c.CDCC_RATE_START_AGI:
            cdcc_rate = c.CDCC_MAX_RATE
        else:
            steps = int((result.line_11_agi - c.CDCC_RATE_START_AGI) / c.CDCC_RATE_STEP_AGI)
            cdcc_rate = max(c.CDCC_MIN_RATE, c.CDCC_MAX_RATE - steps * 0.01)

        cdcc_credit = qualifying_expenses * cdcc_rate
        # Nonrefundable: capped at remaining tax liability
        result.cdcc = min(cdcc_credit, result.line_24_total_tax)
        result.line_24_total_tax -= result.cdcc

    # =======================================================================
    # RETIREMENT SAVINGS CREDIT (SAVER'S CREDIT) — Form 8880
    # =======================================================================

    retirement_contributions = retirement_contributions or []
    if retirement_contributions and result.line_24_total_tax > 0:
        tiers = c.SAVERS_AGI_TIERS.get(filing_status, c.SAVERS_AGI_TIERS[SINGLE])
        agi = result.line_11_agi

        if agi <= tiers[0]:
            savers_rate = 0.50
        elif agi <= tiers[1]:
            savers_rate = 0.20
        elif agi <= tiers[2]:
            savers_rate = 0.10
        else:
            savers_rate = 0.0

        if savers_rate > 0:
            total_eligible = sum(
                min(rc.contribution_amount, c.SAVERS_MAX_CONTRIBUTION)
                for rc in retirement_contributions
            )
            savers_credit = total_eligible * savers_rate
            result.savers_credit = min(savers_credit, result.line_24_total_tax)
            result.line_24_total_tax -= result.savers_credit

    # =======================================================================
    # RESIDENTIAL ENERGY CREDITS — Form 5695
    # =======================================================================

    energy_improvements = energy_improvements or []
    if energy_improvements and result.line_24_total_tax > 0:
        total_clean = 0.0    # §25D: solar, wind, geothermal, battery
        total_envelope = 0.0 # §25C envelope: insulation, windows, doors, audit
        total_hp = 0.0       # §25C heat pump: heat pumps, biomass

        for ei in energy_improvements:
            # §25D: Residential Clean Energy (no annual cap, 30%)
            total_clean += (ei.solar_electric + ei.solar_water_heating +
                           ei.small_wind + ei.geothermal_heat_pump +
                           ei.battery_storage + ei.fuel_cell)
            # §25C: Energy Efficient Home Improvement
            total_envelope += (ei.insulation + ei.windows_skylights +
                              ei.exterior_doors + min(ei.energy_audit, 150))
            total_hp += ei.heat_pump + ei.biomass_stove

        # §25D credit: 30% of all clean energy costs (no annual limit)
        result.energy_clean_credit = total_clean * c.ENERGY_CLEAN_CREDIT_RATE

        # §25C credit: 30% with subcaps
        envelope_credit = min(total_envelope * c.ENERGY_IMPROVEMENT_CREDIT_RATE,
                             c.ENERGY_IMPROVEMENT_ENVELOPE_LIMIT)
        hp_credit = min(total_hp * c.ENERGY_IMPROVEMENT_CREDIT_RATE,
                       c.ENERGY_IMPROVEMENT_HP_LIMIT)
        result.energy_improvement_credit = min(envelope_credit + hp_credit,
                                               c.ENERGY_IMPROVEMENT_ANNUAL_LIMIT)

        # Total energy credit (nonrefundable — capped at tax liability)
        result.energy_total_credit = min(
            result.energy_clean_credit + result.energy_improvement_credit,
            result.line_24_total_tax
        )
        result.line_24_total_tax -= result.energy_total_credit

    # =======================================================================
    # EARNED INCOME TAX CREDIT (EITC) — Schedule EIC
    # =======================================================================

    # EITC: refundable credit for low-to-moderate income workers
    # MFS filers generally ineligible (we disallow here; IRS has limited exception)
    num_eitc_children = min(num_eitc_children, 3)  # 3+ treated as 3
    earned_income = result.line_1a_wages + max(0, result.sched_se_taxable)
    result.eitc_earned_income = earned_income

    # Investment income test: interest + dividends + capital gains
    investment_income = (
        result.line_2b_taxable_interest
        + result.line_3b_ordinary_dividends
        + max(0, result.sched_d_net_gain)
    )

    if filing_status != MFS and investment_income <= c.EITC_INVESTMENT_INCOME_LIMIT:
        phase_in_rate = c.EITC_PHASE_IN_RATE[num_eitc_children]
        phase_out_rate = c.EITC_PHASE_OUT_RATE[num_eitc_children]
        max_credit = c.EITC_MAX_CREDIT[num_eitc_children]
        earned_amount = c.EITC_EARNED_INCOME_AMOUNT[num_eitc_children]
        phaseout_start = c.EITC_PHASEOUT_START.get(filing_status, c.EITC_PHASEOUT_START[SINGLE])[num_eitc_children]

        # Phase-in: credit grows at phase_in_rate up to earned_amount
        credit_from_earned = min(earned_income * phase_in_rate, max_credit)

        # Phase-out: credit reduces at phase_out_rate above phaseout_start
        # Use the greater of AGI or earned income for phase-out test
        phaseout_income = max(result.line_11_agi, earned_income)
        if phaseout_income > phaseout_start:
            reduction = (phaseout_income - phaseout_start) * phase_out_rate
        else:
            reduction = 0.0

        result.eitc = max(0, credit_from_earned - reduction)

    # =======================================================================
    # PAYMENTS (Lines 25-33)
    # =======================================================================

    result.line_25_federal_withheld = sum(w.federal_withheld for w in w2s) + additional_withholding + result.retirement_federal_withheld + result.ss_federal_withheld
    result.estimated_payments = payments.estimated_federal
    result.line_33_total_payments = (
        result.line_25_federal_withheld
        + result.line_27_ctc
        + result.education_credit_refundable
        + result.eitc
        + result.estimated_payments
    )

    # =======================================================================
    # REFUND OR AMOUNT OWED (Lines 34/37)
    # =======================================================================

    diff = result.line_33_total_payments - result.line_24_total_tax
    if diff >= 0:
        result.line_34_overpaid = diff
        result.line_37_owed = 0.0
    else:
        result.line_34_overpaid = 0.0
        result.line_37_owed = abs(diff)

    # =======================================================================
    # ESTIMATED TAX PENALTY — Form 2210 (simplified short method)
    # =======================================================================

    # Penalty applies if: (1) owed >= $1,000 AND (2) withholding/credits < required payment
    # Required payment = lesser of 90% current year tax or 100% prior year tax (110% if high AGI)
    if result.line_37_owed >= c.ESTIMATED_TAX_PENALTY_THRESHOLD and prior_year_tax > 0:
        current_year_required = result.line_24_total_tax * c.ESTIMATED_TAX_SAFE_HARBOR_PCT

        high_agi_threshold = c.ESTIMATED_TAX_HIGH_AGI_THRESHOLD[filing_status]
        if prior_year_agi > high_agi_threshold:
            prior_year_required = prior_year_tax * c.ESTIMATED_TAX_PRIOR_YEAR_HIGH_AGI
        else:
            prior_year_required = prior_year_tax * c.ESTIMATED_TAX_PRIOR_YEAR_PCT

        result.estimated_tax_required = min(current_year_required, prior_year_required)

        # Total payments (withholding + estimated + refundable credits) vs required
        total_timely_payments = result.line_25_federal_withheld + result.estimated_payments
        if total_timely_payments < result.estimated_tax_required:
            # Underpayment = required - paid. Penalty = underpayment * rate * (time fraction)
            # Simplified: assume full year underpayment (4 quarters)
            underpayment = result.estimated_tax_required - total_timely_payments
            result.estimated_tax_penalty = underpayment * c.ESTIMATED_TAX_PENALTY_RATE
            result.line_37_owed += result.estimated_tax_penalty

    # =======================================================================
    # QUARTERLY ESTIMATED TAX PLANNER
    # =======================================================================

    # Calculate recommended quarterly payments for next year
    # Based on 100% of current year tax (110% if AGI > threshold)
    total_tax_liability = result.line_24_total_tax + result.estimated_tax_penalty
    total_withholding = result.line_25_federal_withheld

    if total_tax_liability > total_withholding:
        # Net tax after withholding
        net_tax = total_tax_liability - total_withholding
        high_agi_threshold = c.ESTIMATED_TAX_HIGH_AGI_THRESHOLD[filing_status]
        if result.line_11_agi > high_agi_threshold:
            safe_harbor_factor = c.ESTIMATED_TAX_PRIOR_YEAR_HIGH_AGI  # 110%
        else:
            safe_harbor_factor = c.ESTIMATED_TAX_PRIOR_YEAR_PCT  # 100%

        annual_required = net_tax * safe_harbor_factor
        quarterly = round(annual_required / 4, 2)
        result.quarterly_estimated_tax = quarterly
        result.quarterly_schedule = [
            {"quarter": "Q1", "due_date": f"{tax_year + 1}-04-15", "amount": quarterly},
            {"quarter": "Q2", "due_date": f"{tax_year + 1}-06-15", "amount": quarterly},
            {"quarter": "Q3", "due_date": f"{tax_year + 1}-09-15", "amount": quarterly},
            {"quarter": "Q4", "due_date": f"{tax_year + 2}-01-15", "amount": quarterly},
        ]

    # =======================================================================
    # SCHEDULE B
    # =======================================================================

    result.sched_b_interest_total = result.line_2b_taxable_interest
    result.sched_b_dividends_total = result.line_3b_ordinary_dividends

    # =======================================================================
    # STATE TAX COMPUTATION (multi-state support)
    # =======================================================================

    work_states = work_states or []
    residence_state = residence_state.upper() if residence_state else "IL"

    # Build per-state wage/withholding maps from W-2s
    w2_state_wages: dict[str, float] = {}
    w2_state_withheld: dict[str, float] = {}
    for w in w2s:
        # Use per-state breakdowns if available, otherwise default to residence state
        if hasattr(w, 'state_wage_infos') and w.state_wage_infos:
            for swi in w.state_wage_infos:
                st = swi.state.upper()
                w2_state_wages[st] = w2_state_wages.get(st, 0.0) + swi.state_wages
                w2_state_withheld[st] = w2_state_withheld.get(st, 0.0) + swi.state_withheld
        else:
            # Legacy: single state_wages/state_withheld → assign to residence state
            w2_state_wages[residence_state] = w2_state_wages.get(residence_state, 0.0) + w.state_wages
            w2_state_withheld[residence_state] = w2_state_withheld.get(residence_state, 0.0) + w.state_withheld

    num_exemptions = 1
    if filing_status == MFJ and spouse:
        num_exemptions = 2
    num_exemptions += num_dependents

    state_returns = compute_all_state_returns(
        residence_state=residence_state,
        work_states=work_states,
        filing_status=filing_status,
        federal_agi=result.line_11_agi,
        w2_state_wages=w2_state_wages,
        w2_state_withheld=w2_state_withheld,
        estimated_state_payments=payments.estimated_state,
        num_exemptions=num_exemptions,
        days_worked_by_state=days_worked_by_state,
        total_wages=result.line_1a_wages,
    )

    result.state_returns = state_returns
    result.residence_state = residence_state

    # Backward compatibility: map IL results to il_* fields
    il_result = None
    for sr in state_returns:
        if sr.state_code == "IL" and sr.return_type == "resident":
            il_result = sr
            break
    if il_result is None:
        # Check nonresident IL too
        for sr in state_returns:
            if sr.state_code == "IL":
                il_result = sr
                break

    if il_result:
        result.il_line_1_federal_agi = il_result.federal_agi
        result.il_line_3_additions = il_result.additions
        result.il_line_7_base_income = il_result.base_income
        result.il_line_9_exemptions = il_result.exemptions
        result.il_line_10_taxable = il_result.taxable_income
        result.il_line_11_tax = il_result.total_tax
        result.il_line_18_withheld = il_result.withholding
        result.il_estimated_payments = il_result.estimated_payments
        result.il_refund = il_result.refund
        result.il_owed = il_result.owed

    # =======================================================================
    # FORMS LIST
    # =======================================================================

    result.forms_generated = ["1040"]
    if businesses:
        result.forms_generated.append("Schedule C")
        result.forms_generated.append("Schedule SE")
    if result.deduction_type == "itemized":
        result.forms_generated.append("Schedule A")
    if result.sched_b_interest_total > 1500 or result.sched_b_dividends_total > 1500:
        result.forms_generated.append("Schedule B")
    if rental_properties:
        result.forms_generated.append("Schedule E")
    if additional.capital_transactions:
        result.forms_generated.append("Schedule D")
    if result.niit > 0 or result.additional_medicare_tax > 0 or result.se_tax > 0:
        result.forms_generated.append("Schedule 2")
    if result.additional_medicare_tax > 0:
        result.forms_generated.append("Form 8959")
    if result.niit > 0:
        result.forms_generated.append("Form 8960")
    if result.amt > 0:
        result.forms_generated.append("Form 6251")
    if result.education_credit > 0 or result.education_credit_refundable > 0:
        result.forms_generated.append("Form 8863")
    if result.eitc > 0:
        result.forms_generated.append("Schedule EIC")
    if result.cdcc > 0:
        result.forms_generated.append("Form 2441")
    if result.savers_credit > 0:
        result.forms_generated.append("Form 8880")
    if result.estimated_tax_penalty > 0:
        result.forms_generated.append("Form 2210")
    if result.hsa_deduction > 0 or result.form_8889_contributions > 0:
        result.forms_generated.append("Form 8889")
    if result.energy_total_credit > 0:
        result.forms_generated.append("Form 5695")
    if result.crypto_transactions_count > 0:
        result.forms_generated.append("Form 8949")
    if result.retirement_distributions_count > 0:
        result.forms_generated.append("1099-R Summary")
    if result.ss_gross_benefits > 0:
        result.forms_generated.append("SSA-1099 Summary")
    if result.depreciation_assets_count > 0:
        result.forms_generated.append("Form 4562")
    if k1_incomes:
        result.forms_generated.append("Schedule K-1 Summary")
    # State forms
    for sr in state_returns:
        if sr.form_name:
            result.forms_generated.append(sr.form_name)

    return result
