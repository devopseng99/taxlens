# TaxLens — Agentic Tax Intelligence Platform

## Overview

TaxLens is a multi-tenant SaaS tax platform: document intake, OCR, computation, PDF generation, and MCP server. Deployed on K8s with Dolt (versioned MySQL-compatible database) for multi-tenant data isolation.

| Component | Details |
|-----------|---------|
| API | Python FastAPI (uvicorn, port 8000) |
| Frontend | Nginx static (port 80) |
| Database | Dolt SQL Server (port 3306, StatefulSet) |
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
  ├── TenantContextMiddleware (X-API-Key → tenant_id via Dolt)
  ├── POST /api/upload → local PVC
  ├── POST /api/analyze/{proc_id} → Azure DI → PVC
  ├── POST /api/tax-draft → tax_engine.compute_tax() → pdf_generator → PVC
  ├── GET  /api/tax-draft/{id}/pdf/{form} → filled IRS PDF
  ├── POST /api/bridge/{proc_id} → OpenFile populated_data (psycopg2)
  ├── GET  /api/whoami → tenant context from API key
  ├── /admin/* → tenant provisioning (X-Admin-Key)
  └── /api/mcp → MCP StreamableHTTP (7 tools)

taxlens-dolt:3306 (StatefulSet)
  ├── 9 tables: tenants, users, api_keys, oauth_clients, oauth_tokens,
  │             tax_drafts, documents, plaid_items, tenant_plans
  ├── Git-like version control (dolt_commit, dolt_log, dolt_diff)
  └── PV at /opt/k8s-pers/vol1/taxlens-dolt
```

## Key Source Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, middleware stack, lifespan, route mounts |
| `app/auth.py` | Dual-mode auth (Dolt multi-tenant or legacy env-var) |
| `app/admin_routes.py` | Tenant provisioning API (/admin prefix) |
| `app/tax_routes.py` | Tax draft CRUD + PDF download endpoints |
| `app/tax_engine.py` | Federal 1040 + multi-state computation engine |
| `app/tax_config.py` | 2025 brackets, rates, constants |
| `app/pdf_generator.py` | Fill IRS fillable PDFs via pypdf |
| `app/mcp_server.py` | MCP server (7 tools, 2 resources) |
| `app/templates/*.pdf` | 11 official IRS/IL fillable PDF templates |
| `app/ocr.py` | Azure Document Intelligence client |
| `app/bridge.py` | OCR → OpenFile DB bridge |
| `app/db/connection.py` | aiomysql pool (min=2, max=5), DOLT_ENABLED flag |
| `app/db/schema.sql` | Full multi-tenant schema (9 tables) |
| `app/db/migrate.py` | Idempotent schema migration on startup |
| `app/db/*_repo.py` | Repository CRUD modules (7 repos) |
| `app/db/versioning.py` | Dolt commit/log/diff/history helpers |
| `app/middleware/tenant_context.py` | Extract tenant from API key, set request.state |
| `frontend/index.html` | Tabbed UI (Documents, Tax Drafts, Smoke Tests) |

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/health` | None | Health + version + dolt_enabled |
| GET | `/api/whoami` | API Key | Tenant context from key |
| POST | `/api/upload` | API Key | Upload document (multipart) |
| POST | `/api/analyze/{proc_id}` | API Key | Run Azure OCR |
| GET | `/api/documents/{username}` | API Key | List documents |
| POST | `/api/tax-draft` | API Key | Create tax draft (compute + PDF) |
| GET | `/api/tax-draft/{id}` | API Key | Get draft summary |
| GET | `/api/tax-draft/{id}/pdf/{form}` | API Key | Download PDF |
| POST | `/admin/tenants` | Admin Key | Create tenant + user + API key |
| GET | `/admin/tenants` | Admin Key | List all tenants |
| GET | `/admin/tenants/{id}/stats` | Admin Key | Tenant usage stats |
| POST | `/admin/tenants/{id}/api-keys` | Admin Key | Create API key |
| GET | `/admin/history` | Admin Key | Dolt commit log |

## Testing

```bash
# Run all 198 tests
PYTHONPATH=app python3 -m pytest tests/ -v

# Run 31-scenario smoke test
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

| Secret | Namespace | Keys |
|--------|-----------|------|
| `azure-docai` | taxlens | endpoint, key |
| `taxlens-admin` | taxlens | admin-key |

## Multi-Tenant Auth

- **Dolt mode** (DOLT_HOST set): X-API-Key validated via SHA-256 hash against api_keys table. Returns tenant_id, tenant_slug, user_id.
- **Legacy mode** (DOLT_HOST empty): X-API-Key validated against TAXLENS_API_KEYS env var. tenant_id="default".
- **Admin routes**: X-Admin-Key header validated against TAXLENS_ADMIN_KEY env var.
- **Unauthenticated**: /health, /docs, /openapi.json, /mcp paths skip auth.

## Dolt Gotchas

- `plan` is a MySQL reserved word — use `plan_tier`
- Root user is localhost-only — must CREATE USER for pod-to-pod access
- Config uses `data_dir:` not `databases:` array
- ALTER TABLE needs explicit `dolt_commit` + pool restart to take effect
- Comment lines in SQL before first CREATE cause migration to skip that table (strip comments before semicolon split)
- `key_prefix VARCHAR(8)` too small for `tlk_` prefix — use VARCHAR(12)

## Constraints

- Max upload: 30MB
- Azure F0 tier: 500 pages/month free
- Budget cap: $25/month on rg-taxoptics
- Node: mgplcb05 only (local PV)
- API memory: 192Mi request / 384Mi limit
- Dolt memory: 128Mi request / 256Mi limit
- pypdf `PdfWriter(clone_from=reader)` required — `append_pages_from_reader` drops AcroForm
