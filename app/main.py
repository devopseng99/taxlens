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

app = FastAPI(
    title="TaxLens Document Intake API",
    version="0.1.0",
    docs_url="/docs",
    root_path="/api",
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


# --- Endpoints ---

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "storage_root": str(STORAGE_ROOT),
        "writable": STORAGE_ROOT.exists(),
        "auth_enabled": AUTH_ENABLED,
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

    # Save OCR result
    ocr_path = dest / "ocr_result.json"
    ocr_path.write_text(json.dumps(result["raw"], indent=2, default=str))

    ocr = OcrResult(
        proc_id=proc_id,
        model_id=model_id,
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
