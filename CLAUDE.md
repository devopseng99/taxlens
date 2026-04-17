# TaxLens — Agentic Tax Intelligence Platform

## Overview

TaxLens is a full-stack tax document intake, OCR, computation, and PDF generation platform. It stores files locally on K8s PVC, uses Azure Document Intelligence for structured data extraction, computes federal + Illinois state taxes, and generates filled official IRS PDF forms.

| Component | Details |
|-----------|---------|
| API | Python FastAPI (uvicorn, port 8000) |
| Frontend | Nginx static (port 80) |
| Storage | Local PVC at `/opt/k8s-pers/vol1/taxlens-docs` on mgplcb05 |
| OCR | Azure Document Intelligence (45+ prebuilt tax models) |
| PDF Engine | pypdf (fillable IRS templates) + ReportLab (summary page) |
| Namespace | `taxlens` |
| API URL | https://dropit.istayintek.com |
| UI URL | https://taxlens.istayintek.com |

## Architecture

```
User → taxlens.istayintek.com → CF Tunnel → taxlens-ui:80 (nginx)
User → dropit.istayintek.com  → CF Tunnel → taxlens-api:8000 (FastAPI)

taxlens-api:8000
  ├── POST /api/upload → local PVC
  ├── POST /api/analyze/{proc_id} → Azure DI → PVC
  ├── POST /api/tax-draft → tax_engine.compute_tax() → pdf_generator → PVC
  ├── GET  /api/tax-draft/{id}/pdf/{form} → filled IRS PDF
  └── POST /api/bridge/{proc_id} → OpenFile populated_data (psycopg2)
```

## Key Source Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, upload/analyze/bridge endpoints |
| `app/tax_routes.py` | Tax draft CRUD + PDF download endpoints |
| `app/tax_engine.py` | Federal 1040 + IL-1040 computation engine |
| `app/tax_config.py` | 2025 brackets, rates, constants |
| `app/pdf_generator.py` | Fill IRS fillable PDFs via pypdf |
| `app/templates/*.pdf` | 8 official IRS/IL fillable PDF templates |
| `app/ocr.py` | Azure Document Intelligence client |
| `app/bridge.py` | OCR → OpenFile DB bridge |
| `frontend/index.html` | Tabbed UI (Documents, Tax Drafts, Smoke Tests) |
| `tests/smoke_test_tax_drafts.sh` | 20-scenario E2E test suite |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/upload` | Upload document (multipart) |
| POST | `/api/analyze/{proc_id}` | Run Azure OCR |
| GET | `/api/documents/{username}` | List documents |
| GET | `/api/documents/{username}/{proc_id}` | Doc detail + OCR |
| GET | `/api/documents/{username}/{proc_id}/file` | Download original |
| DELETE | `/api/documents/{username}/{proc_id}` | Delete document |
| POST | `/api/bridge/{proc_id}` | Write OCR to OpenFile DB |
| POST | `/api/bridge/{proc_id}/preview` | Preview bridge payload |
| POST | `/api/tax-draft` | Create tax draft (compute + PDF) |
| GET | `/api/tax-draft/{id}?username=X` | Get draft summary |
| GET | `/api/tax-draft/{id}/pdf/{form}?username=X` | Download PDF |
| GET | `/api/tax-draft/{id}/pdfs?username=X` | List available PDFs |
| GET | `/api/tax-drafts/{username}` | List all drafts |

## Testing

See `TESTING.md` for full commands reference.

```bash
# Run 20-scenario smoke test
bash tests/smoke_test_tax_drafts.sh

# Verify templates match IRS originals
for f in app/templates/*.pdf; do sha256sum "$f"; done
```

## Build & Deploy

```bash
bash scripts/build-and-deploy.sh
# Or manually: podman build → podman save → ssh ctr import → helm upgrade
```

## Secrets

K8s secret `azure-docai` in namespace `taxlens`:
- `endpoint`: Azure Document Intelligence endpoint URL
- `key`: Azure API key

## Constraints

- Max upload: 30MB
- Azure F0 tier: 500 pages/month free
- Budget cap: $25/month on rg-taxoptics
- Node: mgplcb05 only (local PV)
- No auth yet — username is self-reported
- pypdf `PdfWriter(clone_from=reader)` required — `append_pages_from_reader` drops AcroForm
