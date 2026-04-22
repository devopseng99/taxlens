"""Document metadata repository — CRUD for the documents table."""

from datetime import datetime, timezone

from db.connection import execute, fetchone, fetchall


async def save_metadata(proc_id: str, tenant_id: str, username: str,
                        filename: str, content_type: str, size_bytes: int,
                        sha256: str, storage_path: str,
                        form_type: str | None = None) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await execute(
        "INSERT INTO documents "
        "(proc_id, tenant_id, username, filename, content_type, size_bytes, "
        "sha256, form_type, has_ocr, storage_path, uploaded_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s)",
        (proc_id, tenant_id, username, filename, content_type,
         size_bytes, sha256, form_type, storage_path, now),
    )
    return {
        "proc_id": proc_id, "tenant_id": tenant_id, "username": username,
        "filename": filename, "content_type": content_type,
        "size_bytes": size_bytes, "sha256": sha256, "form_type": form_type,
        "has_ocr": False, "storage_path": storage_path, "uploaded_at": now,
    }


async def get_document(tenant_id: str, proc_id: str) -> dict | None:
    return await fetchone(
        "SELECT * FROM documents WHERE proc_id = %s AND tenant_id = %s",
        (proc_id, tenant_id),
    )


async def list_documents(tenant_id: str, username: str | None = None) -> list[dict]:
    if username:
        return await fetchall(
            "SELECT * FROM documents WHERE tenant_id = %s AND username = %s ORDER BY uploaded_at DESC",
            (tenant_id, username),
        )
    return await fetchall(
        "SELECT * FROM documents WHERE tenant_id = %s ORDER BY uploaded_at DESC",
        (tenant_id,),
    )


async def mark_ocr_done(tenant_id: str, proc_id: str, form_type: str | None = None) -> int:
    if form_type:
        return await execute(
            "UPDATE documents SET has_ocr = 1, form_type = %s WHERE proc_id = %s AND tenant_id = %s",
            (form_type, proc_id, tenant_id),
        )
    return await execute(
        "UPDATE documents SET has_ocr = 1 WHERE proc_id = %s AND tenant_id = %s",
        (proc_id, tenant_id),
    )


async def delete_document(tenant_id: str, proc_id: str) -> int:
    return await execute(
        "DELETE FROM documents WHERE proc_id = %s AND tenant_id = %s",
        (proc_id, tenant_id),
    )
