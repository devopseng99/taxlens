"""Tax draft API routes — create, view, and download completed tax form PDFs."""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from tax_engine import (
    PersonInfo, W2Income, CapitalTransaction, BusinessIncome, Deductions,
    AdditionalIncome, DividendIncome, Payments, TaxResult, Dependent,
    RentalProperty, HSAContribution,
    compute_tax, parse_w2_from_ocr, parse_1099int_from_ocr,
    parse_1099div_from_ocr, parse_1099nec_from_ocr, parse_1098_from_ocr,
    parse_1099b_from_structured,
)
from pdf_generator import generate_all_pdfs
from audit_risk import assess_audit_risk
from prior_year_import import extract_from_fillable_pdf, PriorYearData
from auth import require_auth

router = APIRouter(prefix="/tax-draft", tags=["Tax Drafts"])

STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------
class PersonInput(BaseModel):
    first_name: str = ""
    last_name: str = ""
    ssn: str = "XXX-XX-XXXX"
    address_street: str = ""
    address_city: str = ""
    address_state: str = "IL"
    address_zip: str = ""


class DependentInput(BaseModel):
    first_name: str = ""
    last_name: str = ""
    ssn: str = "XXX-XX-XXXX"
    date_of_birth: str = Field(default="", description="YYYY-MM-DD format")
    relationship: str = Field(default="", description="son, daughter, stepchild, foster, sibling, other")
    months_lived_with: int = Field(default=12, description="Months lived with filer (EITC requires > 6)")
    is_disabled: bool = False
    is_student: bool = False


class CapitalTransactionInput(BaseModel):
    description: str = "Stock/Crypto sale"
    date_acquired: str = "Various"
    date_sold: str = "2025"
    proceeds: float = 0.0
    cost_basis: float = 0.0
    is_long_term: bool = False


class AdditionalIncomeInput(BaseModel):
    other_interest: float = 0.0
    ordinary_dividends: float = 0.0
    qualified_dividends: float = 0.0
    capital_transactions: list[CapitalTransactionInput] = []
    other_income: float = 0.0
    other_income_description: str = ""


class DeductionsInput(BaseModel):
    mortgage_interest: float = 0.0
    property_tax: float = 0.0
    state_income_tax_paid: float = 0.0
    charitable_cash: float = 0.0
    charitable_noncash: float = 0.0
    medical_expenses: float = 0.0
    student_loan_interest: float = 0.0


class BusinessIncomeInput(BaseModel):
    business_name: str = "Self-Employment"
    business_type: str = ""
    ein: str = ""
    gross_receipts: float = 0.0
    cost_of_goods_sold: float = 0.0
    advertising: float = 0.0
    car_expenses: float = 0.0
    insurance: float = 0.0
    office_expense: float = 0.0
    rent: float = 0.0
    supplies: float = 0.0
    utilities: float = 0.0
    home_office_sqft: float = 0.0
    home_total_sqft: float = 0.0
    home_expenses: float = 0.0
    other_expenses: float = 0.0
    other_expenses_description: str = ""


class BrokerageTransactionInput(BaseModel):
    """Structured 1099-B transaction (JSON import, not OCR)."""
    description: str = "Security Sale"
    date_acquired: str = "Various"
    date_sold: str = "2025"
    proceeds: float = 0.0
    cost_basis: float = 0.0
    is_long_term: bool = False


class RentalPropertyInput(BaseModel):
    """Schedule E — Rental real estate income/expenses."""
    property_address: str = ""
    rental_days: int = 365
    personal_use_days: int = 0
    gross_rents: float = 0.0
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


class HSAContributionInput(BaseModel):
    """Health Savings Account contribution (Form 8889)."""
    contributor: str = "filer"
    contribution_amount: float = 0.0
    employer_contributions: float = 0.0
    coverage_type: str = "self"
    age_55_plus: bool = False


class PaymentsInput(BaseModel):
    estimated_federal: float = 0.0
    estimated_state: float = 0.0


