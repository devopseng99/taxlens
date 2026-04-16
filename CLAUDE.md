# TaxLens — Agentic Tax Intelligence Platform

## Overview

TaxLens is a document intake and OCR service for tax documents. It stores files locally on K8s PVC and uses Azure Document Intelligence for structured data extraction.

| Component | Details |
|-----------|---------|
| API | Python FastAPI (uvicorn, port 8000) |
| Storage | Local PVC at `/opt/k8s-pers/vol1/taxlens-docs` on mgplcb05 |
| OCR | Azure Document Intelligence (45+ prebuilt tax models) |
| Namespace | `taxlens` |
| URL | https://dropit.istayintek.com |

## Architecture

```
User → dropit.istayintek.com → CF Tunnel → taxlens-api:8000
                                              ├── POST /api/upload → local PVC
                                              ├── POST /api/analyze/{proc_id} → Azure DI → PVC
                                              └── GET  /api/documents/{user} → list
```

Documents are stored at: `/{username}/{proc_id}/{timestamp}_{proc_id}.{ext}`

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/upload` | Upload document (multipart: file, username, doc_type) |
| POST | `/api/analyze/{proc_id}?username=X&model_id=Y` | Run Azure OCR |
| GET | `/api/documents/{username}` | List user's documents |
| GET | `/api/documents/{username}/{proc_id}` | Get metadata + OCR result |
| GET | `/api/documents/{username}/{proc_id}/file` | Download original file |
| DELETE | `/api/documents/{username}/{proc_id}` | Delete document |

## Azure OCR Models

- Auto-detect: `prebuilt-tax.us` (routes to correct model)
- W-2: `prebuilt-tax.us.w2`
- 1099 (21 variants): `prebuilt-tax.us.1099{INT,MISC,NEC,DIV,...}`
- 1040 + schedules: `prebuilt-tax.us.1040`

## Build & Deploy

```bash
# 1. Provision node directories
bash scripts/provision-node-dirs.sh

# 2. Build, transfer, deploy
bash scripts/build-and-deploy.sh

# 3. Add CF tunnel entry
# dropit.istayintek.com → taxlens-api.taxlens.svc.cluster.local:8000
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
- No auth yet — username is self-reported in upload form
