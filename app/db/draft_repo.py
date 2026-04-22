"""Tax draft repository — CRUD for the tax_drafts table."""

import uuid
import json
from datetime import datetime, timezone

from db.connection import execute, fetchone, fetchall


async def save_draft(tenant_id: str, username: str, filing_status: str,
                     filer_name: str = None, residence_state: str = None,
                     result: dict = None, input_data: dict = None,
                     pdf_forms: list[str] = None, storage_path: str = None) -> dict:
    """Save a new tax draft. Returns the draft dict with id."""
    draft_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    total_income = result.get("total_income", 0) if result else 0
    agi = result.get("agi", 0) if result else 0
    federal_tax = result.get("federal_tax", 0) if result else 0
    net_refund = result.get("net_refund_or_owed", 0) if result else 0

    await execute(
        "INSERT INTO tax_drafts "
        "(id, tenant_id, username, filing_status, filer_name, residence_state, "
        "total_income, agi, federal_tax, net_refund, result_json, input_json, "
        "pdf_forms, storage_path, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (draft_id, tenant_id, username, filing_status, filer_name,
         residence_state, total_income, agi, federal_tax, net_refund,
         json.dumps(result) if result else None,
         json.dumps(input_data) if input_data else None,
         json.dumps(pdf_forms) if pdf_forms else None,
         storage_path, now, now),
    )
    return {
        "id": draft_id, "tenant_id": tenant_id, "username": username,
        "filing_status": filing_status, "filer_name": filer_name,
        "residence_state": residence_state,
        "total_income": total_income, "agi": agi,
        "federal_tax": federal_tax, "net_refund": net_refund,
        "storage_path": storage_path, "created_at": now,
    }


async def get_draft(tenant_id: str, draft_id: str) -> dict | None:
    return await fetchone(
        "SELECT * FROM tax_drafts WHERE id = %s AND tenant_id = %s",
        (draft_id, tenant_id),
    )


async def list_drafts(tenant_id: str, username: str | None = None) -> list[dict]:
    if username:
        return await fetchall(
            "SELECT id, tenant_id, username, filing_status, filer_name, residence_state, "
            "total_income, agi, federal_tax, net_refund, pdf_forms, storage_path, created_at "
            "FROM tax_drafts WHERE tenant_id = %s AND username = %s ORDER BY created_at DESC",
            (tenant_id, username),
        )
    return await fetchall(
        "SELECT id, tenant_id, username, filing_status, filer_name, residence_state, "
        "total_income, agi, federal_tax, net_refund, pdf_forms, storage_path, created_at "
        "FROM tax_drafts WHERE tenant_id = %s ORDER BY created_at DESC",
        (tenant_id,),
    )


async def delete_draft(tenant_id: str, draft_id: str) -> int:
    return await execute(
        "DELETE FROM tax_drafts WHERE id = %s AND tenant_id = %s",
        (draft_id, tenant_id),
    )
