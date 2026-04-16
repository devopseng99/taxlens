"""Tax draft API routes — create, view, and download completed tax form PDFs."""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from tax_engine import (
    PersonInfo, W2Income, CapitalTransaction, BusinessIncome, Deductions,
    AdditionalIncome, Payments, TaxResult,
    compute_tax, parse_w2_from_ocr, parse_1099int_from_ocr,
)
from pdf_generator import generate_all_pdfs

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


class PaymentsInput(BaseModel):
    estimated_federal: float = 0.0
    estimated_state: float = 0.0


class TaxDraftRequest(BaseModel):
    filing_status: str = Field(..., description="single, mfj, hoh, or mfs")
    username: str = Field(..., description="TaxLens username (for document lookup)")
    filer: PersonInput = PersonInput()
    spouse: Optional[PersonInput] = None
    num_dependents: int = 0

    # OCR document references — pull W-2/1099 data from existing TaxLens documents
    w2_proc_ids: list[str] = Field(default=[], description="proc_ids of uploaded W-2s with OCR results")
    interest_1099_proc_ids: list[str] = Field(default=[], description="proc_ids of uploaded 1099-INTs with OCR")

    # Business income (Schedule C)
    businesses: list[BusinessIncomeInput] = Field(default=[], description="Self-employment / business income")

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
async def create_tax_draft(req: TaxDraftRequest):
    """Create a complete tax draft from OCR data + supplemental info.

    Computes federal 1040 + Illinois IL-1040, generates PDF forms,
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
    ]

    additional = AdditionalIncome(
        other_interest=ocr_interest + req.additional_income.other_interest,
        ordinary_dividends=req.additional_income.ordinary_dividends,
        qualified_dividends=req.additional_income.qualified_dividends,
        capital_transactions=cap_txns,
        other_income=req.additional_income.other_income,
        other_income_description=req.additional_income.other_income_description,
    )

    # --- Build deductions ---
    deductions = Deductions(
        mortgage_interest=req.deductions.mortgage_interest,
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
        businesses=biz_list,
    )

    # --- Generate PDFs ---
    draft_dir = get_draft_dir(req.username, result.draft_id)
    pdf_paths = generate_all_pdfs(result, str(draft_dir))
    result.pdf_paths = pdf_paths

    # Save computation result as JSON
    result_json = result.to_summary()
    result_json["pdf_urls"] = {
        name: f"/api/tax-draft/{result.draft_id}/pdf/{name}?username={req.username}"
        for name in pdf_paths.keys()
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
async def download_pdf(draft_id: str, form_name: str, username: str = Query(...)):
    """Download a generated tax form PDF.

    form_name: summary, 1040, schedule_a, schedule_b, schedule_d, il_1040
    """
    draft_dir = get_draft_dir(username, draft_id)
    if not draft_dir.exists():
        raise HTTPException(404, f"Draft {draft_id} not found")

    # Map form names to filenames
    file_map = {
        "summary": "summary.pdf",
        "1040": "form_1040.pdf",
        "schedule_a": "schedule_a.pdf",
        "schedule_b": "schedule_b.pdf",
        "schedule_c": "schedule_c.pdf",
        "schedule_d": "schedule_d.pdf",
        "schedule_se": "schedule_se.pdf",
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
    )


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