class TaxDraftRequest(BaseModel):
    filing_status: str = Field(..., description="single, mfj, hoh, or mfs")
    username: str = Field(..., description="TaxLens username (for document lookup)")
    tax_year: int = Field(default=2025, description="Tax year (2024 or 2025)")
    filer: PersonInput = PersonInput()
    spouse: Optional[PersonInput] = None
    num_dependents: int = Field(default=0, description="Number of dependents (backward compat — prefer 'dependents' list)")
    dependents: list[DependentInput] = Field(default=[], description="Structured dependent records with DOB for credit eligibility")

    # Multi-state support
    residence_state: str = Field(default="IL", description="Two-letter state code where filer lives")
    work_states: list[str] = Field(default=[], description="Additional states where filer earned income")
    days_worked_by_state: dict[str, int] = Field(default={}, description="Manual allocation: {state: days_worked}")

    # OCR document references — pull W-2/1099 data from existing TaxLens documents
    w2_proc_ids: list[str] = Field(default=[], description="proc_ids of uploaded W-2s with OCR results")
    interest_1099_proc_ids: list[str] = Field(default=[], description="proc_ids of uploaded 1099-INTs with OCR")
    div_1099_proc_ids: list[str] = Field(default=[], description="proc_ids of uploaded 1099-DIVs with OCR")
    nec_1099_proc_ids: list[str] = Field(default=[], description="proc_ids of uploaded 1099-NECs with OCR")
    mortgage_1098_proc_ids: list[str] = Field(default=[], description="proc_ids of uploaded 1098s with OCR")

    # Structured brokerage data (1099-B — JSON import, not OCR)
    brokerage_transactions: list[BrokerageTransactionInput] = Field(default=[], description="Structured 1099-B transactions")

    # Plaid connected accounts — pull investment data from synced Plaid items
    plaid_item_ids: list[str] = Field(default=[], description="Plaid item_ids to include (must be synced first)")

    # Business income (Schedule C)
    businesses: list[BusinessIncomeInput] = Field(default=[], description="Self-employment / business income")

    # Rental income (Schedule E)
    rental_properties: list[RentalPropertyInput] = Field(default=[], description="Rental real estate properties")

    # HSA contributions
    hsa_contributions: list[HSAContributionInput] = Field(default=[], description="HSA contributions for above-the-line deduction")

    # Manual income entries (in addition to OCR-extracted data)
    additional_income: AdditionalIncomeInput = AdditionalIncomeInput()
    deductions: DeductionsInput = DeductionsInput()
    payments: PaymentsInput = PaymentsInput()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_ocr_result(username: str, proc_id: str) -> dict:
    """Load OCR result from TaxLens storage."""
    doc_dir = STORAGE_ROOT / username.replace("/", "_").replace("..", "_") / proc_id
    ocr_file = doc_dir / "ocr_result.json"
    if not ocr_file.exists():
        raise HTTPException(400, f"No OCR result for {proc_id}. Run /analyze first.")
    return json.loads(ocr_file.read_text())


def get_draft_dir(username: str, draft_id: str) -> Path:
    return STORAGE_ROOT / username.replace("/", "_").replace("..", "_") / "drafts" / draft_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("")
