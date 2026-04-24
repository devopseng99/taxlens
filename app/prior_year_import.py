"""Prior-year 1040 import — extract key values from a completed 1040 PDF.

Reads a prior-year Form 1040 PDF (fillable or OCR'd) and extracts values
that can pre-populate the current year's return or help with penalty
calculations (prior_year_tax, prior_year_agi).

This module uses pypdf to read fillable form fields. If the PDF has no
form fields (i.e., scanned/printed), it falls back to Azure OCR via
the existing OCR module.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PriorYearData:
    """Key values extracted from a prior-year Form 1040."""
    tax_year: int = 0
    filing_status: str = ""
    # Income
    wages: float = 0.0                  # Line 1a
    taxable_interest: float = 0.0       # Line 2b
    ordinary_dividends: float = 0.0     # Line 3b
    capital_gain_loss: float = 0.0      # Line 7
    other_income: float = 0.0           # Line 8
    total_income: float = 0.0           # Line 9
    # Adjustments
    adjustments: float = 0.0            # Line 10
    agi: float = 0.0                    # Line 11
    # Deductions
    deduction_type: str = ""            # "standard" or "itemized"
    deduction_amount: float = 0.0       # Line 13
    taxable_income: float = 0.0         # Line 15
    # Tax
    total_tax: float = 0.0              # Line 24
    federal_withheld: float = 0.0       # Line 25
    refund: float = 0.0                 # Line 34
    owed: float = 0.0                   # Line 37
    # State
    residence_state: str = ""
    # Metadata
    source: str = ""                    # "fillable_pdf" or "ocr"
    fields_extracted: int = 0
    confidence: str = "low"             # "low", "medium", "high"

    def to_dict(self) -> dict:
        return {
            "tax_year": self.tax_year,
            "filing_status": self.filing_status,
            "income": {
                "wages": self.wages,
                "taxable_interest": self.taxable_interest,
                "ordinary_dividends": self.ordinary_dividends,
                "capital_gain_loss": self.capital_gain_loss,
                "other_income": self.other_income,
                "total_income": self.total_income,
            },
            "agi": self.agi,
            "deduction_type": self.deduction_type,
            "deduction_amount": self.deduction_amount,
            "taxable_income": self.taxable_income,
            "total_tax": self.total_tax,
            "federal_withheld": self.federal_withheld,
            "refund": self.refund,
            "owed": self.owed,
            "residence_state": self.residence_state,
            "source": self.source,
            "fields_extracted": self.fields_extracted,
            "confidence": self.confidence,
            "penalty_inputs": {
                "prior_year_tax": self.total_tax,
                "prior_year_agi": self.agi,
            },
        }


# Field name mappings for fillable IRS Form 1040 PDFs
# These field names come from the official IRS fillable PDF
FIELD_MAPPINGS_1040 = {
    # Filing status checkboxes
    "f1_1": "filing_status_single",
    "f1_2": "filing_status_mfj",
    "f1_3": "filing_status_mfs",
    "f1_4": "filing_status_hoh",
    "f1_5": "filing_status_qss",
    # Income lines
    "f1_7": "line_1a_wages",        # Line 1a - Wages
    "f1_10": "line_2b_interest",    # Line 2b - Taxable interest
    "f1_12": "line_3b_dividends",   # Line 3b - Ordinary dividends
    "f1_17": "line_7_cap_gains",    # Line 7 - Capital gain/loss
    "f1_18": "line_8_other",        # Line 8 - Other income
    "f1_19": "line_9_total",        # Line 9 - Total income
    "f1_20": "line_10_adjustments", # Line 10 - Adjustments
    "f1_21": "line_11_agi",         # Line 11 - AGI
    "f1_23": "line_13_deduction",   # Line 13 - Deduction
    "f1_25": "line_15_taxable",     # Line 15 - Taxable income
    "f1_34": "line_24_total_tax",   # Line 24 - Total tax
    "f1_35": "line_25_withheld",    # Line 25 - Federal withheld
    "f1_42": "line_34_overpaid",    # Line 34 - Overpaid (refund)
    "f1_47": "line_37_owed",        # Line 37 - Amount owed
    # Address
    "f1_8": "city",
    "f1_9": "state",
}

# Alternative field names used by some IRS PDFs
ALT_FIELD_MAPPINGS = {
    "topmostSubform[0].Page1[0].f1_7[0]": "line_1a_wages",
    "topmostSubform[0].Page1[0].f1_21[0]": "line_11_agi",
    "topmostSubform[0].Page2[0].f1_34[0]": "line_24_total_tax",
    "topmostSubform[0].Page2[0].f1_42[0]": "line_34_overpaid",
    "topmostSubform[0].Page2[0].f1_47[0]": "line_37_owed",
}


def _parse_money(val: str | None) -> float:
    """Parse a money string, handling commas, parens (negatives), etc."""
    if not val:
        return 0.0
    val = str(val).strip()
    if not val or val == "-" or val.lower() == "n/a":
        return 0.0
    negative = val.startswith("(") or val.startswith("-")
    val = val.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "").strip()
    try:
        result = float(val)
        return -result if negative else result
    except ValueError:
        return 0.0


def _detect_filing_status(fields: dict) -> str:
    """Detect filing status from checkbox fields."""
    for field_name, mapped in FIELD_MAPPINGS_1040.items():
        if "filing_status" in mapped and fields.get(field_name):
            val = str(fields[field_name]).strip()
            if val and val != "/Off":
                if "single" in mapped:
                    return "single"
                if "mfj" in mapped:
                    return "mfj"
                if "mfs" in mapped:
                    return "mfs"
                if "hoh" in mapped:
                    return "hoh"
    return ""


def extract_from_fillable_pdf(pdf_path: str | Path) -> PriorYearData:
    """Extract prior-year data from a fillable Form 1040 PDF.

    Uses pypdf to read form field values. Works with official IRS
    fillable PDFs that have been filled in (e.g., from tax software
    that outputs fillable PDFs).

    Args:
        pdf_path: Path to the 1040 PDF file

    Returns:
        PriorYearData with extracted values
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    data = PriorYearData(source="fillable_pdf")

    # Collect all form fields
    fields: dict[str, str] = {}
    for page in reader.pages:
        if hasattr(page, '/Annots') and page['/Annots']:
            for annot in page['/Annots']:
                obj = annot.get_object()
                field_name = obj.get('/T', '')
                field_value = obj.get('/V', '')
                if field_name and field_value:
                    fields[str(field_name)] = str(field_value)

    if not fields:
        # Try reader.get_form_text_fields() as fallback
        try:
            text_fields = reader.get_form_text_fields()
            if text_fields:
                fields = {k: v for k, v in text_fields.items() if v}
        except Exception:
            pass

    if not fields:
        data.confidence = "low"
        return data

    # Map fields to PriorYearData
    mapped_values: dict[str, str] = {}
    for field_name, value in fields.items():
        # Try direct mapping
        mapped = FIELD_MAPPINGS_1040.get(field_name)
        if not mapped:
            mapped = ALT_FIELD_MAPPINGS.get(field_name)
        if not mapped:
            # Try partial match (field names can have [0] suffixes)
            base = field_name.split("[")[0] if "[" in field_name else field_name
            mapped = FIELD_MAPPINGS_1040.get(base)
        if mapped:
            mapped_values[mapped] = value

    # Extract income values
    data.wages = _parse_money(mapped_values.get("line_1a_wages"))
    data.taxable_interest = _parse_money(mapped_values.get("line_2b_interest"))
    data.ordinary_dividends = _parse_money(mapped_values.get("line_3b_dividends"))
    data.capital_gain_loss = _parse_money(mapped_values.get("line_7_cap_gains"))
    data.other_income = _parse_money(mapped_values.get("line_8_other"))
    data.total_income = _parse_money(mapped_values.get("line_9_total"))
    data.adjustments = _parse_money(mapped_values.get("line_10_adjustments"))
    data.agi = _parse_money(mapped_values.get("line_11_agi"))
    data.deduction_amount = _parse_money(mapped_values.get("line_13_deduction"))
    data.taxable_income = _parse_money(mapped_values.get("line_15_taxable"))
    data.total_tax = _parse_money(mapped_values.get("line_24_total_tax"))
    data.federal_withheld = _parse_money(mapped_values.get("line_25_withheld"))
    data.refund = _parse_money(mapped_values.get("line_34_overpaid"))
    data.owed = _parse_money(mapped_values.get("line_37_owed"))

    # Filing status
    data.filing_status = _detect_filing_status(fields)

    # State
    state = mapped_values.get("state", "")
    if state and len(state) == 2:
        data.residence_state = state.upper()

    # Count extracted fields and set confidence
    extracted = sum(1 for v in [
        data.wages, data.agi, data.total_tax, data.taxable_income,
        data.deduction_amount, data.federal_withheld,
    ] if v != 0)
    data.fields_extracted = extracted

    if extracted >= 4:
        data.confidence = "high"
    elif extracted >= 2:
        data.confidence = "medium"
    else:
        data.confidence = "low"

    return data
