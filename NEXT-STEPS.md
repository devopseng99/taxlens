# TaxLens — Next Steps

Updated: 2026-04-23 (v3.11.0)

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

## Wave 17 — Landing Page on Cloudflare Workers (DEPLOYED — v1.0.0)

Astro 6 SSR site on CF Workers replacing nginx K8s service.
Repo: https://github.com/devopseng99/taxlens-landing
Live: https://taxlens.istayintek.com

**Delivered:**
- [x] 12 marketing pages (all returning 200):
  - `/` landing, `/features`, `/pricing` (4 tiers), `/how-it-works`
  - `/signup` (fetch to `/billing/onboarding/free`), `/for-professionals`
  - `/blog` (3 seed posts), `/contact`, `/tools` (placeholder)
  - `/login` (redirect to portal), `/legal/terms`, `/legal/privacy`
- [x] CF Workers deployment: `taxlens-landing.gitit102.workers.dev`
- [x] Workers Route: `taxlens.istayintek.com/*` → `taxlens-landing` worker
- [x] D1 database `taxlens-landing-db` + R2 bucket `taxlens-landing-assets`
- [x] `nodejs_compat` flag for Node.js built-in support
- [x] Old taxlens-ui nginx scaled to 0 (reclaimed 32Mi)
- [x] CF API token with `CLOUDFLARE_ACCOUNT_ID` env var pattern

**Deferred:**
- emDash CMS admin panel (SQLite adapter incompatible with Workers — needs D1 adapter)
- Blog content management (currently hardcoded Astro components)

## Wave 18 — Free Tax Calculator Tools (DEPLOYED — v1.1.0)

4 client-side JS calculators on the landing page. No login, no API, no data stored.

**Delivered:**
- [x] `/tools/refund-estimator` — 2025 brackets, standard deduction, CTC, effective/marginal rates
- [x] `/tools/filing-status` — Interactive questionnaire → recommended status + explanation
- [x] `/tools/brackets` — Color-coded stacked bar chart with real-time bracket breakdown
- [x] `/tools/se-tax` — SE tax: 92.35% base, SS cap ($176,100), Medicare, 50% deduction, W-2 offset
- [x] `/tools` index updated: all 4 tools linked (was "Coming Soon")
- [x] All 16 pages returning 200 on production

## Wave 19 — Subscription Portal UX + Early Access (DEPLOYED — v3.3.0)

Feature-aware portal with upgrade flow and early access toggles.

**Delivered:**
- [x] Feature-aware dashboard: fetches `tenant_features` via admin API, shows 10 features with enabled/locked badges
- [x] Upgrade flow: `/billing/upgrade` with 4-tier plan comparison → Stripe checkout redirect → `/billing/success`
- [x] Usage dashboard: `/usage` with color-coded progress bars (green/yellow/red), upgrade prompts at limits
- [x] Early access: `/settings/early-access` with opt-in checkboxes for 3 beta features (enterprise only)
- [x] Sidebar: new Billing section (Usage, Early Access, Plans & Upgrade)
- [x] CSS: progress bars, upgrade CTAs, feature-locked cards, lock icons in `base.html`
- [x] 6 new E2E tests (T60-T65), 65/65 total passing
- [x] Portal rebuilt, image imported to mgplcb05, deployed

**New files:**
- `app/routes/billing.py` — plan tiers, upgrade page, Stripe checkout redirect, success page
- `app/routes/usage.py` — usage meters with plan limits, progress bar data
- `app/templates/billing/upgrade.html` — 4-tier plan comparison grid
- `app/templates/billing/success.html` — post-checkout celebration
- `app/templates/usage.html` — progress bars with color coding
- `app/templates/settings/early_access.html` — beta feature toggles

**Modified files:**
- `app/routes/dashboard.py` — fetches features, passes to template
- `app/routes/settings.py` — early access route + beta feature list
- `app/main.py` — includes billing + usage routers
- `app/templates/base.html` — sidebar billing section + CSS
- `app/templates/dashboard.html` — feature-gated UI with lock icons

## Wave 20 — Production Hardening (DEPLOYED — v3.4.0 API + v2.6.0 Portal)

Security, observability, and operational readiness improvements.

**Delivered:**
- [x] DB password moved from values.yaml to K8s Secret (`openfile-postgresql`)
- [x] URL env vars: `TAXLENS_PORTAL_URL`, `TAXLENS_API_URL`, `TAXLENS_LANDING_URL` (15+ hardcoded instances replaced)
- [x] Deep health check: `/api/health` pings PostgREST, returns `degraded` if DB unreachable
- [x] Daily PG backup CronJob (`taxlens-pg-backup`, 3 AM, 7-day retention, pg_dump to hostPath)
- [x] CSRF double-submit cookie protection on portal
- [x] Security headers: CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- [x] Branded error pages (error.html with base.html layout)
- [x] Azure OCR graceful degradation (`os.getenv` + `OCR_ENABLED` flag)
- [x] V006 migration: 7 DB indexes (api_keys, oauth_tokens, usage_events, billing_customers, tenant_features)
- [x] 258/258 unit tests, 65/65 E2E tests passing

