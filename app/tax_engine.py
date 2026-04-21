"""Tax computation engine — Federal 1040 + multi-state for tax year 2025."""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tax_config import *
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
class AdditionalIncome:
    other_interest: float = 0.0
    ordinary_dividends: float = 0.0
    qualified_dividends: float = 0.0
    capital_transactions: list = field(default_factory=list)
    other_income: float = 0.0
    other_income_description: str = ""


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
    line_24_total_tax: float = 0.0

    # Payments & credits
    line_25_federal_withheld: float = 0.0
    line_27_ctc: float = 0.0             # Child Tax Credit
    estimated_payments: float = 0.0
    line_33_total_payments: float = 0.0

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
            "residence_state": self.residence_state,
            "total_income": round(self.line_9_total_income, 2),
            "agi": round(self.line_11_agi, 2),
            "deduction_type": self.deduction_type,
            "deduction_amount": round(self.line_13_deduction, 2),
            "taxable_income": round(self.line_15_taxable_income, 2),
            "business_income": round(self.sched_c_total_profit, 2),
            "se_tax": round(self.se_tax, 2),
            "niit": round(self.niit, 2),
            "additional_medicare_tax": round(self.additional_medicare_tax, 2),
            "qbi_deduction": round(self.qbi_deduction, 2),
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
    businesses: list[BusinessIncome] | None = None,
    residence_state: str = "IL",
    work_states: list[str] | None = None,
    days_worked_by_state: dict[str, int] | None = None,
) -> TaxResult:
    """Compute full federal + state tax return."""

    if filing_status not in FILING_STATUSES:
        raise ValueError(f"Invalid filing status: {filing_status}")

    businesses = businesses or []

    result = TaxResult(
        draft_id=uuid.uuid4().hex[:12],
        filing_status=filing_status,
        tax_year=TAX_YEAR,
        filer=filer,
        spouse=spouse,
        num_dependents=num_dependents,
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

    # Line 9: Total income
    result.line_9_total_income = (
        result.line_1a_wages
        + result.line_2b_taxable_interest
        + result.line_3b_ordinary_dividends
        + result.line_7_capital_gain_loss
        + result.line_8_other_income
        + result.line_8a_business_income
    )

    # =======================================================================
    # SCHEDULE SE — Self-Employment Tax
    # =======================================================================

    if result.sched_c_total_profit > 0:
        # Net SE earnings = 92.35% of net profit
        result.sched_se_net_earnings = result.sched_c_total_profit
        result.sched_se_taxable = result.sched_se_net_earnings * SE_INCOME_FACTOR

        # SS portion: 12.4% on earnings up to wage base (minus W-2 SS wages)
        w2_ss_wages = sum(w.ss_wages for w in w2s)
        ss_room = max(0, SS_WAGE_BASE - w2_ss_wages)
        ss_taxable = min(result.sched_se_taxable, ss_room)
        result.sched_se_ss_tax = ss_taxable * SE_SS_RATE

        # Medicare portion: 2.9% on all SE earnings (no cap)
        result.sched_se_medicare_tax = result.sched_se_taxable * SE_MEDICARE_RATE

        result.sched_se_total = result.sched_se_ss_tax + result.sched_se_medicare_tax
        result.se_tax = result.sched_se_total

    # =======================================================================
    # ADJUSTMENTS (Line 10-11)
    # =======================================================================

    adjustments = 0.0
    # Student loan interest deduction (above-the-line, max $2,500)
    adjustments += min(deductions.student_loan_interest, STUDENT_LOAN_INTEREST_MAX)
    # 50% of SE tax is deductible above-the-line
    result.se_tax_deduction = result.se_tax * 0.5
    adjustments += result.se_tax_deduction
    result.line_10_adjustments = adjustments

    # Line 11: AGI
    result.line_11_agi = max(0, result.line_9_total_income - result.line_10_adjustments)

    # =======================================================================
    # SCHEDULE A — Itemized Deductions
    # =======================================================================

    # Medical (exceeding 7.5% of AGI)
    medical_floor = result.line_11_agi * MEDICAL_AGI_THRESHOLD
    result.sched_a_medical = max(0, deductions.medical_expenses - medical_floor)

    # SALT (capped at $10k or $5k MFS)
    salt_cap = SALT_CAP_MFS if filing_status == MFS else SALT_CAP
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

    result.standard_deduction = STANDARD_DEDUCTION[filing_status]

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
    if result.sched_c_total_profit > 0:
        qbi_limit = QBI_TAXABLE_INCOME_LIMIT[filing_status]
        tentative_taxable = result.line_11_agi - result.line_13_deduction
        if tentative_taxable <= qbi_limit:
            # Full 20% deduction below threshold
            result.qbi_deduction = result.sched_c_total_profit * QBI_DEDUCTION_RATE
        else:
            # Simplified: phase-out not implemented, cap at 20%
            result.qbi_deduction = result.sched_c_total_profit * QBI_DEDUCTION_RATE
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
        ordinary_tax = compute_bracket_tax(ordinary_taxable, FEDERAL_BRACKETS[filing_status])

        # LTCG tax on the preferential portion
        cap_gains_tax = compute_ltcg_tax(
            result.line_15_taxable_income,
            min(preferential_income, result.line_15_taxable_income),
            LTCG_BRACKETS[filing_status],
        )

        result.line_16_tax = ordinary_tax
        result.capital_gains_tax = cap_gains_tax
    else:
        # All ordinary income
        result.line_16_tax = compute_bracket_tax(
            result.line_15_taxable_income, FEDERAL_BRACKETS[filing_status]
        )
        result.capital_gains_tax = 0.0

    # Short-term gains are taxed as ordinary income (already included in brackets above)
    # If there were short-term gains, they're part of taxable_income and taxed at ordinary rates

    # =======================================================================
    # NET INVESTMENT INCOME TAX (NIIT) — 3.8% surtax
    # =======================================================================

    niit_threshold = NIIT_THRESHOLD[filing_status]
    if result.line_11_agi > niit_threshold:
        # Net investment income = interest + dividends + capital gains + other investment income
        net_investment_income = (
            result.line_2b_taxable_interest
            + result.line_3b_ordinary_dividends
            + max(0, result.sched_d_net_gain)
        )
        # NIIT is 3.8% on the LESSER of net investment income OR AGI exceeding threshold
        niit_base = min(net_investment_income, result.line_11_agi - niit_threshold)
        result.niit = max(0, niit_base * NIIT_RATE)

    # =======================================================================
    # ADDITIONAL MEDICARE TAX — 0.9% on earnings above threshold
    # =======================================================================

    amt_threshold = ADDITIONAL_MEDICARE_THRESHOLD[filing_status]
    total_medicare_wages = sum(w.medicare_wages for w in w2s) + result.sched_se_taxable
    if total_medicare_wages > amt_threshold:
        # 0.9% on the excess — W-2 withholding already covers base Medicare
        result.additional_medicare_tax = (total_medicare_wages - amt_threshold) * ADDITIONAL_MEDICARE_RATE

    # =======================================================================
    # TOTAL TAX (Line 24)
    # =======================================================================

    result.line_24_total_tax = (
        result.line_16_tax
        + result.capital_gains_tax
        + result.se_tax
        + result.niit
        + result.additional_medicare_tax
    )

    # =======================================================================
    # CREDITS
    # =======================================================================

    # Child Tax Credit
    if num_dependents > 0:
        ctc_base = num_dependents * CTC_PER_CHILD
        phaseout_start = CTC_PHASEOUT_START[filing_status]
        if result.line_11_agi > phaseout_start:
            reduction = ((result.line_11_agi - phaseout_start) // 1000) * CTC_PHASEOUT_RATE
            ctc_base = max(0, ctc_base - reduction)
        result.line_27_ctc = min(ctc_base, result.line_24_total_tax)
        result.line_24_total_tax -= result.line_27_ctc

    # =======================================================================
    # PAYMENTS (Lines 25-33)
    # =======================================================================

    result.line_25_federal_withheld = sum(w.federal_withheld for w in w2s)
    result.estimated_payments = payments.estimated_federal
    result.line_33_total_payments = (
        result.line_25_federal_withheld
        + result.line_27_ctc
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
    if additional.capital_transactions:
        result.forms_generated.append("Schedule D")
    if result.niit > 0 or result.additional_medicare_tax > 0 or result.se_tax > 0:
        result.forms_generated.append("Schedule 2")
    if result.additional_medicare_tax > 0:
        result.forms_generated.append("Form 8959")
    if result.niit > 0:
        result.forms_generated.append("Form 8960")
    # State forms
    for sr in state_returns:
        if sr.form_name:
            result.forms_generated.append(sr.form_name)

    return result
