#!/usr/bin/env python3
"""One-time migration: scan existing PVC files and populate Dolt tables.

Creates a 'default' tenant and migrates all existing data.
Run as a K8s Job AFTER Dolt is deployed but BEFORE the new API is deployed.

Usage:
    DOLT_HOST=taxlens-dolt DOLT_PORT=3306 DOLT_DATABASE=taxlens python migrate_to_dolt.py
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from db.connection import init_pool, close_pool, execute, fetchone, get_conn
from db.migrate import run_migrations


STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))
DEFAULT_TENANT_ID = os.getenv("MIGRATION_TENANT_ID", uuid.uuid4().hex)
DEFAULT_TENANT_NAME = os.getenv("MIGRATION_TENANT_NAME", "Default Tenant")
DEFAULT_TENANT_SLUG = os.getenv("MIGRATION_TENANT_SLUG", "default")


async def migrate():
    print(f"=== TaxLens Migration to Dolt ===")
    print(f"Storage root: {STORAGE_ROOT}")
    print(f"Default tenant: {DEFAULT_TENANT_NAME} ({DEFAULT_TENANT_SLUG})")
    print(f"Tenant ID: {DEFAULT_TENANT_ID}")

    # Initialize pool and run schema
    await init_pool()
    await run_migrations()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Check if default tenant already exists
    existing = await fetchone("SELECT id FROM tenants WHERE slug = %s", (DEFAULT_TENANT_SLUG,))
    if existing:
        print(f"Default tenant already exists (id={existing['id']}), skipping tenant creation.")
        tenant_id = existing["id"]
    else:
        # Create default tenant
        await execute(
            "INSERT INTO tenants (id, name, slug, plan, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'starter', 'active', %s, %s)",
            (DEFAULT_TENANT_ID, DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG, now, now),
        )
        tenant_id = DEFAULT_TENANT_ID
        print(f"Created default tenant: {tenant_id}")

    if not STORAGE_ROOT.exists():
        print(f"Storage root {STORAGE_ROOT} does not exist. Nothing to migrate.")
        await close_pool()
        return

    # Scan user directories
    user_count = 0
    doc_count = 0
    draft_count = 0
    plaid_count = 0

    for user_path in sorted(STORAGE_ROOT.iterdir()):
        if not user_path.is_dir():
            continue
        # Skip tenant ID directories (already migrated)
        if len(user_path.name) == 32 and all(c in "0123456789abcdef" for c in user_path.name):
            continue

        username = user_path.name

        # Create or find user
        user_exists = await fetchone(
            "SELECT id FROM users WHERE tenant_id = %s AND username = %s",
            (tenant_id, username),
        )
        if not user_exists:
            user_id = uuid.uuid4().hex
            await execute(
                "INSERT INTO users (id, tenant_id, username, role, created_at) "
                "VALUES (%s, %s, %s, 'member', %s)",
                (user_id, tenant_id, username, now),
            )
            user_count += 1
        else:
            user_id = user_exists["id"]

        # Scan document directories (proc_id dirs with metadata.json)
        for item in sorted(user_path.iterdir()):
            if not item.is_dir():
                continue

            # Skip special directories
            if item.name in ("drafts", "plaid"):
                continue

            meta_file = item / "metadata.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    proc_id = meta.get("proc_id", item.name)
                    has_ocr = (item / "ocr_result.json").exists()
                    ocr_data = json.loads((item / "ocr_result.json").read_text()) if has_ocr else {}
                    form_type = ocr_data.get("form_type")

                    # Check if already migrated
                    exists = await fetchone(
                        "SELECT proc_id FROM documents WHERE proc_id = %s",
                        (proc_id,),
                    )
                    if not exists:
                        await execute(
                            "INSERT INTO documents "
                            "(proc_id, tenant_id, username, filename, content_type, "
                            "size_bytes, sha256, form_type, has_ocr, storage_path, uploaded_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (proc_id, tenant_id, username,
                             meta.get("filename", "unknown"),
                             meta.get("content_type", ""),
                             meta.get("size_bytes", 0),
                             meta.get("sha256", ""),
                             form_type,
                             1 if has_ocr else 0,
                             meta.get("storage_path", f"{username}/{proc_id}"),
                             meta.get("uploaded_at", now)),
                        )
                        doc_count += 1
                except Exception as e:
                    print(f"  Warning: failed to migrate doc {item}: {e}")

        # Scan drafts directory
        drafts_dir = user_path / "drafts"
        if drafts_dir.exists():
            for draft_dir in sorted(drafts_dir.iterdir()):
                if not draft_dir.is_dir():
                    continue
                result_file = draft_dir / "result.json"
                if result_file.exists():
                    try:
                        result = json.loads(result_file.read_text())
                        draft_id = draft_dir.name
                        input_file = draft_dir / "input.json"
                        input_data = json.loads(input_file.read_text()) if input_file.exists() else {}

                        exists = await fetchone(
                            "SELECT id FROM tax_drafts WHERE id = %s",
                            (draft_id,),
                        )
                        if not exists:
                            summary = result.get("summary", result)
                            await execute(
                                "INSERT INTO tax_drafts "
                                "(id, tenant_id, username, filing_status, filer_name, "
                                "residence_state, total_income, agi, federal_tax, "
                                "net_refund, result_json, input_json, storage_path, "
                                "created_at, updated_at) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                (draft_id, tenant_id, username,
                                 summary.get("filing_status", "single"),
                                 summary.get("filer_name", ""),
                                 input_data.get("residence_state", "IL"),
                                 summary.get("total_income", 0),
                                 summary.get("agi", 0),
                                 summary.get("federal_tax", 0),
                                 summary.get("net_refund_or_owed", 0),
                                 json.dumps(result),
                                 json.dumps(input_data),
                                 f"{username}/drafts/{draft_id}",
                                 now, now),
                            )
                            draft_count += 1
                    except Exception as e:
                        print(f"  Warning: failed to migrate draft {draft_dir}: {e}")

        # Scan Plaid items
        plaid_dir = user_path / "plaid"
        if plaid_dir.exists():
            for item_dir in sorted(plaid_dir.iterdir()):
                if not item_dir.is_dir():
                    continue
                meta_file = item_dir / "metadata.json"
                token_file = item_dir / "token.enc"
                if meta_file.exists() and token_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text())
                        item_id = item_dir.name

                        exists = await fetchone(
                            "SELECT item_id FROM plaid_items WHERE item_id = %s",
                            (item_id,),
                        )
                        if not exists:
                            await execute(
                                "INSERT INTO plaid_items "
                                "(item_id, tenant_id, username, institution_name, "
                                "encrypted_token, environment, has_sync, connected_at) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                (item_id, tenant_id, username,
                                 meta.get("institution_name", ""),
                                 token_file.read_text(),
                                 meta.get("environment", "sandbox"),
                                 1 if (item_dir / "tax_data.json").exists() else 0,
                                 meta.get("connected_at", now)),
                            )
                            plaid_count += 1
                    except Exception as e:
                        print(f"  Warning: failed to migrate Plaid item {item_dir}: {e}")

    # Dolt commit
    import aiomysql
    async with get_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("CALL dolt_add('.')")
            await cur.execute(
                "CALL dolt_commit('-m', %s, '--allow-empty')",
                (f"migration: {user_count} users, {doc_count} docs, {draft_count} drafts, {plaid_count} plaid items",),
            )

    print(f"\n=== Migration Complete ===")
    print(f"Tenant: {tenant_id}")
    print(f"Users: {user_count}")
    print(f"Documents: {doc_count}")
    print(f"Tax Drafts: {draft_count}")
    print(f"Plaid Items: {plaid_count}")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(migrate())
