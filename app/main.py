"""TaxLens Document Intake API — local-first tax document storage + Azure OCR."""

import os
import uuid
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from ocr import analyze_document
from bridge import ocr_to_w2_payload, write_populated_data
from tax_routes import router as tax_router
from auth import require_auth, AUTH_ENABLED
from contextlib import asynccontextmanager
from mcp_server import mcp

# Create MCP Starlette app (initializes session_manager lazily)
_mcp_starlette = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app):
    """Start MCP session manager (required for StreamableHTTP transport)."""
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="TaxLens Document Intake API",
    version="0.1.0",
    docs_url="/docs",
    root_path="/api",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taxlens.istayintek.com",
        "https://dropit.istayintek.com",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Config from env ---
STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))
MAX_FILE_SIZE = int(os.getenv("TAXLENS_MAX_FILE_MB", "30")) * 1024 * 1024  # 30MB default

# Mount tax draft routes
app.include_router(tax_router)

# Mount MCP server (StreamableHTTP at /mcp)
# Accessible at https://dropit.istayintek.com/api/mcp
# Session manager lifecycle managed by FastAPI lifespan above
from starlette.routing import Mount, Route
from mcp.server.fastmcp.server import StreamableHTTPASGIApp

_mcp_asgi = StreamableHTTPASGIApp(mcp.session_manager)
app.router.routes.append(Route("/mcp", endpoint=_mcp_asgi))
app.router.routes.append(Route("/mcp/", endpoint=_mcp_asgi))


# --- Models ---
class DocumentMetadata(BaseModel):
    proc_id: str
    username: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_at: str
    storage_path: str


class OcrResult(BaseModel):
    proc_id: str
    model_id: str
    form_type: str | None = None
    fields: dict
    confidence: float
    pages: int
    raw_path: str | None = None


# --- Helpers ---
def user_dir(username: str) -> Path:
    """Safe user directory — no path traversal."""
    safe = username.replace("/", "_").replace("..", "_").replace("\\", "_")
    return STORAGE_ROOT / safe


def doc_dir(username: str, proc_id: str) -> Path:
    return user_dir(username) / proc_id


# Azure doc_type strings → simplified form type
_DOC_TYPE_MAP = {
    "tax.us.w2": "W-2",
    "tax.us.1099Int": "1099-INT",
    "tax.us.1099Div": "1099-DIV",
    "tax.us.1099Nec": "1099-NEC",
    "tax.us.1099Misc": "1099-MISC",
    "tax.us.1098": "1098",
    "tax.us.1099B": "1099-B",
    "tax.us.1040": "1040",
}


def _detect_form_type(doc_type: str | None, model_id: str) -> str | None:
    """Detect tax form type from Azure doc_type or model_id."""
    if doc_type:
        # Azure auto-detect returns e.g. "tax.us.w2", "tax.us.1099Div"
        for key, form in _DOC_TYPE_MAP.items():
            if key.lower() in doc_type.lower():
                return form
        # If doc_type is present but unrecognized, use it as-is
        return doc_type

    # Fall back to model_id hints
    model_lower = model_id.lower()
    if "w2" in model_lower:
        return "W-2"
    if "1099int" in model_lower:
        return "1099-INT"
    if "1099div" in model_lower:
        return "1099-DIV"
    if "1099nec" in model_lower:
        return "1099-NEC"
    if "1098" in model_lower:
        return "1098"
    return None


# --- Endpoints ---

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "storage_root": str(STORAGE_ROOT),
        "writable": STORAGE_ROOT.exists(),
        "auth_enabled": AUTH_ENABLED,
        "mcp_endpoint": "/api/mcp",
    }


