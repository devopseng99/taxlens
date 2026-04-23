# TaxLens — Next Steps

Updated: 2026-04-23 (v3.2.0)

## Completed
- [x] Wave 1-4: Deploy, bridge, E2E, multi-form OCR
- [x] Wave 5: Tax computation engine + PDF generation (1040, Schedules A/B/D, IL-1040)
- [x] Wave 5b: Business income (Schedule C, SE tax, QBI deduction, Schedule C/SE PDFs)
- [x] Wave 5c: pypdf fillable IRS templates (replaced ReportLab canvas PDFs)
- [x] 20-scenario smoke test suite (all passing, including 5 custom filing cases)
- [x] 5 custom hr1 drafts (nurse+tutor, retired couple, gig worker, real estate agent, crypto trader)
- [x] PDF template validation against official IRS 26f25 tax-refs
- [x] Playwright E2E UI + PDF header verification
- [x] Frontend redesign with tabbed interface (Documents, Tax Drafts, Smoke Tests)
- [x] NIIT (3.8%) + Additional Medicare Tax (0.9%) in engine + PDF
- [x] Schedule C home office line + Schedule D proceeds/cost basis
- [x] 43 pytest unit tests + 9 auth tests + 4 OCR fixture tests
- [x] API key auth layer (X-API-Key header, disabled by default)
- [x] W-2/1099-INT OCR fixture tests (4 scenarios, no Azure needed)
- [x] Schedule 2 PDF (Form 1040) — Additional Taxes (SE + NIIT + Add'l Medicare)
- [x] Form 8959 PDF — Additional Medicare Tax (Parts I-V with withholding reconciliation)
- [x] Form 8960 PDF — Net Investment Income Tax (Parts I-III for individuals)
- [x] Conditional form generation (only when surtaxes apply)
- [x] 58 total unit tests passing (49 engine + 9 auth)
- [x] Multi-state support — 10 states (IL, CA, NY, NJ, PA, NC, GA, OH, TX, FL)
- [x] Multi-state worker orchestration (nonresident + resident with credits)
- [x] Reciprocal agreements (IL↔WI/IA/KY/MI, NJ↔PA, PA↔OH/IN/MD/VA/WV)
- [x] StateWageInfo + W-2 OCR StateTaxInfos parsing
- [x] Generic ReportLab state PDF summary for non-IL states
- [x] 42 new state tax tests + 5 new smoke tests (100 total tests, 25 smoke tests)
- [x] Built, deployed, verified (v0.8.0)
- [x] Extended OCR parsers: 1099-DIV, 1099-NEC, 1098, 1099-B structured import
- [x] Auto-detect form type from Azure doc_type
- [x] 26 new parser unit tests + 5 fixtures + 4 smoke tests (126 total tests, 29 smoke tests)
- [x] Built, deployed, verified (v0.8.5)
- [x] MCP server with 7 tools + 2 resources via StreamableHTTP at `/api/mcp`
- [x] DNS rebinding protection, stateless HTTP, FastAPI lifespan integration
- [x] 19 MCP tool handler unit tests (145 total tests, 29 smoke tests)
- [x] Built, deployed, verified (v0.9.0)
- [x] Plaid integration — connect brokerages, sync investment transactions + dividends
- [x] Fernet-encrypted access_token storage, Plaid Link frontend, K8s secrets template
- [x] plaid_item_ids in TaxDraftRequest merges Plaid data into tax computation
- [x] 18 Plaid unit tests + 2 smoke tests (163 total tests, 31 smoke tests)
- [x] Built, deployed, verified (v1.0.0)
- [x] Wave 11a: Dolt StatefulSet + schema + 9 tables + connection pool (aiomysql)
- [x] Wave 11a: 7 repository modules (tenant, user, api_key, draft, document, plaid, oauth)
- [x] Wave 11a: Dolt version control hooks (commit, log, diff, history, tenant-scoped rollback)
- [x] Wave 11b: Multi-tenant middleware (X-API-Key → tenant_id via SHA-256 hash)
- [x] Wave 11b: Admin provisioning API (create tenant + user + API key + PVC dir in one call)
- [x] Wave 11b: Data migration script (PVC scan → Dolt tables)
- [x] Wave 11b: Graceful degradation (Dolt optional, falls back to legacy single-tenant)
- [x] Wave 11b: 35 new tests (21 repo + 8 middleware + 6 admin), 198 total
- [x] Built, deployed, verified (v2.0.0) — 2 test tenants provisioned, Dolt history tracking
- [x] Wave 12: A2UI Tenant Portal (v2.1.0) — FastAPI+Jinja2+HTMX, 6 pages, dark theme, deployed to taxlens-portal ns
- [x] Wave 12: Portal chat widget (v2.2.0) — SSE streaming, floating panel, tool indicators, agent URL config
- [x] Wave 13: Claude Support Agent (v1.0.0) — git-backed JSONL conversations, MCP tool proxy, SSE streaming
- [x] Wave 13: 31 new tests (20 git store + 11 route), 229 total across platform
- [x] Wave 13: Deployed to taxlens-agent ns on mgplcb03, CF tunnel route configured
- [x] Wave 13: Admin oversight API (tenant stats, search via git grep, full conversation read)

## Wave 12 — A2UI Tenant Portal (COMPLETE — v2.2.0)

Deployed at https://taxlens-portal.istayintek.com (namespace `taxlens-portal`, mgplcb05).
Repo: https://github.com/devopseng99/taxlens-portal

**Delivered:**
- Login with API key → /api/whoami → encrypted session cookie (itsdangerous)
- Dashboard with stats, tax drafts list/detail/PDF proxy
- MCP-driven computation forms (auto-generated from tool schemas; JSON-RPC blocked by DNS rebinding — deferred)
- Dolt history timeline, API key/OAuth client management, admin tenant views
- Chat widget for Claude agent integration (SSE, tool indicators)

## Wave 13 — Git-Backed Claude Support Agent (COMPLETE — v1.0.0)

Deployed at https://taxlens-agent.istayintek.com (namespace `taxlens-agent`, mgplcb03).
Repo: https://github.com/devopseng99/taxlens-agent

**Delivered:**
- Git conversation store (JSONL + auto git commit, fcntl locking, per-tenant repos)
- MCP tool proxy (JSON-RPC to taxlens-api, tenant username scoping)
- Claude conversation engine (claude-sonnet-4-20250514, 5-round tool use loop, SSE output)
- Portal chat widget (floating button, SSE client, tool use indicators)
- Admin oversight API (tenant stats, full read, git grep search)
- Rate limiting (10 msg/min per tenant, in-memory)
- **Known issue:** Requires funded Anthropic account — billing error if credits low

## Wave 14 — Billing, Metering & Launch (COMPLETE — v3.0.0)

**Delivered:**
- Async buffered metering logger (6 event types, flush every 30s/100 events)
- Token bucket rate limiting per tenant (3 plan tiers, Dolt-backed with 5min cache)
- Stripe billing (checkout, webhook, portal, metered add-ons) — gracefully disabled when not configured
- Self-service onboarding (Stripe checkout → webhook → auto-provision tenant + API key + plan)
- Monitoring endpoints: `/usage/me` (tenant-facing), `/admin/monitoring/*` (platform admin)
- Usage aggregation CronJob (hourly, Dolt-backed)
- MeteringRateLimitMiddleware with correct LIFO ordering (innermost, after TenantContext)
- 39 new tests (7 metering + 19 rate limiter + 13 billing), 237 total
- 8 new E2E tests (T41-T48), 48 total portal E2E tests
- v3.0.0 deployed and verified

## Wave 15 — PostgreSQL + PostgREST Migration (DEPLOYED — v3.1.1)

Replaces Dolt with PostgreSQL 16 + PostgREST v12 in isolated `taxlens-db` namespace.

**Delivered (code):**
- db-flyway-admin migration engine (`db/flyway/`) — reusable Flyway-inspired module with CLI
- 4 PostgreSQL migrations: schema (12 tables), roles + RLS, functions, audit triggers
- PostgREST HTTP client (`db/postgrest_client.py`) — replaces 7 repo modules + connection.py
- JWT + RLS role architecture (authenticator, app_anon, app_tenant, app_admin)
- Auth cache (OrderedDict LRU, 256 entries, 60s TTL)
- All middleware, routes, services converted from Dolt/aiomysql to PostgREST/httpx
- Helm chart for taxlens-db namespace (PG StatefulSet + PostgREST Deployment + Flyway Job + NetworkPolicy)
- Updated taxlens API Helm chart (PostgREST env vars, removed Dolt templates)
- E2E test hardening (retry login, 45s timeouts, _ensure_logged_in guards)
- 27 new unit tests (14 flyway + 7 PostgREST client + 6 auth cache), 242 total
- Deleted 11 old Dolt files (7 repos + connection + migrate + versioning + schema.sql)

**Deployed (infrastructure):**
- [x] Node directory `/opt/k8s-pers/vol1/psql-taxlens` on mgplcb05 (chmod 777, uid 999)
- [x] Namespace `taxlens-db` with Helm ownership annotations
- [x] Secrets: `taxlens-db-credentials` + `taxlens-db-jwt` (both namespaces)
- [x] PostgreSQL 16-alpine StatefulSet running (PV correctly bound to `data-taxlens-pg-0`)
- [x] PostgREST v12.2.3 running (13 relations, 5 functions, 12 relationships loaded)
- [x] All 4 migrations applied via `kubectl exec psql`
- [x] API v3.1.1 deployed with `POSTGREST_URL` + `DB_JWT_SECRET` env vars
- [x] Seed data: 1 tenant, 1 user, 2 API keys (admin + E2E test)
- [x] Auth latency: **68ms** (was 30,000ms+ with Dolt) — **384x improvement**

**Critical fixes during deployment:**
- Pure ASGI middleware (BaseHTTPMiddleware deadlocked with nested async httpx)
- StatefulSet PVC naming (`data-{name}-0`, not custom name)
- PostgREST env var ordering (`PG_PASSWORD` before `PGRST_DB_URI`)
- Namespace Helm ownership annotations required for pre-created namespaces

**Test results (post-deployment):**
- 242/242 unit tests pass (3.17s)
- 52/59 E2E tests pass (7 minor: history page, admin rendering, field expectations)
- Portal login: working with spinner (v2.3.0)

**Remaining minor E2E failures (non-blocking):**
- T12: History page not implemented in portal yet
- T15/T16: Admin pages don't render tenant list/health in current portal version
- T39: Test expects >1 tenant (only 1 seeded)
- T52: whoami doesn't return `username`/`role` fields (test expectation mismatch)
- T53/T54: Playwright session state carryover between tests

### Plan Tiers

| Feature | Free ($0) | Starter ($29/mo) | Professional ($99/mo) | Enterprise ($299/mo) |
|---------|-----------|-------------------|-----------------------|----------------------|
| Tax compute | Std deduction + W-2 | All schedules | All schedules | All schedules |
| Doc upload | W-2 only (unlimited) | All forms | All forms | All forms |
| Filings/year | 1 | Unlimited | Unlimited | Unlimited |
| API calls/min | 10 | 30 | 120 | 600 |
| Computations/day | 5 | 50 | 500 | Unlimited |
| OCR pages/month | 20 | 100 | 1,000 | 10,000 |
| Agent messages/day | 0 | 100 | 500 | Unlimited |
| MCP server | No | Yes | Yes | Yes |
| Plaid sync | No | No | Yes | Yes |
| Multi-state | No | No | Yes | Yes |
| Users | 1 | 3 | 10 | Unlimited |
| Early access | No | No | No | Yes |

## Wave 16 — Feature Flags + Free Tier (DEPLOYED — v3.2.0)

Per-tenant feature gating with NIST/IRS-compliant free tier.

**Delivered:**
- [x] V005 migration: `tenant_features` table (10 boolean flags, 4 quotas, JSONB form allowlist)
- [x] RLS policies (tenant reads own, admin reads/writes all) + audit trigger
- [x] `upsert_tenant_features` RPC function
- [x] Free tier added to `PLAN_DEFAULTS` and `PLAN_TIERS`
- [x] `TIER_FEATURES` constant mapping plan → feature defaults
- [x] `FeatureGateMiddleware` (pure ASGI, 256-entry LRU cache, 5-min TTL)
- [x] `POST /billing/onboarding/free` self-service signup (IP rate-limited 10/hr)
- [x] Admin API: GET/PUT `/admin/tenants/{id}/features` + early-access toggle
- [x] `provision_tenant()` inserts `tenant_features` row on creation
- [x] Stripe webhook `_sync_plan_limits()` syncs features on plan change
- [x] Feature cache invalidation on admin updates
- [x] Existing tenants backfilled (enterprise + professional = all features)
- [x] 16 new unit tests (258 total), 59/59 E2E (T41 updated for 4 tiers)
- [x] API v3.2.0 deployed and verified

## v3.1.2 — Logging Suppression (DEPLOYED)

Reduces disk I/O by suppressing INFO-level logging across all 5 TaxLens pods.

**Changes:**
- [x] taxlens-api: uvicorn `--log-level warning`, httpx/httpcore/uvicorn.access suppressed
- [x] taxlens-portal: uvicorn `--log-level warning`, httpx/httpcore/uvicorn.access suppressed
- [x] taxlens-agent: `logging.basicConfig(level=WARNING)`, httpx/httpcore/uvicorn.access suppressed
- [x] taxlens-pg: `log_min_messages=warning`, `log_checkpoints=off`, `log_connections=off`, `log_disconnections=off`
- [x] taxlens-postgrest: `PGRST_LOG_LEVEL=warn`
- [x] Metering pseudo-tenant skip (FK constraint fix for `default`/`__admin__`)
- [x] CronJob `aggregate_usage.py` rewritten for PostgREST (was Dolt/aiomysql)
- [x] `COPY scripts/ /app/scripts/` added to Dockerfile for CronJob access
- [x] All 3 repos committed and pushed, releases created (API v3.1.2, Portal v2.3.1, Agent v1.0.1)

## Upcoming Waves

### Wave 17 — emDash Landing Page CMS (Cloudflare Workers)
- emDash v0.1.0 (Astro 6 + CF Workers + D1 + R2) at `taxlens.istayintek.com`
- Marketing pages: hero, features, pricing (4 tiers), how-it-works, blog
- Free signup form → `POST /billing/onboarding/free` → redirect to portal
- CF API token with Workers Scripts, D1, R2, KV, Routes permissions
- Replace current nginx K8s service with CF Worker route

### Wave 18 — Public Tax Estimator Tools (CF Worker Functions)
- Client-side-only tax calculators on the landing page (no login, no data stored)
- Refund estimator, filing status advisor, bracket visualizer, SE tax calculator
- Marketing tools only — actual filing requires login (free or paid tier)

### Wave 19 — Subscription Portal UX + Early Access
- Feature-aware dashboard (hide/show based on `tenant_features`)
- Upgrade flow: plan comparison → Stripe checkout → features unlock
- Usage dashboard with visual progress bars per resource
- Early access toggle for Enterprise tenants (opt-in to beta features)
- 6 new E2E tests (T60-T65), target 65/65

## Future Enhancements

- **MCP OAuth 2.0 implementation** (deferred — API key auth working)
- **Multi-replica rate limiting:** Redis-backed token bucket for horizontal scaling
- **Production Stripe:** Enable test mode → live mode cutover, real product creation
- **Prometheus metrics:** Full `/metrics` endpoint with Grafana dashboards
- **API reference docs:** OpenAPI spec + MCP integration guide
- **PostgREST auto-generated OpenAPI:** Expose PostgREST's /api docs for DB schema
