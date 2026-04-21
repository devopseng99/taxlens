"""Plaid integration routes — connect banks/brokerages and import tax data.

Endpoints:
  POST /plaid/create-link-token   — Get a Link token for frontend
  POST /plaid/exchange-token      — Exchange public_token for access_token
  GET  /plaid/accounts/{username} — List connected accounts
  POST /plaid/sync/{item_id}      — Pull investment data from connected account
  DELETE /plaid/accounts/{item_id} — Disconnect an institution
"""

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import require_auth
from plaid_client import (
    get_plaid_client,
    create_link_token,
    exchange_public_token,
    get_investment_transactions,
    remove_item,
)
from plaid_parsers import plaid_to_tax_data

router = APIRouter(prefix="/plaid", tags=["Plaid Integration"])

STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))
FERNET_KEY = os.getenv("PLAID_FERNET_KEY", "")

# Plaid integration enabled only when credentials + encryption key are set
PLAID_ENABLED = bool(os.getenv("PLAID_CLIENT_ID")) and bool(FERNET_KEY)


def _get_fernet() -> Fernet:
    """Get Fernet instance for encrypting/decrypting access tokens."""
    if not FERNET_KEY:
        raise HTTPException(500, "Plaid encryption key not configured (PLAID_FERNET_KEY)")
    return Fernet(FERNET_KEY.encode())


def _plaid_dir(username: str) -> Path:
    """Base directory for a user's Plaid data."""
    safe = username.replace("/", "_").replace("..", "_")
    return STORAGE_ROOT / safe / "plaid"


def _item_dir(username: str, item_id: str) -> Path:
    safe_item = item_id.replace("/", "_").replace("..", "_")
    return _plaid_dir(username) / safe_item


def _require_plaid():
    """Check that Plaid integration is enabled."""
    if not PLAID_ENABLED:
        raise HTTPException(
            503,
            "Plaid integration not configured. Set PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_FERNET_KEY.",
        )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ExchangeTokenRequest(BaseModel):
    public_token: str
    username: str
    institution_name: str = ""


class SyncRequest(BaseModel):
    username: str
    tax_year: int = 2025


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/status")
async def plaid_status():
    """Check if Plaid integration is enabled."""
    return {
        "enabled": PLAID_ENABLED,
        "environment": os.getenv("PLAID_ENV", "sandbox"),
    }


@router.post("/create-link-token")
async def create_link_token_endpoint(
    username: str = Query(...),
    _auth: str = Depends(require_auth),
):
    """Create a Plaid Link token for the frontend."""
    _require_plaid()
    client = get_plaid_client()
    result = create_link_token(client, user_id=username)
    return {
        "link_token": result.get("link_token"),
        "expiration": result.get("expiration"),
    }


@router.post("/exchange-token")
async def exchange_token_endpoint(
    req: ExchangeTokenRequest,
    _auth: str = Depends(require_auth),
):
    """Exchange a Plaid Link public_token for a persistent access_token.

    The access_token is encrypted with Fernet and stored on the PVC.
    """
    _require_plaid()
    client = get_plaid_client()
    result = exchange_public_token(client, req.public_token)

    access_token = result["access_token"]
    item_id = result["item_id"]

    # Encrypt and store access token
    fernet = _get_fernet()
    encrypted = fernet.encrypt(access_token.encode()).decode()

    item_path = _item_dir(req.username, item_id)
    item_path.mkdir(parents=True, exist_ok=True)

    (item_path / "token.enc").write_text(encrypted)
    (item_path / "metadata.json").write_text(json.dumps({
        "item_id": item_id,
        "institution_name": req.institution_name,
        "username": req.username,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "environment": os.getenv("PLAID_ENV", "sandbox"),
    }, indent=2))

    return {
        "item_id": item_id,
        "institution_name": req.institution_name,
        "status": "connected",
    }