@app.post("/upload", response_model=DocumentMetadata)
async def upload_document(
    file: UploadFile = File(...),
    username: str = Form(...),
    doc_type: str = Form(default="auto"),
    _auth: str = Depends(require_auth),
):
    """Upload a tax document (PDF, image). Stored locally on PVC."""

    # Validate content type
    allowed = {"application/pdf", "image/jpeg", "image/png", "image/tiff", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Allowed: {', '.join(allowed)}")

    # Read and check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large: {len(content)} bytes. Max: {MAX_FILE_SIZE} bytes ({MAX_FILE_SIZE // (1024*1024)}MB)")

    # Generate processing ID and paths
    proc_id = uuid.uuid4().hex[:12]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = Path(file.filename).suffix if file.filename else ".bin"
    storage_name = f"{ts}_{proc_id}{ext}"

    dest_dir = doc_dir(username, proc_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / storage_name

    # Write file
    dest_path.write_bytes(content)

    # Compute SHA-256
    sha = hashlib.sha256(content).hexdigest()

    # Write metadata sidecar
    meta = DocumentMetadata(
        proc_id=proc_id,
        username=username,
        filename=file.filename or "unknown",
        content_type=file.content_type,
        size_bytes=len(content),
        sha256=sha,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        storage_path=str(dest_path.relative_to(STORAGE_ROOT)),
    )
    (dest_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))

    return meta


@app.post("/analyze/{proc_id}", response_model=OcrResult)
async def analyze(
    proc_id: str,
    username: str = Query(...),
    model_id: str = Query(default="prebuilt-tax.us"),
    _auth: str = Depends(require_auth),
):
    """Run Azure Document Intelligence OCR on an uploaded document."""

    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404, f"Document {proc_id} not found for user {username}")

    # Find the uploaded file (not metadata.json)
    files = [f for f in dest.iterdir() if f.name != "metadata.json" and f.name != "ocr_result.json"]
    if not files:
        raise HTTPException(404, f"No document file in {proc_id}")

    doc_file = files[0]

    # Call Azure Document Intelligence
    try:
        result = await analyze_document(doc_file, model_id)
    except Exception as e:
        raise HTTPException(502, f"Azure OCR failed: {str(e)}")

    # Detect form type from Azure response
    form_type = _detect_form_type(result.get("doc_type", ""), model_id)

    # Save OCR result (include form_type for downstream parsers)
    raw_data = result["raw"]
    raw_data["form_type"] = form_type
    ocr_path = dest / "ocr_result.json"
    ocr_path.write_text(json.dumps(raw_data, indent=2, default=str))

    ocr = OcrResult(
        proc_id=proc_id,
        model_id=model_id,
        form_type=form_type,
        fields=result["fields"],
        confidence=result["confidence"],
        pages=result["pages"],
        raw_path=str(ocr_path.relative_to(STORAGE_ROOT)),
    )
    return ocr


@app.get("/documents/{username}")
async def list_documents(username: str):
    """List all documents for a user."""
    udir = user_dir(username)
    if not udir.exists():
        return {"documents": []}

    docs = []
    for proc_dir in sorted(udir.iterdir()):
        meta_file = proc_dir / "metadata.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            meta["has_ocr"] = (proc_dir / "ocr_result.json").exists()
            docs.append(meta)
    return {"documents": docs}


@app.get("/documents/{username}/{proc_id}")
async def get_document(username: str, proc_id: str):
    """Get document metadata + OCR result if available."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    meta_file = dest / "metadata.json"
    result = json.loads(meta_file.read_text()) if meta_file.exists() else {}

    ocr_file = dest / "ocr_result.json"
    if ocr_file.exists():
        result["ocr_result"] = json.loads(ocr_file.read_text())

    return result


@app.get("/documents/{username}/{proc_id}/file")
async def download_file(
    username: str,
    proc_id: str,
    download: bool = Query(default=False, description="Force download instead of inline view"),
):
    """View or download the original uploaded file."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    files = [f for f in dest.iterdir() if f.name not in ("metadata.json", "ocr_result.json")]
    if not files:
        raise HTTPException(404)

    if download:
        return FileResponse(files[0], filename=files[0].name)
    return FileResponse(
        files[0],
        filename=files[0].name,
        content_disposition_type="inline",
    )


@app.post("/bridge/{proc_id}")
async def bridge_to_openfile(
    proc_id: str,
    username: str = Query(...),
    tax_return_id: str = Query(...),
    _auth: str = Depends(require_auth),
):
    """Bridge OCR results to OpenFile populated_data table."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404, f"Document {proc_id} not found for user {username}")

    ocr_file = dest / "ocr_result.json"
    if not ocr_file.exists():
        raise HTTPException(400, f"No OCR result for {proc_id}. Run /analyze first.")

    ocr_data = json.loads(ocr_file.read_text())
    ocr_fields = ocr_data.get("fields", {})

    try:
        result = write_populated_data(tax_return_id, ocr_fields)
    except Exception as e:
        raise HTTPException(502, f"Failed to write to OpenFile DB: {str(e)}")

    return result


@app.post("/bridge/{proc_id}/preview")
async def preview_bridge(
    proc_id: str,
    username: str = Query(...),
):
    """Preview the W2 payload that would be written to OpenFile (dry run)."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    ocr_file = dest / "ocr_result.json"
    if not ocr_file.exists():
        raise HTTPException(400, "No OCR result. Run /analyze first.")

    ocr_data = json.loads(ocr_file.read_text())
    return {"w2_payload": ocr_to_w2_payload(ocr_data.get("fields", {}))}


@app.delete("/documents/{username}/{proc_id}")
async def delete_document(username: str, proc_id: str, _auth: str = Depends(require_auth)):
    """Delete a document and all associated files."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    import shutil
    shutil.rmtree(dest)
    return {"deleted": proc_id}