## Wave 21 — Observability & Operations (DEPLOYED — v3.5.0 API)

Request tracing, metrics, structured logging, and IP rate limiting.

**Delivered:**
- [x] Prometheus `/metrics` endpoint via `prometheus-fastapi-instrumentator` — request count, latency histograms, status codes
- [x] `X-Request-ID` correlation middleware — generates UUID4 per request or accepts client-provided ID, returned in response header
- [x] Structured JSON logging via `python-json-logger` — all log output is machine-parseable JSON with timestamp, level, logger fields
- [x] IP-based rate limiting on public endpoints — `/health` (60/min), `/billing/plans` (30/min), `/billing/onboarding/free` (10/min)
- [x] Reusable `IPRateLimiter` class with per-IP token buckets and 4096-IP eviction cap
- [x] `/metrics` and `/health` excluded from Prometheus instrumentation (avoids noise)
- [x] Middleware stack: CORS → RequestID → TenantContext → FeatureGate → MeteringRateLimit
- [x] 273/273 unit tests (15 new), 65/65 E2E tests passing

**New files:**
- `app/middleware/request_id.py` — pure ASGI request ID middleware
- `tests/test_observability.py` — 15 tests (request ID, IP rate limiter, JSON logging, Prometheus)

**Modified files:**
- `app/main.py` — v3.5.0, Prometheus instrumentator, RequestID middleware, IP rate limiting in exempt paths, JSON logging setup
- `app/rate_limiter.py` — `IPRateLimiter` class, `IP_RATE_LIMITS` config
- `app/requirements.txt` — `prometheus-fastapi-instrumentator>=7.0.0`, `python-json-logger>=3.0.0`
- `app/middleware/tenant_context.py` — `/metrics` added to skip paths
- `Dockerfile` — `--no-access-log` flag (JSON formatter handles logging)

## Wave 22 — Revenue Activation (DEPLOYED — v3.6.0 API)

Stripe billing integration activated in test mode.

**Delivered:**
- [x] K8s secret `taxlens-stripe` with test key + webhook secret
- [x] Stripe webhook endpoint registered (`we_1TPT6kGghEIUa3k8AK87ALmk`) — 5 event types
- [x] Stripe enabled in Helm values + deployment template
- [x] Price ID env vars via K8s secret (optional keys, populated via `scripts/setup-stripe-products.sh`)
- [x] `STRIPE_MODE` detection (test/live/disabled) exposed in `/api/health`
- [x] 275/275 unit tests (2 new billing mode tests), 65/65 E2E tests passing

**New files:**
- `scripts/setup-stripe-products.sh` — Creates Stripe products in Dashboard, patches K8s secret with price IDs

**Modified files:**
- `app/billing.py` — `STRIPE_MODE` constant for test/live detection
- `app/main.py` — Health endpoint includes `stripe_mode`
- `charts/taxlens/values.yaml` — `stripe.enabled: true`
- `charts/taxlens/templates/deployment.yaml` — Price ID env vars from secret (optional)

**Stripe Products (COMPLETED):**
- Starter: `prod_UOGelXMZCrPHkV` → `price_1TPU7uGghEIUa3k8ek4hg4Qc` ($29/mo)
- Professional: `prod_UOGeNG1PnY24NL` → `price_1TPU7zGghEIUa3k8uQ672L8W` ($99/mo)
- Enterprise: `prod_UOGfQ7Zot1FTns` → `price_1TPU85GghEIUa3k83hniJ6iq` ($299/mo)
- Checkout flow verified: `POST /billing/checkout` → valid Stripe Checkout session URL

## Wave 23 — Tax Engine Completeness (DEPLOYED — v3.7.0 API)

AMT, education credits, and QBI phase-out for complete 2025 federal computation.

**Delivered:**
- [x] AMT (Form 6251): SALT add-back, exemption phase-out, 26%/28% brackets, tentative minimum tax
- [x] AOTC ($2,500 max, 40% refundable) + LLC ($2,000 max, nonrefundable)
- [x] Education credit MAGI phase-out ($80K-$90K single, $160K-$180K MFJ, MFS ineligible)
- [x] QBI W-2 wage limitation phase-out ($50K/$100K range above threshold)
- [x] EducationExpense dataclass with per-student tracking
- [x] 291/291 unit tests (16 new), 65/65 E2E tests passing

**Modified files:**
- `app/tax_engine.py` — AMT computation, education credits, QBI phase-out, EducationExpense dataclass
- `app/tax_config.py` — AMT constants, education credit constants, QBI phase-out range

**New files:**
- `tests/test_wave23_tax.py` — 16 tests (5 AMT, 7 education credits, 4 QBI phase-out)

## Wave 24 — EITC (DEPLOYED — v3.8.0 API)

Earned Income Tax Credit — the largest refundable credit in the US tax system.