async def create_tax_draft(req: TaxDraftRequest, _auth: str = Depends(require_auth)):
    """Create a complete tax draft from OCR data + supplemental info.

    Computes federal 1040 + state returns, generates PDF forms,
    and stores everything on the PVC for private access.
    """

    # --- Parse W-2s from OCR ---
    w2s = []
    for proc_id in req.w2_proc_ids:
        ocr_data = load_ocr_result(req.username, proc_id)
        fields = ocr_data.get("fields", {})
        w2 = parse_w2_from_ocr(fields)
        w2s.append(w2)

    # --- Parse 1099-INT interest from OCR ---
    ocr_interest = 0.0
    for proc_id in req.interest_1099_proc_ids:
        ocr_data = load_ocr_result(req.username, proc_id)
        fields = ocr_data.get("fields", {})
        ocr_interest += parse_1099int_from_ocr(fields)

    # --- Parse 1099-DIV dividends from OCR ---
    ocr_ordinary_div = 0.0
    ocr_qualified_div = 0.0
    ocr_cap_gain_dist = 0.0
    ocr_div_withheld = 0.0
    for proc_id in req.div_1099_proc_ids:
        ocr_data = load_ocr_result(req.username, proc_id)
        fields = ocr_data.get("fields", {})
        div = parse_1099div_from_ocr(fields)
        ocr_ordinary_div += div.ordinary_dividends
        ocr_qualified_div += div.qualified_dividends
        ocr_cap_gain_dist += div.capital_gain_dist
        ocr_div_withheld += div.federal_withheld

    # --- Parse 1099-NEC nonemployee compensation from OCR ---
    nec_businesses = []
    nec_withheld = 0.0
    for proc_id in req.nec_1099_proc_ids:
        ocr_data = load_ocr_result(req.username, proc_id)
        fields = ocr_data.get("fields", {})
        biz, withheld = parse_1099nec_from_ocr(fields)
        nec_businesses.append(biz)
        nec_withheld += withheld

    # --- Parse 1098 mortgage interest from OCR ---
    ocr_mortgage = 0.0
    for proc_id in req.mortgage_1098_proc_ids:
        ocr_data = load_ocr_result(req.username, proc_id)
        fields = ocr_data.get("fields", {})
        ocr_mortgage += parse_1098_from_ocr(fields)

    # --- Parse 1099-B structured brokerage transactions ---
    brokerage_txns = parse_1099b_from_structured(
        [t.model_dump() for t in req.brokerage_transactions]
    ) if req.brokerage_transactions else []

    # --- Load Plaid investment data (if connected) ---
    plaid_cap_txns = []
    plaid_ordinary_div = 0.0
    plaid_qualified_div = 0.0
    plaid_cap_gain_dist = 0.0
    if req.plaid_item_ids:
        from plaid_routes import load_plaid_tax_data
        for item_id in req.plaid_item_ids:
            tax_data = load_plaid_tax_data(req.username, item_id)
            if tax_data is None:
                raise HTTPException(400, f"Plaid item {item_id} not synced. Run POST /plaid/sync/{item_id} first.")
            # Capital transactions from sells
            for t in tax_data.get("capital_transactions", []):
                plaid_cap_txns.append(CapitalTransaction(
                    description=t["description"],
                    date_acquired=t.get("date_acquired", "Various"),
                    date_sold=t.get("date_sold", "2025"),
                    proceeds=t["proceeds"],
                    cost_basis=t["cost_basis"],
                    is_long_term=t.get("is_long_term", False),
                ))
            # Dividend income
            div = tax_data.get("dividend_income", {})
            plaid_ordinary_div += div.get("ordinary_dividends", 0)
            plaid_qualified_div += div.get("qualified_dividends", 0)
            plaid_cap_gain_dist += div.get("capital_gain_dist", 0)

    # --- Build additional income ---
    cap_txns = [
        CapitalTransaction(
            description=t.description,
            date_acquired=t.date_acquired,
            date_sold=t.date_sold,
            proceeds=t.proceeds,
            cost_basis=t.cost_basis,
            is_long_term=t.is_long_term,
        )
        for t in req.additional_income.capital_transactions
    ] + brokerage_txns + plaid_cap_txns

    # Cap gain distributions from 1099-DIV are long-term
    # Cap gain distributions from Plaid are also long-term
    if plaid_cap_gain_dist > 0:
        cap_txns.append(CapitalTransaction(
            description="Plaid Capital Gain Distributions",
            date_acquired="Various",
            date_sold="2025",
            proceeds=plaid_cap_gain_dist,
            cost_basis=0.0,
            is_long_term=True,
        ))

    if ocr_cap_gain_dist > 0:
        cap_txns.append(CapitalTransaction(
            description="1099-DIV Capital Gain Distributions",
            date_acquired="Various",
            date_sold="2025",
            proceeds=ocr_cap_gain_dist,
            cost_basis=0.0,
            is_long_term=True,
        ))

    additional = AdditionalIncome(
        other_interest=ocr_interest + req.additional_income.other_interest,
        ordinary_dividends=ocr_ordinary_div + plaid_ordinary_div + req.additional_income.ordinary_dividends,
        qualified_dividends=ocr_qualified_div + plaid_qualified_div + req.additional_income.qualified_dividends,
        capital_transactions=cap_txns,
        other_income=req.additional_income.other_income,
        other_income_description=req.additional_income.other_income_description,
    )

    # --- Build deductions ---
    deductions = Deductions(
        mortgage_interest=ocr_mortgage + req.deductions.mortgage_interest,
        property_tax=req.deductions.property_tax,
        state_income_tax_paid=req.deductions.state_income_tax_paid,
        charitable_cash=req.deductions.charitable_cash,
        charitable_noncash=req.deductions.charitable_noncash,
        medical_expenses=req.deductions.medical_expenses,
        student_loan_interest=req.deductions.student_loan_interest,
    )

    # --- Build payments ---
    payments = Payments(
        estimated_federal=req.payments.estimated_federal,
        estimated_state=req.payments.estimated_state,
    )

    # --- Filer info ---
    filer = PersonInfo(
        first_name=req.filer.first_name,
        last_name=req.filer.last_name,
        ssn=req.filer.ssn,
        address_street=req.filer.address_street,
        address_city=req.filer.address_city,
        address_state=req.filer.address_state,
        address_zip=req.filer.address_zip,
    )

    spouse = None
    if req.spouse:
        spouse = PersonInfo(
            first_name=req.spouse.first_name,
            last_name=req.spouse.last_name,
            ssn=req.spouse.ssn,
            address_street=req.spouse.address_street,
            address_city=req.spouse.address_city,
            address_state=req.spouse.address_state,
            address_zip=req.spouse.address_zip,
        )

    # --- Build business income (Schedule C) ---
    biz_list = [
        BusinessIncome(
            business_name=b.business_name,
            business_type=b.business_type,
            ein=b.ein,
            gross_receipts=b.gross_receipts,
            cost_of_goods_sold=b.cost_of_goods_sold,
            advertising=b.advertising,
            car_expenses=b.car_expenses,
            insurance=b.insurance,
            office_expense=b.office_expense,
            rent=b.rent,
            supplies=b.supplies,
            utilities=b.utilities,
            home_office_sqft=b.home_office_sqft,
            home_total_sqft=b.home_total_sqft,
            home_expenses=b.home_expenses,
            other_expenses=b.other_expenses,
            other_expenses_description=b.other_expenses_description,
        )
        for b in req.businesses
    ]

    # --- Build structured dependents ---
    dep_list = [
        Dependent(
            first_name=d.first_name, last_name=d.last_name, ssn=d.ssn,
            date_of_birth=d.date_of_birth, relationship=d.relationship,
            months_lived_with=d.months_lived_with,
            is_disabled=d.is_disabled, is_student=d.is_student,
        )
        for d in req.dependents
    ] if req.dependents else None

    # --- Build rental properties ---
    rental_list = [
        RentalProperty(
            property_address=r.property_address, rental_days=r.rental_days,
            personal_use_days=r.personal_use_days, gross_rents=r.gross_rents,
            advertising=r.advertising, auto_travel=r.auto_travel,
            cleaning_maintenance=r.cleaning_maintenance, commissions=r.commissions,
            insurance=r.insurance, legal_professional=r.legal_professional,
            management_fees=r.management_fees, mortgage_interest=r.mortgage_interest,
            repairs=r.repairs, supplies=r.supplies, taxes=r.taxes,
            utilities=r.utilities, depreciation=r.depreciation,
            other_expenses=r.other_expenses,
        )
        for r in req.rental_properties
    ] if req.rental_properties else None

    # --- Build HSA contributions ---
    hsa_list = [
        HSAContribution(
            contributor=h.contributor, contribution_amount=h.contribution_amount,
            employer_contributions=h.employer_contributions,
            coverage_type=h.coverage_type, age_55_plus=h.age_55_plus,
        )
        for h in req.hsa_contributions
    ] if req.hsa_contributions else None

    # --- Compute taxes ---
    result = compute_tax(
        filing_status=req.filing_status,
        filer=filer,
        w2s=w2s,
        additional=additional,
        deductions=deductions,
        payments=payments,
        spouse=spouse,
        num_dependents=req.num_dependents,
        dependents=dep_list,
        businesses=biz_list + nec_businesses,
        residence_state=req.residence_state,
        work_states=req.work_states,
        days_worked_by_state=req.days_worked_by_state or None,
        additional_withholding=ocr_div_withheld + nec_withheld,
        rental_properties=rental_list,
        hsa_contributions=hsa_list,
        tax_year=req.tax_year,
    )

    # --- Generate PDFs ---
    draft_dir = get_draft_dir(req.username, result.draft_id)
    pdf_paths = generate_all_pdfs(result, str(draft_dir))
    result.pdf_paths = pdf_paths

    # Audit risk assessment
    risk_report = assess_audit_risk(result)

    # Save computation result as JSON (include input for UI display)
    result_json = result.to_summary()
    result_json["audit_risk"] = risk_report.to_dict()
    result_json["pdf_urls"] = {
        name: f"/api/tax-draft/{result.draft_id}/pdf/{name}?username={req.username}"
        for name in pdf_paths.keys()
    }

    # Store the original request input for review
    result_json["input"] = {
        "filing_status": req.filing_status,
        "residence_state": req.residence_state,
        "work_states": req.work_states,
        "filer": req.filer.model_dump(),
        "spouse": req.spouse.model_dump() if req.spouse else None,
        "num_dependents": req.num_dependents,
        "w2_proc_ids": req.w2_proc_ids,
        "interest_1099_proc_ids": req.interest_1099_proc_ids,
        "div_1099_proc_ids": req.div_1099_proc_ids,
        "nec_1099_proc_ids": req.nec_1099_proc_ids,
        "mortgage_1098_proc_ids": req.mortgage_1098_proc_ids,
        "brokerage_transactions": [t.model_dump() for t in req.brokerage_transactions],
        "plaid_item_ids": req.plaid_item_ids,
        "businesses": [b.model_dump() for b in req.businesses + nec_businesses],
        "additional_income": req.additional_income.model_dump(),
        "deductions": req.deductions.model_dump(),
        "payments": req.payments.model_dump(),
    }

    (draft_dir / "result.json").write_text(json.dumps(result_json, indent=2, default=str))

    return result_json