@router.get("/accounts/{username}")
async def list_accounts(username: str):
    """List all connected Plaid accounts for a user."""
    plaid_base = _plaid_dir(username)
    if not plaid_base.exists():
        return {"accounts": [], "plaid_enabled": PLAID_ENABLED}

    accounts = []
    for item_path in sorted(plaid_base.iterdir()):
        meta_file = item_path / "metadata.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            meta["has_sync"] = (item_path / "transactions.json").exists()
            accounts.append(meta)

    return {"accounts": accounts, "plaid_enabled": PLAID_ENABLED}


@router.post("/sync/{item_id}")
async def sync_investments(
    item_id: str,
    req: SyncRequest,
    _auth: str = Depends(require_auth),
):
    """Pull investment transactions from a connected Plaid account.

    Fetches transactions for the tax year, converts to tax objects,
    and stores raw + parsed data on PVC.
    """
    _require_plaid()

    item_path = _item_dir(req.username, item_id)
    token_file = item_path / "token.enc"
    if not token_file.exists():
        raise HTTPException(404, f"No connected account with item_id {item_id} for user {req.username}")

    # Decrypt access token
    fernet = _get_fernet()
    access_token = fernet.decrypt(token_file.read_text().encode()).decode()

    # Fetch investment transactions for tax year
    client = get_plaid_client()
    start = date(req.tax_year, 1, 1)
    end = date(req.tax_year, 12, 31)

    raw_data = get_investment_transactions(client, access_token, start, end)

    # Store raw response
    (item_path / "transactions.json").write_text(
        json.dumps(raw_data, indent=2, default=str)
    )

    # Parse into tax objects
    tax_data = plaid_to_tax_data(
        raw_data.get("investment_transactions", []),
        raw_data.get("securities", []),
    )

    # Store parsed tax data (serializable summary)
    parsed = {
        "tax_year": req.tax_year,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "summary": tax_data["summary"],
        "capital_transactions": [
            {
                "description": t.description,
                "date_acquired": t.date_acquired,
                "date_sold": t.date_sold,
                "proceeds": t.proceeds,
                "cost_basis": t.cost_basis,
                "is_long_term": t.is_long_term,
            }
            for t in tax_data["capital_transactions"]
        ],
        "dividend_income": {
            "payer_name": tax_data["dividend_income"].payer_name,
            "ordinary_dividends": tax_data["dividend_income"].ordinary_dividends,
            "qualified_dividends": tax_data["dividend_income"].qualified_dividends,
            "capital_gain_dist": tax_data["dividend_income"].capital_gain_dist,
        },
    }
    (item_path / "tax_data.json").write_text(json.dumps(parsed, indent=2))

    return {
        "item_id": item_id,
        "tax_year": req.tax_year,
        "status": "synced",
        **tax_data["summary"],
    }


@router.delete("/accounts/{item_id}")
async def disconnect_account(
    item_id: str,
    username: str = Query(...),
    _auth: str = Depends(require_auth),
):
    """Disconnect a Plaid institution and remove stored data."""
    _require_plaid()

    item_path = _item_dir(username, item_id)
    token_file = item_path / "token.enc"

    if token_file.exists():
        # Try to remove from Plaid (best effort)
        try:
            fernet = _get_fernet()
            access_token = fernet.decrypt(token_file.read_text().encode()).decode()
            client = get_plaid_client()
            remove_item(client, access_token)
        except Exception:
            pass  # Continue with local cleanup even if Plaid API call fails

    # Remove local data
    if item_path.exists():
        import shutil
        shutil.rmtree(item_path)

    return {"item_id": item_id, "status": "disconnected"}


# ---------------------------------------------------------------------------
# Helper for tax draft integration
# ---------------------------------------------------------------------------
def load_plaid_tax_data(username: str, item_id: str) -> dict | None:
    """Load parsed tax data for a Plaid item.

    Returns the tax_data.json contents, or None if not synced.
    """
    item_path = _item_dir(username, item_id)
    tax_file = item_path / "tax_data.json"
    if not tax_file.exists():
        return None
    return json.loads(tax_file.read_text())