**Delivered:**
- [x] Full 2025 EITC computation: phase-in, plateau, phase-out for 0/1/2/3+ qualifying children
- [x] Max credits: $649 (0 children), $4,328 (1), $7,152 (2), $8,046 (3+)
- [x] MFJ higher phase-out thresholds ($17,740/$29,200 vs $10,620/$22,080)
- [x] MFS disqualification, investment income limit ($11,600)
- [x] SE income counts as earned income for EITC
- [x] Refundable credit: added to `line_33_total_payments`
- [x] Schedule EIC added to forms list when EITC claimed
- [x] 311/311 unit tests (20 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave24_eitc.py` — 20 tests (phase-in/out, children, MFJ, disqualification, SE income, refundable)

**Modified files:**
- `app/tax_config.py` — EITC constants (max credits, rates, thresholds, investment income limit)
- `app/tax_engine.py` — EITC computation, `eitc`/`eitc_earned_income` fields in TaxResult, added to payments + summary

## Wave 25 — CDCC + Saver's Credit (DEPLOYED — v3.9.0 API)

Child and Dependent Care Credit (Form 2441) and Retirement Savings Credit (Form 8880).

**Delivered:**
- [x] CDCC: AGI-based rate (35% → 20%), $3K/$6K expense limits, earned income cap
- [x] Saver's Credit: 3-tier (50%/20%/10%), $2K max contribution, MFJ doubled thresholds
- [x] Both nonrefundable: capped at remaining tax liability
- [x] DependentCareExpense and RetirementContribution dataclasses
- [x] Credit ordering: CTC → Education → CDCC → Saver's → EITC
- [x] 328/328 unit tests (17 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave25_credits.py` — 17 tests (8 CDCC, 9 Saver's Credit)

**Modified files:**
- `app/tax_config.py` — CDCC + Saver's Credit constants
- `app/tax_engine.py` — New dataclasses, computation, TaxResult fields, forms list

## Wave 26 — Estimated Tax Penalty (DEPLOYED — v3.10.0 API)

Form 2210 simplified short method — penalty for underpayment of estimated tax.

**Delivered:**
- [x] Penalty computation: 90% current year or 100% prior year safe harbor (110% if high AGI)
- [x] $1,000 threshold: no penalty if owed < $1,000
- [x] High AGI ($150K/$75K MFS) triggers 110% prior year requirement
- [x] Estimated payments + withholding reduce underpayment
- [x] Penalty = underpayment × 8% annual rate, added to amount owed
- [x] Optional prior_year_tax/prior_year_agi parameters (backward compatible)
- [x] 342/342 unit tests (14 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave26_penalty.py` — 14 tests (no penalty, penalty applies, high AGI, estimated payments, forms)

**Modified files:**
- `app/tax_config.py` — Form 2210 constants (threshold, rates, safe harbor percentages)
- `app/tax_engine.py` — Penalty computation, prior_year_tax/agi params, TaxResult fields

## Wave 27 — Credit Form PDFs (DEPLOYED — v3.11.0 API)

PDF generation for all 6 credits computed in Waves 23-26 that previously only appeared in JSON.

**Delivered:**
- [x] Form 6251 (AMT) — ReportLab summary with AMTI, exemption, tentative tax, AMT amount
- [x] Form 8863 (Education Credits) — AOTC refundable + nonrefundable, LLC
- [x] Schedule EIC (EITC) — earned income, AGI, qualifying children, credit amount
- [x] Form 2441 (CDCC) — AGI-based rate, care expenses, credit amount
- [x] Form 8880 (Saver's Credit) — AGI tier, contribution cap, credit amount
- [x] Form 2210 (Estimated Tax Penalty) — required payment, underpayment, penalty rate
- [x] Summary cover page enriched with Credits section (CTC, education, CDCC, Saver's, EITC)
- [x] Form 6251 and Form 8863 added to `forms_generated` in tax engine
- [x] `generate_all_pdfs()` conditionally produces each form
- [x] `tax_routes.py` file_map updated for all 6 new downloadable forms
- [x] 362/362 unit tests (20 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave27_pdfs.py` — 20 tests (3 AMT, 3 education, 3 EITC, 3 CDCC, 3 Saver's, 3 penalty, 2 summary)

**Modified files:**
- `app/pdf_generator.py` — 6 new generation functions, summary page credits section, generate_all_pdfs updates
- `app/tax_engine.py` — Form 6251/8863 added to forms_generated
- `app/tax_routes.py` — file_map expanded with 6 new form entries
- `app/main.py` — version bump to 3.11.0

## Future Enhancements

- **MCP OAuth 2.0 implementation** (deferred — API key auth working)
- **Multi-replica rate limiting:** Redis-backed token bucket for horizontal scaling
- **Stripe live mode:** Create full-access key, cutover from test → live
- **Grafana dashboards:** Wire Prometheus metrics to visual dashboards
- **API reference docs:** OpenAPI spec + MCP integration guide
- **PostgREST auto-generated OpenAPI:** Expose PostgREST's /api docs for DB schema
- **Landing page completion:** /about, /security, /for-businesses pages (from original spec)
- **Tax engine remaining:** Depreciation (Form 4562), annualized installment method
- **Audit risk scoring:** Statistical comparison to IRS norms by income bracket
- **Prior-year import:** Upload previous 1040 PDF → OCR extract → pre-populate current year