@router.get("/{draft_id}")
async def get_tax_draft(draft_id: str, username: str = Query(...)):
    """Get a previously computed tax draft summary."""
    draft_dir = get_draft_dir(username, draft_id)
    result_file = draft_dir / "result.json"
    if not result_file.exists():
        raise HTTPException(404, f"Draft {draft_id} not found for user {username}")
    return json.loads(result_file.read_text())


@router.get("/{draft_id}/pdf/{form_name}")
async def download_pdf(
    draft_id: str,
    form_name: str,
    username: str = Query(...),
    download: bool = Query(default=False, description="Force download instead of inline view"),
):
    """View or download a generated tax form PDF.

    form_name: summary, 1040, schedule_a, schedule_b, schedule_c, schedule_d, schedule_se, il_1040
    """
    draft_dir = get_draft_dir(username, draft_id)
    if not draft_dir.exists():
        raise HTTPException(404, f"Draft {draft_id} not found")

    file_map = {
        "summary": "summary.pdf",
        "1040": "form_1040.pdf",
        "schedule_a": "schedule_a.pdf",
        "schedule_b": "schedule_b.pdf",
        "schedule_c": "schedule_c.pdf",
        "schedule_d": "schedule_d.pdf",
        "schedule_se": "schedule_se.pdf",
        "schedule_2": "schedule_2.pdf",
        "form_8959": "form_8959.pdf",
        "form_8960": "form_8960.pdf",
        "form_6251": "form_6251.pdf",
        "form_8863": "form_8863.pdf",
        "schedule_eic": "schedule_eic.pdf",
        "form_2441": "form_2441.pdf",
        "form_8880": "form_8880.pdf",
        "form_2210": "form_2210.pdf",
        "form_8889": "form_8889.pdf",
        "il_1040": "il_1040.pdf",
    }

    filename = file_map.get(form_name)
    if not filename:
        raise HTTPException(400, f"Unknown form: {form_name}. Available: {', '.join(file_map.keys())}")

    pdf_path = draft_dir / filename
    if not pdf_path.exists():
        raise HTTPException(404, f"Form {form_name} not generated for this draft")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"TaxLens_{draft_id}_{form_name}.pdf",
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/import-prior-year")
async def import_prior_year(
    file: UploadFile = File(...),
    tax_year: int = Query(default=0, description="Tax year of the uploaded return (auto-detected if 0)"),
    _auth: str = Depends(require_auth),
):
    """Import a prior-year Form 1040 PDF to extract key values.

    Upload a completed 1040 PDF (fillable or scanned). Extracts AGI,
    total tax, filing status, income breakdown, and deduction info.
    These values can be used to pre-populate the current year or
    for Form 2210 penalty safe harbor calculations.

    Returns extracted data with confidence level.
    """
    import tempfile

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        data = extract_from_fillable_pdf(tmp_path)
        if tax_year > 0:
            data.tax_year = tax_year

        result = data.to_dict()
        result["filename"] = file.filename
        return result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/{draft_id}/pdfs")
async def list_draft_pdfs(draft_id: str, username: str = Query(...)):
    """List all PDFs available for a draft."""
    draft_dir = get_draft_dir(username, draft_id)
    if not draft_dir.exists():
        raise HTTPException(404, f"Draft {draft_id} not found")

    pdfs = {}
    for f in draft_dir.glob("*.pdf"):
        name = f.stem.replace("form_", "")
        pdfs[name] = {
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "url": f"/api/tax-draft/{draft_id}/pdf/{name}?username={username}",
        }
    return {"draft_id": draft_id, "pdfs": pdfs}


@router.get("s/{username}")
async def list_drafts(username: str):
    """List all tax drafts for a user."""
    drafts_dir = STORAGE_ROOT / username.replace("/", "_").replace("..", "_") / "drafts"
    if not drafts_dir.exists():
        return {"drafts": []}

    drafts = []
    for d in sorted(drafts_dir.iterdir()):
        result_file = d / "result.json"
        if result_file.exists():
            data = json.loads(result_file.read_text())
            drafts.append(data)
    return {"drafts": drafts}
