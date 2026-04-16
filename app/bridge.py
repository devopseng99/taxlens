"""Bridge TaxLens OCR results to OpenFile populated_data table."""

import os
import json
import uuid
from datetime import datetime, timezone

import psycopg2


def get_openfile_db():
    """Connect to OpenFile PostgreSQL."""
    return psycopg2.connect(
        host=os.environ.get("OPENFILE_DB_HOST", "openfile-postgresql.openfile.svc.cluster.local"),
        port=int(os.environ.get("OPENFILE_DB_PORT", "5432")),
        dbname=os.environ.get("OPENFILE_DB_NAME", "openfile"),
        user=os.environ.get("OPENFILE_DB_USER", "postgres"),
        password=os.environ.get("OPENFILE_DB_PASSWORD", "postgres"),
    )


def ocr_to_w2_payload(ocr_fields: dict) -> dict:
    """Transform Azure DI OCR fields to OpenFile W2 payload format."""

    def get_val(field_name: str, default="") -> str:
        field = ocr_fields.get(field_name, {})
        val = field.get("value")
        if val is None:
            return default
        return str(val)

    def get_nested(parent_name: str, child_name: str, default="") -> str:
        parent = ocr_fields.get(parent_name, {})
        val = parent.get("value")
        if not isinstance(val, dict):
            return default
        child = val.get(child_name, {})
        return str(child.get("value", default)) if isinstance(child, dict) else default

    def parse_address(parent_name: str) -> dict:
        """Parse address from OCR into OpenFile address format."""
        raw = get_nested(parent_name, "Address")
        lines = raw.split("\n") if raw else [""]
        street = lines[0] if lines else ""
        city_state_zip = lines[1] if len(lines) > 1 else ""

        city, state, zipcode = "", "", ""
        if ", " in city_state_zip:
            parts = city_state_zip.split(", ")
            city = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            state_zip = rest.split(" ")
            state = state_zip[0] if state_zip else ""
            zipcode = state_zip[1] if len(state_zip) > 1 else ""

        return {
            "nameLine": get_nested(parent_name, "Name"),
            "nameLine2": "",
            "streetAddressLine1": street,
            "streetAddressLine2": "",
            "city": city,
            "state": state,
            "zipCode": zipcode,
            "country": "USA",
        }

    # Map checkbox fields
    is_statutory = get_val("IsStatutoryEmployee")
    is_sick_pay = get_val("IsThirdPartySickPay")
    is_retirement = get_val("IsRetirementPlan")

    w2 = {
        "source": "OCR",
        "tags": ["W2"],
        "ein": get_nested("Employer", "IdNumber"),
        "firstName": get_nested("Employee", "Name").split(" ")[0] if get_nested("Employee", "Name") else "",
        "employersAddress": parse_address("Employer"),
        "controlNumber": get_val("ControlNumber"),
        "employeeAddress": parse_address("Employee"),
        "wagesTipsOtherCompensation": get_val("WagesTipsAndOtherCompensation"),
        "federalIncomeTaxWithheld": get_val("FederalIncomeTaxWithheld"),
        "socialSecurityWages": get_val("SocialSecurityWages"),
        "socialSecurityTaxWithheld": get_val("SocialSecurityTaxWithheld"),
        "medicareWagesAndTips": get_val("MedicareWagesAndTips"),
        "medicareTaxWithheld": get_val("MedicareTaxWithheld"),
        "socialSecurityTips": get_val("SocialSecurityTips"),
        "allocatedTips": get_val("AllocatedTips"),
        "dependentCareBenefits": get_val("DependentCareBenefits"),
        "statutoryEmployeeIndicator": ":selected:" in is_statutory if is_statutory else False,
        "thirdPartySickPayIndicator": ":selected:" in is_sick_pay if is_sick_pay else False,
        "retirementPlanIndicator": ":selected:" in is_retirement if is_retirement else False,
        "nonQualifiedPlans": get_val("NonQualifiedPlans"),
    }

    return {"w2s": [w2]}


def write_populated_data(tax_return_id: str, ocr_fields: dict) -> dict:
    """Write OCR W2 data to OpenFile's populated_data table.

    Args:
        tax_return_id: UUID of the tax return in OpenFile
        ocr_fields: OCR fields from Azure DI analysis

    Returns:
        dict with inserted row details
    """
    w2_payload = ocr_to_w2_payload(ocr_fields)
    now = datetime.now(timezone.utc)
    row_id = str(uuid.uuid4())

    data_json = json.dumps(w2_payload)
    raw_json = json.dumps({"source": "taxlens_ocr", "ocr_fields": ocr_fields}, default=str)

    conn = get_openfile_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO populated_data (id, taxreturn_id, source, tags, data, created_at, raw_data)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (row_id, tax_return_id, "W2", "W2", data_json, now, raw_json),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": row_id,
        "taxreturn_id": tax_return_id,
        "source": "W2",
        "w2_payload": w2_payload,
        "created_at": now.isoformat(),
    }
