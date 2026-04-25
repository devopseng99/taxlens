# TaxLens — Next Steps

Updated: 2026-04-25 (v3.56.0 — 77 waves complete)

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

## Wave 28 — Structured Dependent Model (DEPLOYED — v3.12.0 API)

Replaces integer `num_dependents` with structured `Dependent` records for accurate credit eligibility.

**Delivered:**
- [x] `Dependent` dataclass: first_name, last_name, SSN, DOB, relationship, months_lived_with, disabled, student
- [x] `age_at_year_end()` method for precise age calculation
- [x] `qualifies_ctc()` — under 17 at year end
- [x] `qualifies_eitc()` — under 19, or under 24 if student, or any age if disabled
- [x] `qualifies_cdcc()` — under 13, or any age if disabled
- [x] Engine derives `num_ctc_children`, `num_eitc_children`, `num_cdcc_dependents` from structured records
- [x] CTC uses `num_ctc_children` instead of `num_dependents`
- [x] EITC uses `num_eitc_children` instead of `num_dependents`
- [x] Full backward compatibility: `num_dependents` integer still works
- [x] `DependentInput` Pydantic model in API with DOB, relationship, disability flags
- [x] Summary JSON includes per-dependent credit eligibility breakdown
- [x] PDF summary shows dependent names when structured records provided
- [x] 391/391 unit tests (29 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave28_dependents.py` — 29 tests (4 age, 6 CTC, 6 EITC, 3 CDCC, 3 backward compat, 5 mixed, 2 summary)

**Modified files:**
- `app/tax_engine.py` — Dependent dataclass, compute_tax accepts dependents list, CTC/EITC use derived counts
- `app/tax_routes.py` — DependentInput model, TaxDraftRequest.dependents field
- `app/pdf_generator.py` — Summary page shows dependent names
- `app/main.py` — version bump to 3.12.0

## Wave 29 — Multi-Year Tax Config (DEPLOYED — v3.13.0 API)

Multi-year support: compute taxes for both 2024 and 2025 tax years with year-specific constants.

**Delivered:**
- [x] `TaxYearConfig` with `get_year_config(year)` returning SimpleNamespace of all constants
- [x] `_YEAR_2024` dict: all IRS Rev. Proc. 2023-34 inflation-adjusted constants
- [x] `_YEAR_2025` dict: all IRS Rev. Proc. 2024-40 inflation-adjusted constants
- [x] Statutory rates (NIIT, SE, AOTC, etc.) defined once — shared across years
- [x] `compute_tax(tax_year=)` parameter (default 2025) loads year-specific config
- [x] All ~50 constant references in compute_tax() use `c.` prefix for year-specific config
- [x] `TaxDraftRequest.tax_year` field in API (default 2025)
- [x] MCP `compute_tax_scenario` accepts `tax_year` parameter
- [x] MCP `_build_inputs()` passes through `tax_year`
- [x] Full backward compat: module-level `from tax_config import *` exports 2025 values
- [x] 415/415 unit tests (24 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave29_multiyear.py` — 24 tests (10 config, 7 compute, 2 backward compat, 3 credits, 2 summary)

**Modified files:**
- `app/tax_config.py` — Restructured: year-specific dicts + get_year_config() + backward compat exports
- `app/tax_engine.py` — `tax_year` param, `c = get_year_config(tax_year)`, all constant refs use `c.`
- `app/tax_routes.py` — `TaxDraftRequest.tax_year`, passed to compute_tax()
- `app/mcp_server.py` — `tax_year` param on compute_tax_scenario and _build_inputs
- `app/main.py` — version bump to 3.13.0

## Wave 30 — MCP Parity (DEPLOYED — v3.14.0 API)

Full parameter parity between MCP tools and the tax engine — agents now have the same capabilities as the REST API.

**Delivered:**
- [x] Structured dependents: `dependents` list with DOB, relationship, disabled/student flags → age-based CTC/EITC/CDCC eligibility
- [x] Education expenses: `education_expenses` list → AOTC ($2,500 max, 40% refundable) + LLC ($2,000 max)
- [x] Dependent care expenses: `dependent_care_expenses` list → CDCC (Form 2441)
- [x] Retirement contributions: `retirement_contributions` list → Saver's Credit (Form 8880)
- [x] Multi-state filing: `work_states` + `days_worked_by_state` → nonresident returns + credit allocation
- [x] Penalty estimation: `prior_year_tax` + `prior_year_agi` → Form 2210 safe harbor check
- [x] Additional deductions: `medical_expenses`, `charitable_noncash`, `other_income`, `additional_withholding`
- [x] New `get_tax_config` tool: brackets, deductions, credit limits, penalty constants by year + filing status
- [x] New `taxlens://config/{year}` MCP resource
- [x] `optimize_deductions` upgraded: `tax_year`, `charitable_noncash`, `medical_expenses` params
- [x] Updated MCP instructions with full capability list
- [x] 452/452 unit tests (37 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave30_mcp_parity.py` — 37 tests (4 dependents, 2 education, 2 care, 2 retirement, 2 multi-state, 2 penalty, 4 additional params, 7 tax config, 8 build inputs, 2 optimize, 2 compare)

**Modified files:**
- `app/mcp_server.py` — Full parameter parity: 12 new params on compute_tax_scenario, new get_tax_config tool, new resource, updated instructions
- `app/main.py` — version bump to 3.14.0

## Wave 31 — Stripe Live Mode (DEPLOYED — v3.15.0 API)

Safety guard and cutover infrastructure for switching from Stripe test to live mode.

**Delivered:**
- [x] `STRIPE_LIVE_MODE_CONFIRMED` env var safety guard — live keys disabled unless explicitly confirmed
- [x] Live mode detection: `sk_live_`/`rk_live_` keys auto-detected, logged warning when unconfirmed
- [x] `GET /billing/status` admin endpoint — mode, configured prices, plan list
- [x] `scripts/setup-stripe-live.sh` — automated cutover: creates secret, sets env, verifies health
- [x] Script validates key prefixes, requires interactive confirmation for live mode
- [x] Revert instructions included in script output
- [x] 465/465 unit tests (13 new), 65/65 E2E tests passing

**New files:**
- `scripts/setup-stripe-live.sh` — Live mode cutover script with runbook
- `tests/test_wave31_stripe_live.py` — 13 tests (9 mode detection, 3 plan tiers, 1 status response)

**Modified files:**
- `app/billing.py` — STRIPE_LIVE_MODE_CONFIRMED guard, warning log on unconfirmed live key
- `app/billing_routes.py` — `/billing/status` admin endpoint
- `app/main.py` — version bump to 3.15.0

**To activate live mode:**
1. Create live products in Stripe Dashboard (3 monthly subscriptions)
2. Create restricted live API key with billing permissions
3. Create live webhook at `https://dropit.istayintek.com/api/billing/webhook`
4. Run: `./scripts/setup-stripe-live.sh <live_key> <webhook_secret> <price_ids...>`

## Wave 32-33 — Schedule E Rental Income + HSA Deduction (DEPLOYED — v3.16.0 API)

Coverage expansion: two new income/deduction types that are common for small landlords and HSA holders.

**Delivered:**
- [x] `RentalProperty` dataclass: 14 expense fields (mirrors IRS Schedule E line items) + total_expenses/net_income properties
- [x] Passive activity loss rules (IRC §469): $25K loss limit, AGI phaseout $100K-$150K (50% reduction), fully disallowed at $150K+
- [x] Net rental income/loss flows to Line 9 total income; Schedule E in forms_generated
- [x] `HSAContribution` dataclass: contributor, amount, coverage type, age 55+ catch-up
- [x] Above-the-line HSA deduction with year-specific limits: 2025 ($4,300 self / $8,550 family), 2024 ($4,150 / $8,300), $1,000 catch-up
- [x] API: `RentalPropertyInput` + `HSAContributionInput` Pydantic models in TaxDraftRequest
- [x] MCP: `_build_inputs()` + `compute_tax_scenario()` + `get_tax_config()` updated with HSA/rental constants
- [x] `to_summary()` includes `rental_income` + `hsa_deduction`
- [x] `tax_config.py`: HSA_CATCHUP, RENTAL_LOSS_LIMIT, RENTAL_LOSS_PHASEOUT_START/END constants
- [x] 491/491 unit tests (26 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave32_33_rental_hsa.py` — 26 tests (9 rental, 9 HSA, 2 combined, 6 MCP)

**Modified files:**
- `app/tax_engine.py` — RentalProperty, HSAContribution dataclasses + computation logic + summary
- `app/tax_config.py` — HSA limits (year-specific) + rental loss constants (statutory)
- `app/mcp_server.py` — rental/HSA in _build_inputs, compute_tax_scenario, get_tax_config
- `app/tax_routes.py` — RentalPropertyInput, HSAContributionInput, TaxDraftRequest fields
- `app/main.py` — version bump to 3.16.0

## Wave 34 — Infrastructure Hardening (DEPLOYED — v3.16.1 API)

Pre-scaling infrastructure improvements for reliability and operability.

**Delivered:**
- [x] Deep health probe: `/health?deep=true` measures DB latency (ms) + verifies storage write
- [x] Uptime tracking: `_STARTUP_TIME` + `uptime_seconds` in health response
- [x] Readiness endpoint: `/ready` returns 503 when DB or storage unavailable
- [x] PostgreSQL backup: `scripts/backup-pg.sh` with pg_dump → gzip → node storage, 7-day retention
- [x] Graceful shutdown: metering buffer flushed + structured shutdown logging
- [x] 506/506 unit tests (15 new), 65/65 E2E tests passing

**New files:**
- `scripts/backup-pg.sh` — Automated backup with restore instructions
- `tests/test_wave34_infrastructure.py` — 15 tests (6 backup, 6 health, 3 config)

**Modified files:**
- `app/main.py` — Deep health, readiness endpoint, uptime tracking, graceful shutdown

## Wave 35-36 — Audit Risk + Prior-Year Import (DEPLOYED — v3.17.0 API)

Differentiation features that set TaxLens apart from basic tax calculators.

**Delivered:**
- [x] Audit risk scoring module (`audit_risk.py`): IRS SOI-based statistical comparison by AGI bracket
- [x] 8 risk indicators: charitable, Schedule C expenses/losses, home office, rental loss, EITC+SE, income level, itemized
- [x] Risk score 0-100 with low/medium/high overall rating, auto-included in tax draft response
- [x] MCP tool `assess_audit_risk_tool` for agent-driven risk analysis
- [x] Prior-year import module (`prior_year_import.py`): fillable 1040 PDF field extraction via pypdf
- [x] Extracts wages, AGI, total tax, filing status, deductions, refund/owed with confidence rating
- [x] `penalty_inputs` output for Form 2210 safe harbor (prior_year_tax, prior_year_agi)
- [x] API endpoint `POST /tax-draft/import-prior-year` with file upload
- [x] 536/536 unit tests (30 new), 65/65 E2E tests passing

**New files:**
- `app/audit_risk.py` — Audit risk engine with SOI norms and 8 risk categories
- `app/prior_year_import.py` — 1040 PDF extraction with field mappings
- `tests/test_wave35_36_audit_import.py` — 30 tests (15 audit, 2 MCP, 9 money, 4 data model)

**Modified files:**
- `app/mcp_server.py` — `assess_audit_risk_tool` MCP tool
- `app/tax_routes.py` — `audit_risk` in draft response + `/import-prior-year` endpoint
- `app/main.py` — version bump to 3.17.0

### Wave 37 — Form 8889 HSA Reporting (v3.18.0) — 2026-04-24

- [x] `employer_contributions` field on HSAContribution dataclass
- [x] Form 8889 line item computation (Lines 2, 7, 9, 10, 13 + excess detection)
- [x] Employer contributions reduce deductible room (IRC §223(b)(4))
- [x] Excess contribution detection (personal + employer over limit → 6% excise)
- [x] HDHP constants (min deductible, max OOP) for both 2024 and 2025
- [x] Form 8889 PDF generation via ReportLab
- [x] Summary includes `form_8889` section with all line items
- [x] API model updated with `employer_contributions` field
- [x] MCP `_build_inputs()` and `compute_tax_scenario()` updated
- [x] MCP `get_tax_config()` returns HDHP limits
- [x] `form_8889` added to file_map for PDF download
- [x] 557/557 unit tests (21 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave37_form8889.py` — 21 tests (8 line items, 4 excess, 4 summary/forms, 3 MCP, 2 backward compat)

**Modified files:**
- `app/tax_engine.py` — HSAContribution.employer_contributions, TaxResult.form_8889_*, computation, summary, forms_generated
- `app/tax_config.py` — HDHP_MIN_DEDUCTIBLE_*, HDHP_MAX_OOP_* for 2024+2025
- `app/tax_routes.py` — HSAContributionInput.employer_contributions, form_8889 in file_map
- `app/mcp_server.py` — employer_contributions in _build_inputs(), HDHP in get_tax_config()
- `app/pdf_generator.py` — generate_form_8889() + integration in generate_all_pdfs()
- `app/main.py` — version bump to 3.18.0

### Wave 38 — Email & Notifications (v3.18.1) — 2026-04-24

- [x] `email_service.py` — Resend API via httpx (no SDK dependency)
- [x] Graceful degradation: disabled when RESEND_API_KEY not set
- [x] Welcome email template (API key + MCP config + portal link)
- [x] Filing deadline reminder template
- [x] Plan upgrade confirmation template
- [x] Onboarding integration: welcome email on signup (fire-and-forget)
- [x] Billing webhook integration: upgrade email on subscription change
- [x] Health endpoint reports `email_enabled` status
- [x] 570/570 unit tests (13 new), 65/65 E2E tests passing

**New files:**
- `app/email_service.py` — Transactional email via Resend API
- `tests/test_wave38_email.py` — 13 tests (5 degradation, 3 templates, 2 onboarding, 2 billing, 1 health)

**Modified files:**
- `app/onboarding.py` — Welcome email on signup
- `app/billing_routes.py` — Upgrade email on plan change
- `app/main.py` — email_enabled in health endpoint

### Wave 49 — Student Loan Phaseout + Foreign Tax Credit + Gambling (v3.28.0) — 2026-04-24

- [x] IRC §221(b)(2) student loan interest MAGI phaseout: single/HoH $80K-$95K, MFJ $165K-$195K, MFS $0
- [x] Student loan phaseout computed after all other adjustments (avoids circular MAGI dependency)
- [x] GamblingIncome dataclass: Form W-2G (winnings, withholding, wager type)
- [x] IRC §165(d): gambling losses capped at winnings, netted in line_8_other_income
- [x] W-2G withholding → line_25 federal withholding
- [x] ForeignTaxCredit dataclass: simplified Form 1116 (country, foreign income, tax paid)
- [x] Foreign tax credit: nonrefundable, limited by income ratio and total tax
- [x] Multiple W-2G and foreign tax credit forms aggregate correctly
- [x] Full stack: engine + REST API + MCP server
- [x] 827/827 unit tests (24 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave49_misc_income.py` — 24 tests (10 student loan, 7 gambling, 6 foreign tax, 1 backward compat)

**Modified files:**
- `app/tax_engine.py` — GamblingIncome/ForeignTaxCredit dataclasses, student_loan_deduction fields, gambling/FTC processing, phaseout logic
- `app/tax_config.py` — STUDENT_LOAN_PHASEOUT constant (2024+2025)
- `app/tax_routes.py` — GamblingIncomeInput/ForeignTaxCreditInput models, TaxDraftRequest fields
- `app/mcp_server.py` — gambling/FTC params on _build_inputs + compute_tax_scenario
- `app/main.py` — version 3.28.0

### Wave 48 — Retirement Line Reclassification + IRA Phaseout (v3.27.0) — 2026-04-24

- [x] IRA distributions route to 1040 lines 4a/4b (was lumped in line_8_other_income)
- [x] Pension/annuity distributions route to 1040 lines 5a/5b
- [x] `is_ira` field on RetirementDistribution (default False = backward compat)
- [x] Roth IRA: gross on 4a, taxable 4b = $0; Rollover pension: gross on 5a, taxable 5b = $0
- [x] Lines 4b + 5b included in total income calculation (line 9)
- [x] Lines 4b + 5b included in SS provisional income calculation
- [x] IRC §219(g) IRA deduction phaseout for active plan participants
- [x] 2025 phaseout: single $79K-$89K, MFJ filer-active $126K-$146K, MFJ spouse-active $236K-$246K, MFS $0-$10K
- [x] 2024 phaseout: single $77K-$87K, MFJ filer-active $123K-$143K, MFJ spouse-active $230K-$240K
- [x] IRS rounding: reduction rounded UP to nearest $10
- [x] Full stack: engine + REST API + MCP server
- [x] 803/803 unit tests (22 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave48_retirement_lines.py` — 22 tests (8 line classification, 12 IRA phaseout, 2 backward compat)

**Modified files:**
- `app/tax_engine.py` — lines 4a/4b/5a/5b on TaxResult, is_ira field, IRA phaseout logic, active plan params
- `app/tax_config.py` — IRA_PHASEOUT_ACTIVE + IRA_PHASEOUT_SPOUSE_ACTIVE constants (2024+2025)
- `app/tax_routes.py` — is_ira on RetirementDistributionInput, active plan fields on TaxDraftRequest
- `app/mcp_server.py` — is_ira + active plan params on _build_inputs + compute_tax_scenario
- `app/main.py` — version 3.27.0

### Wave 47 — Additional Standard Deduction + REST API Credit Fields (v3.26.0) — 2026-04-24

- [x] IRC §63(f) additional standard deduction for age 65+ and blind filers
- [x] 2025 rates: $2,000 single/HoH, $1,600 MFJ/MFS per qualifying condition
- [x] 2024 rates: $1,950 single/HoH, $1,550 MFJ/MFS (backward compat)
- [x] Up to 4 conditions for MFJ (both 65+, both blind = $6,400)
- [x] Spouse flags ignored for single/HoH filers
- [x] REST API credit field gap closed: education, dependent care, retirement contributions
- [x] EducationExpenseInput, DependentCareExpenseInput, RetirementContributionInput Pydantic models
- [x] AOTC ($2,500), LLC, CDCC, Saver's Credit now reachable via REST API
- [x] Full stack: engine + API + MCP server
- [x] 781/781 unit tests (18 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave47_senior_credits.py` — 18 tests (14 additional deduction, 3 credit API, 1 backward compat)

**Modified files:**
- `app/tax_engine.py` — additional_standard_deduction field, age/blind params, deduction logic
- `app/tax_config.py` — ADDITIONAL_STD_DED_SINGLE/MARRIED for 2024+2025
- `app/tax_routes.py` — 3 new Pydantic input models, 4 age/blind fields on TaxDraftRequest
- `app/mcp_server.py` — age/blind params on _build_inputs + compute_tax_scenario
- `app/main.py` — version 3.26.0

### Wave 46 — Capital Loss Limitation (v3.25.0) — 2026-04-24

- [x] IRC §1211(b) capital loss limitation: $3,000 single/MFJ/HoH, $1,500 MFS
- [x] `capital_loss_carryforward` tracked on TaxResult for next-year use
- [x] `capital_loss_carryover` input param: prior-year carryover applied as short-term loss
- [x] §1211 applied AFTER all capital sources (Schedule D, crypto, K-1) aggregated
- [x] MFS gets half the limit ($1,500 per IRC §1211(b)(1))
- [x] Full stack: engine + API + MCP + summary
- [x] 763/763 unit tests (17 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave46_capital_loss.py` — 17 tests (8 limitation, 6 carryover, 2 summary, 1 multi-year)

**Modified files:**
- `app/tax_engine.py` — TaxResult capital loss fields, §1211 limitation logic, carryover input
- `app/tax_config.py` — CAPITAL_LOSS_LIMIT ($3,000), CAPITAL_LOSS_LIMIT_MFS ($1,500)
- `app/tax_routes.py` — capital_loss_carryover on TaxDraftRequest
- `app/mcp_server.py` — capital_loss_carryover param on _build_inputs + compute_tax_scenario
- `app/main.py` — version 3.25.0
- `tests/test_tax_engine.py` — Updated test_capital_loss to expect §1211 cap

### Wave 45 — Unemployment, Educator Expenses, Alimony (v3.24.0) — 2026-04-24

- [x] UnemploymentCompensation dataclass: Form 1099-G (state, compensation, withholding)
- [x] Unemployment compensation fully taxable → other income
- [x] Educator expense deduction: $300 single ($600 MFJ both educators), above-the-line
- [x] Alimony paid: above-the-line deduction (pre-2019 divorce only)
- [x] Alimony received: taxable income (pre-2019 divorce only)
- [x] 1099-G withholding → line 25 federal withheld
- [x] Full stack: engine + API + MCP
- [x] 746/746 unit tests (19 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave45_unemployment_educator.py` — 19 tests (2 dataclass, 6 unemployment, 6 educator, 5 alimony)

**Modified files:**
- `app/tax_engine.py` — UnemploymentCompensation dataclass, TaxResult fields, compute_tax() processing
- `app/tax_routes.py` — UnemploymentCompensationInput model, TaxDraftRequest fields
- `app/mcp_server.py` — unemployment_benefits + educator_expenses + alimony params
- `app/main.py` — version 3.24.0

### Wave 44 — Social Security Benefits (v3.23.0) — 2026-04-24

- [x] SocialSecurityBenefit dataclass: recipient, gross_benefits, federal_withheld
- [x] IRC §86 two-threshold taxability formula: 0%/50%/85% based on provisional income
- [x] Provisional income = other income + 50% of SS benefits (avoids circular dependency)
- [x] Filing status thresholds: Single/HoH $25K/$34K, MFJ $32K/$44K, MFS $0/$0
- [x] MFS anti-abuse: $0 thresholds → SS nearly always 85% taxable
- [x] SSA-1099 summary PDF via ReportLab
- [x] W-4V voluntary withholding → line 25
- [x] Full stack: engine + API + MCP + PDF
- [x] 727/727 unit tests (19 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave44_social_security.py` — 19 tests (3 dataclass, 16 engine integration)

**Modified files:**
- `app/tax_engine.py` — SocialSecurityBenefit dataclass, TaxResult SS fields, compute_tax() SS taxability logic
- `app/tax_config.py` — SS thresholds (base/upper per filing status, 85% max)
- `app/tax_routes.py` — SocialSecurityBenefitInput model, TaxDraftRequest field, file_map
- `app/mcp_server.py` — social_security_benefits param, build/forward logic, get_tax_config SS section
- `app/pdf_generator.py` — generate_ss_summary(), generate_all_pdfs() hook
- `app/main.py` — version 3.23.0

### Wave 43 — Retirement Income (v3.22.0) — 2026-04-24

- [x] RetirementDistribution dataclass: distribution codes (1/7/G/H), Roth, early withdrawal
- [x] IRAContribution dataclass: filer/spouse, contribution amount, age 50+ catch-up
- [x] 1099-R processing: taxable distributions → other income, withholding → line 25
- [x] Early withdrawal penalty: 10% on code "1" early distributions
- [x] Roth/rollover exclusions: non-taxable per distribution code routing
- [x] IRA deduction: above-the-line, $7,000 limit ($8,000 with $1,000 catch-up)
- [x] MFJ dual IRA contributions: each spouse gets independent limit
- [x] Retirement summary PDF via ReportLab
- [x] Full stack: engine + API + MCP + PDF
- [x] 708/708 unit tests (27 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave43_retirement.py` — 27 tests (9 dataclass, 2 IRA, 16 engine integration)

**Modified files:**
- `app/tax_engine.py` — RetirementDistribution + IRAContribution dataclasses, TaxResult fields, compute_tax() retirement/IRA logic
- `app/tax_config.py` — IRA limits ($7,000), catch-up ($1,000), early withdrawal penalty rate (10%)
- `app/tax_routes.py` — RetirementDistributionInput + IRAContributionInput models, TaxDraftRequest fields, file_map
- `app/mcp_server.py` — retirement_distributions + ira_contributions params, build/forward logic, get_tax_config retirement section
- `app/pdf_generator.py` — generate_retirement_summary(), generate_all_pdfs() hook
- `app/main.py` — version 3.22.0

### Wave 42 — Depreciation & Form 4562 (v3.21.0) — 2026-04-24

- [x] DepreciableAsset dataclass: MACRS class, Section 179, bonus depreciation, business/rental use
- [x] MACRS GDS half-year convention tables (3/5/7/15-year) + straight-line (27.5/39-year)
- [x] Section 179: $1,250,000 limit (2025), $1,160,000 (2024), aggregate enforcement with phaseout
- [x] Bonus depreciation: TCJA phasedown (40% for 2025, 60% for 2024), placed-in-service year
- [x] Real property (27.5/39-year) excluded from Section 179 and bonus depreciation
- [x] Depreciation order: Section 179 → Bonus → MACRS on remaining basis
- [x] Business depreciation reduces Schedule C profit; rental depreciation reduces Schedule E
- [x] Form 4562 summary PDF via ReportLab
- [x] Full stack: engine + API + MCP + PDF
- [x] 681/681 unit tests (33 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave42_depreciation.py` — 33 tests (11 MACRS, 4 Section 179, 5 bonus, 13 engine integration)

**Modified files:**
- `app/tax_engine.py` — DepreciableAsset dataclass, TaxResult depreciation fields, compute_tax() depreciation logic
- `app/tax_config.py` — MACRS tables, bonus rates, Section 179 limits (2024+2025)
- `app/tax_routes.py` — DepreciableAssetInput model, TaxDraftRequest field, file_map
- `app/mcp_server.py` — depreciable_assets param, build/forward logic, get_tax_config depreciation section
- `app/pdf_generator.py` — generate_form_4562(), generate_all_pdfs() hook
- `app/main.py` — version 3.21.0

### Wave 41 — Crypto & Digital Assets (v3.20.0) — 2026-04-24

- [x] CryptoTransaction dataclass: asset_name, exchange, tx_hash, basis_method, wash_sale_loss_disallowed
- [x] Wash sale detection: loss disallowed amount adjusts cost basis (IRS proposed regs 2024)
- [x] Cost basis methods: FIFO, LIFO, HIFO, specific ID (metadata — exchange computes)
- [x] Crypto → CapitalTransaction conversion for Schedule D aggregation
- [x] Schedule D totals recomputed after crypto injection (avoids double-count)
- [x] Form 8949 summary PDF via ReportLab
- [x] Full stack: engine + API + MCP + PDF
- [x] 648/648 unit tests (22 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave41_crypto.py` — 22 tests (8 dataclass, 14 engine integration)

**Modified files:**
- `app/tax_engine.py` — CryptoTransaction dataclass, TaxResult crypto fields, compute_tax() crypto logic
- `app/tax_routes.py` — CryptoTransactionInput model, TaxDraftRequest field, file_map
- `app/mcp_server.py` — crypto_transactions param, build/forward logic
- `app/pdf_generator.py` — generate_form_8949(), generate_all_pdfs() hook
- `app/main.py` — version 3.20.0

### Wave 40 — Advanced Tax Features (v3.19.0) — 2026-04-24

- [x] Form 5695: Residential Energy Credits (§25D clean energy 30% no cap + §25C home improvement 30% $3,200 cap)
- [x] Schedule K-1: Passthrough income from partnerships/S-corps/trusts (ordinary, rental, interest, dividends, gains, guaranteed payments, §199A)
- [x] K-1 guaranteed payments → SE tax (alongside Schedule C)
- [x] K-1 §199A income → QBI deduction (combined with Schedule C)
- [x] Quarterly estimated tax planner: auto-calculated when tax > withholding, 4 quarters with IRS due dates
- [x] Full stack: engine + API (Pydantic) + MCP (compute_tax_scenario + get_tax_config) + PDF (Form 5695 + K-1 Summary)
- [x] 626/626 unit tests (36 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave40_advanced.py` — 36 tests (14 energy, 12 K-1, 6 quarterly, 4 integration)

**Modified files:**
- `app/tax_engine.py` — EnergyImprovement + K1Income dataclasses, TaxResult fields, compute_tax() energy/K-1/quarterly logic
- `app/tax_config.py` — Energy credit constants (§25D/§25C rates and limits)
- `app/tax_routes.py` — EnergyImprovementInput + K1IncomeInput models, TaxDraftRequest fields, file_map
- `app/mcp_server.py` — energy_improvements + k1_incomes params, get_tax_config energy section
- `app/pdf_generator.py` — generate_form_5695() + generate_k1_summary(), generate_all_pdfs() hooks
- `app/main.py` — version 3.19.0

### Wave 39 — Operational Maturity (v3.18.2) — 2026-04-24

- [x] PG backup CronJob: daily at 2am, pg_dump | gzip, 7-day retention, hostPath on mgplcb05
- [x] Smoke test CronJob: every 30 min, checks /health, /ready, /docs, /metrics
- [x] Alpine DNS fix: short service names + ndots:2 dnsConfig (FQDN fails in curlimages/curl)
- [x] Manual smoke test verified: 0 failures (all 4 endpoints returning 200)
- [x] 590/590 unit tests (20 new), 65/65 E2E tests passing

**New files:**
- `k8s/cronjob-pg-backup.yaml` — PG backup CronJob (taxlens-db namespace)
- `k8s/cronjob-smoke-test.yaml` — Smoke test CronJob (taxlens namespace)
- `tests/test_wave39_operational.py` — 20 tests (9 backup YAML, 11 smoke test YAML)

### Wave 73 — Grafana Dashboard Integration (v3.52.0) — 2026-04-24

- [x] app/grafana_dashboards.py: 4 dashboard definitions + 7 custom metrics + 4 alert rules
- [x] Dashboards: API Performance, Business Metrics, Tenant Activity, Infrastructure
- [x] Custom metrics: taxlens_drafts_total, taxlens_ocr_pages_total, taxlens_active_tenants, taxlens_computation_duration_seconds, taxlens_api_requests_total, taxlens_webhook_deliveries_total, taxlens_stripe_mrr
- [x] Alerts: high error rate >5% (critical), P95 >2s (warning), disk >80% (warning), webhook failures (warning)
- [x] GET /admin/dashboards endpoint
- [x] 1274/1274 unit tests (14 new), 65/65 E2E tests passing

**New files:**
- `app/grafana_dashboards.py` — CUSTOM_METRICS, ALERT_RULES, 4 dashboard generators
- `tests/test_wave73_grafana.py` — 14 tests (3 metrics, 5 alerts, 5 dashboards, 1 endpoint)

**Modified files:**
- `app/main.py` — GET /admin/dashboards endpoint, version 3.52.0

### Wave 72 — Stripe Live Mode Activation (v3.51.0) — 2026-04-24

- [x] app/stripe_live.py: Live products, metered billing, revenue metrics
- [x] 3 tiers: Starter $29, Professional $99, Enterprise $299 (monthly)
- [x] Metered usage: computations, ocr_pages, api_calls with tenant isolation
- [x] Revenue dashboard: MRR, ARR, subscriber breakdown by tier, churn rate
- [x] Billing state machine: 6 states with validated transitions
- [x] GET /admin/revenue endpoint for revenue dashboard
- [x] 1260/1260 unit tests (17 new), 65/65 E2E tests passing

**New files:**
- `app/stripe_live.py` — LIVE_PRODUCTS, metered usage, RevenueMetrics, billing state machine
- `tests/test_wave72_stripe_live.py` — 17 tests (5 products, 3 usage, 5 revenue, 3 transitions, 1 endpoint)

**Modified files:**
- `app/main.py` — GET /admin/revenue endpoint, version 3.51.0

### Wave 71 — Additional 10 State Tax Engines (v3.50.0) — 2026-04-24

- [x] 9 new state config modules: VA, MA, MI, AZ, CO, MN, MD, WI, IN (WA already no-tax)
- [x] Flat states: MA (5% + 4% millionaire surtax), MI (4.25%), AZ (2.5%), CO (4.4%), IN (3.05%)
- [x] Graduated states: VA (2-5.75%), MN (5.35-9.85%), MD (2-5.75%), WI (3.54-7.65%)
- [x] Reciprocal agreements: VA-DC-KY-MD-PA-WV, MD-DC-PA-VA-WV, MI-IL-IN-KY-MN-OH-WI, WI-IL-IN-KY-MI, IN-KY-MI-OH-PA-WI, MN-MI-ND
- [x] Indiana uses in_.py (Python keyword avoidance), get_state_config handles mapping
- [x] All 9 states compute correctly via compute_state_tax()
- [x] 1243/1243 unit tests (48 new), 65/65 E2E tests passing

**New files:**
- `app/state_configs/va.py`, `ma.py`, `mi.py`, `az.py`, `co.py`, `mn.py`, `md.py`, `wi.py`, `in_.py`
- `tests/test_wave71_additional_states.py` — 48 tests (11 config, 6 flat, 4 graduated, 6 reciprocal, 13+8 computation)

**Modified files:**
- `app/state_configs/__init__.py` — IN → in_ keyword mapping
- `app/main.py` — version 3.50.0

### Wave 70 — Horizontal Scaling Infrastructure (v3.49.0) — 2026-04-24

- [x] app/scaling.py: MeteringBuffer with flush/aggregate pattern
- [x] record_usage() convenience function for tenant metering (computation, ocr_page, api_call)
- [x] HPAConfig: K8s HPA manifest generator (CPU-based, 1-3 replicas, 70% target)
- [x] PDBConfig: K8s PDB manifest generator (minAvailable=1)
- [x] ScalingStatus for health endpoint (metering backend, buffer size, tenants tracked)
- [x] Health endpoint now includes scaling metrics
- [x] 1195/1195 unit tests (13 new), 65/65 E2E tests passing

**New files:**
- `app/scaling.py` — MeteringBuffer, HPAConfig, PDBConfig, ScalingStatus
- `tests/test_wave70_horizontal_scaling.py` — 13 tests (6 metering, 3 HPA, 2 PDB, 2 status)

**Modified files:**
- `app/main.py` — scaling status in health endpoint, version 3.49.0

### Wave 69 — Webhook Notifications + Event System (v3.48.0) — 2026-04-24

- [x] app/webhooks.py: HMAC-SHA256 signed webhook delivery system
- [x] 5 event types: draft.created, draft.updated, document.uploaded, document.ocr_complete, plan.upgraded
- [x] Endpoint CRUD: create, list, update, delete with per-tenant isolation
- [x] Event dispatch: matches tenant + event type + active status
- [x] Delivery log with configurable limit
- [x] Test endpoint for verification
- [x] POST/GET /webhooks, DELETE /webhooks/{id}, POST /webhooks/{id}/test, GET /webhooks/{id}/deliveries
- [x] 1182/1182 unit tests (21 new), 65/65 E2E tests passing

**New files:**
- `app/webhooks.py` — WebhookEndpoint, WebhookDelivery, WebhookEvent, dispatch_event(), HMAC signing
- `tests/test_wave69_webhooks.py` — 21 tests (4 signing, 5 CRUD, 5 dispatch, 2 delivery log, 2 test endpoint, 1 event log, 2 API)

**Modified files:**
- `app/main.py` — Webhook CRUD + test + delivery endpoints, version 3.48.0

### Wave 68 — Withholding Analyzer / W-4 Recommendations (v3.47.0) — 2026-04-24

- [x] app/withholding_analyzer.py: gap analysis with full-year projection from YTD data
- [x] WithholdingInput: wages, withheld_ytd, pay periods, target_refund, deductions, estimated payments
- [x] WithholdingResult: projected tax/withholding, gap, penalty risk, W-4 recommendation
- [x] Safe harbor: 100%/110% threshold based on AGI, penalty risk detection
- [x] Target refund mode: specify desired refund, compute required extra withholding per period
- [x] Marginal rate from bracket lookup (upper_limit, rate format)
- [x] POST /withholding-check endpoint with full parameter set
- [x] 1161/1161 unit tests (15 new), 65/65 E2E tests passing

**New files:**
- `app/withholding_analyzer.py` — WithholdingInput, WithholdingResult, analyze_withholding()
- `tests/test_wave68_withholding_analyzer.py` — 15 tests (5 basic, 3 W-4, 3 penalty, 2 rates, 2 endpoint)

**Modified files:**
- `app/main.py` — POST /withholding-check endpoint, version 3.47.0

### Wave 67 — Amended Return / Form 1040-X (v3.46.0) — 2026-04-24

- [x] app/amended_return.py: compute_amended_return() with 17-line A/B/C column comparison
- [x] AmendedLine dataclass: line, description, column_a (original), column_b (change), column_c (corrected)
- [x] AmendedReturn dataclass: lines, explanation, refund_change, total_tax_change, draft IDs
- [x] Auto-generated Part III explanation (describes material changes)
- [x] Custom explanation override support
- [x] generate_1040x() in pdf_generator.py — ReportLab 1040-X summary PDF with A/B/C columns
- [x] POST /amend/{original_draft_id} endpoint in tax_routes.py
- [x] "1040x" added to file_map for PDF downloads
- [x] 1146/1146 unit tests (12 new), 65/65 E2E tests passing

**New files:**
- `app/amended_return.py` — AmendedLine, AmendedReturn, compute_amended_return()
- `tests/test_wave67_amended_return.py` — 12 tests (7 computation, 1 PDF, 4 endpoint)

**Modified files:**
- `app/pdf_generator.py` — generate_1040x()
- `app/tax_routes.py` — POST /amend/{original_draft_id}, "1040x" in file_map
- `app/main.py` — version 3.46.0

### Wave 66 — Intelligent Tax Optimization Engine (v3.45.0) — 2026-04-24

- [x] app/tax_optimizer.py: 15-strategy optimization engine
- [x] Strategies: HSA, IRA, 401(k), charitable bunching, loss harvesting, QBI, Roth conversion, SALT workaround, filing status, mega backdoor Roth, dependent care FSA, energy credits, estimated tax timing, student loan, standard vs itemized
- [x] Each recommendation: strategy, category, estimated_savings, difficulty, irs_risk, description, action_items
- [x] Sorted by estimated savings, conditional applicability
- [x] POST /optimize endpoint with full parameter set
- [x] 1134/1134 unit tests (18 new), 65/65 E2E tests passing

**New files:**
- `app/tax_optimizer.py` — 15-strategy optimizer with Recommendation/OptimizationPlan dataclasses
- `tests/test_wave66_tax_optimizer.py` — 18 tests (4 basic, 8 strategies, 2 fields, 2 edge, 2 endpoint)

**Modified files:**
- `app/main.py` — POST /optimize endpoint, version 3.45.0

### Wave 65 — Tax Projection + Multi-Year Planning (v3.44.0) — 2026-04-24

- [x] app/tax_projector.py: multi-year projection engine + Roth conversion optimizer
- [x] inflate(): CPI-U chained methodology, rounded to $50 per IRS convention
- [x] get_2026_projected_constants(): 11 inflation-adjusted constants for 2026
- [x] project_tax_liability(): 3-year projection with income growth (2024-2026)
- [x] optimize_roth_conversion(): binary search for optimal conversion within target bracket
- [x] POST /tax-projection: 3-year comparison with projected 2026 constants
- [x] POST /roth-optimizer: find max Roth conversion staying in target bracket
- [x] _effective_rate() + _marginal_rate() helpers (TaxResult lacks these)
- [x] 1116/1116 unit tests (19 new), 65/65 E2E tests passing

**New files:**
- `app/tax_projector.py` — projection engine, Roth optimizer, inflation helpers
- `tests/test_wave65_tax_projection.py` — 19 tests (3 inflation, 4 constants, 5 projection, 4 Roth, 3 endpoint)

**Modified files:**
- `app/main.py` — /tax-projection, /roth-optimizer endpoints, version 3.44.0

### Wave 64 — Scenario Comparison API + Tax Calendar (v3.43.0) — 2026-04-24

- [x] GET /tax-calendar: 11 federal IRS deadlines + 10 state deadline sets
- [x] State-specific deadlines via ?state= query param
- [x] TX/FL empty (no income tax)
- [x] POST /compare-scenarios: 2-4 scenarios, side-by-side with deltas from base
- [x] Result fields: total_income, AGI, taxable_income, total_tax, rates, refund/owed
- [x] tax_delta and refund_delta computed from first scenario
- [x] Planning tag in OpenAPI
- [x] Tax calendar exempt from tenant context middleware
- [x] 1097/1097 unit tests (16 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave64_scenarios_calendar.py` — 16 tests (8 calendar, 8 scenarios)

**Modified files:**
- `app/main.py` — _TAX_CALENDAR_2025, _STATE_DEADLINES, tax_calendar endpoint, compare_scenarios_api endpoint
- `app/middleware/tenant_context.py` — /tax-calendar skip path

### Wave 63 — Batch Document Upload + Document Manager (v3.42.0) — 2026-04-24

- [x] POST /tax-draft/batch-upload: accept up to 20 files, save with UUID proc_ids + metadata
- [x] POST /tax-draft/batch-analyze: parallel Azure OCR via asyncio.gather
- [x] PATCH /tax-draft/documents/{proc_id}/ocr-result: manual OCR field correction
- [x] GET /tax-draft/documents: list all uploaded documents with status
- [x] _DOC_TYPE_MAP: Azure doc_type → internal form type mapping (8 form types)
- [x] Per-document error isolation in batch analyze
- [x] 1081/1081 unit tests (19 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave63_batch_upload.py` — 19 tests (4 type map, 4 upload, 3 analyze, 3 correction, 2 list, 3 storage)

**Modified files:**
- `app/tax_routes.py` — batch endpoints, _DOC_TYPE_MAP, asyncio/uuid imports
- `app/main.py` — version 3.42.0

### Wave 62 — Enhanced PDF Package + Cover Letter (v3.41.0) — 2026-04-24

- [x] generate_full_return_pdf(): merges all forms into single PDF with bookmarks
- [x] Cover page: filer info, return summary (income, AGI, tax, payments, refund/owed), TOC with page numbers
- [x] _FORM_ORDER constant: 30+ forms in IRS filing sequence
- [x] PDF bookmarks for navigation to each form
- [x] GET /tax-draft/{id}/pdf/full_return endpoint
- [x] Handles multiple 1099-R files, state returns, empty directories
- [x] DRAFT watermark on cover page
- [x] 1062/1062 unit tests (12 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave62_full_return_pdf.py` — 12 tests (2 cover, 4 merge, 3 order, 3 endpoint)

**Modified files:**
- `app/pdf_generator.py` — _generate_cover_page(), generate_full_return_pdf(), _FORM_ORDER
- `app/tax_routes.py` — GET /{draft_id}/pdf/full_return endpoint
- `app/main.py` — version 3.41.0

### Wave 61 — 1040-ES Estimated Tax Voucher Generation (v3.40.0) — 2026-04-24

- [x] generate_1040es_vouchers(): 4-page ReportLab PDF with filer info, SSN, amount, due dates
- [x] Due dates: Apr 15 2026, Jun 15 2026, Sep 15 2026, Jan 15 2027
- [x] Filer name, address, SSN, filing status on each voucher
- [x] IRS mailing address reference + DRAFT watermark
- [x] Conditional generation in generate_all_pdfs (quarterly_estimated_tax > 0)
- [x] 1040es added to tax_routes.py file_map for individual download
- [x] 1050/1050 unit tests (13 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave61_1040es.py` — 13 tests (4 PDF render, 3 due dates, 4 integration, 2 engine)

**Modified files:**
- `app/pdf_generator.py` — generate_1040es_vouchers(), _ES_DUE_DATES, generate_all_pdfs hook
- `app/tax_routes.py` — 1040es in file_map
- `app/main.py` — version 3.40.0

### Wave 60 — 1099-MISC + 1099-G OCR Parsers (v3.39.0) — 2026-04-24

- [x] parse_1099misc_from_ocr(): categorized extraction (rents, royalties, other, NEC, medical, withheld)
- [x] 14-box extraction: Boxes 1-10 with proper income routing per category
- [x] parse_1099g_from_ocr(): returns UnemploymentCompensation directly from OCR fields
- [x] State extraction from Box10a with PayerState fallback
- [x] misc_1099_proc_ids + unemployment_1099g_proc_ids on TaxDraftRequest
- [x] 1099-MISC income routed: rents/royalties → other_income, NEC → businesses, withheld → additional_withholding
- [x] OCR-parsed 1099-G entries merged into unemployment_list
- [x] 1037/1037 unit tests (21 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave60_1099misc_1099g.py` — 21 tests (8 MISC parser, 5 G parser, 6 integration, 2 callable)

**Modified files:**
- `app/tax_engine.py` — parse_1099misc_from_ocr(), parse_1099g_from_ocr() functions
- `app/tax_routes.py` — imports, proc_id fields, OCR loops, income/unemployment merge
- `app/main.py` — version 3.39.0

### Wave 59 — 1099-R OCR Parser + PDF Generation (v3.38.0) — 2026-04-24

- [x] parse_1099r_from_ocr(): extracts 9 fields (gross, taxable, code, IRA, Roth, withholding)
- [x] Distribution code interpretation: 7=normal, 1=early, G=rollover, Q=Roth
- [x] IRA/SEP/SIMPLE and Roth flag extraction from Box7 + explicit fields
- [x] generate_1099r(): ReportLab summary PDF with distribution type interpretation
- [x] retirement_1099r_proc_ids on TaxDraftRequest for auto-extraction
- [x] OCR-parsed distributions merge with manual entries
- [x] 1099r added to file_map and generate_all_pdfs
- [x] 1016/1016 unit tests (17 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave59_1099r.py` — 17 tests (8 parser, 3 PDF, 5 integration, 1 engine)

**Modified files:**
- `app/tax_engine.py` — parse_1099r_from_ocr() function
- `app/pdf_generator.py` — generate_1099r() + hook in generate_all_pdfs
- `app/tax_routes.py` — retirement_1099r_proc_ids, parse_1099r_from_ocr import, OCR merge
- `app/main.py` — version 3.38.0

### Wave 58 — Landing Page Content API (v3.37.0) — 2026-04-24

- [x] GET /content/about: mission, platform stats, technology stack, compliance info
- [x] GET /content/security: data handling, encryption, RLS, audit logging, responsible disclosure
- [x] GET /content/for-businesses: CPA/fintech/planning use cases, pricing tiers
- [x] Content paths exempt from tenant context middleware
- [x] Content tag in OpenAPI tags
- [x] 999/999 unit tests (13 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave58_landing_content.py` — 13 tests (3 endpoints, 3 about, 2 security, 2 business, 3 integration)

**Modified files:**
- `app/main.py` — version 3.37.0, 3 content endpoints, Content openapi_tag
- `app/middleware/tenant_context.py` — /content/ skip path

### Wave 57 — Admin Database Explorer (v3.36.0) — 2026-04-24

- [x] GET /admin/database: overview with row counts for all 12 core tables
- [x] GET /admin/database/{table_name}: sample rows + column names with limit param
- [x] Table allowlist prevents arbitrary table access (404 for unknown tables)
- [x] Error handling per table (one table failing doesn't break overview)
- [x] 986/986 unit tests (11 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave57_admin_database.py` — 11 tests (4 config, 2 overview, 3 detail, 2 enrichment)

**Modified files:**
- `app/admin_routes.py` — DB_TABLES constant, database_overview + table_detail endpoints
- `app/main.py` — version 3.36.0

### Wave 56 — API Reference Documentation (v3.35.0) — 2026-04-24

- [x] Enriched OpenAPI metadata: summaries + descriptions on all tax_routes endpoints
- [x] FastAPI openapi_tags for organized Swagger UI (Tax Drafts, Documents, Admin, Billing, etc.)
- [x] Rich app description in FastAPI constructor
- [x] GET /postgrest-openapi: proxied PostgREST spec with Redis cache (5min TTL)
- [x] GET /docs/api-guide: structured API quickstart (auth, endpoints, rate limits, scopes)
- [x] GET /docs/mcp-guide: MCP integration guide (Claude Desktop config, 9 tools, examples)
- [x] PostgREST proxy exempt from tenant context middleware
- [x] 975/975 unit tests (15 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave56_api_docs.py` — 15 tests (4 OpenAPI, 3 PostgREST proxy, 3 API guide, 3 MCP guide, 2 integration)

**Modified files:**
- `app/main.py` — version 3.35.0, openapi_tags, 3 new doc endpoints, PostgREST proxy
- `app/tax_routes.py` — summary/description on all endpoints
- `app/middleware/tenant_context.py` — /postgrest-openapi skip path

### Wave 55 — Redis-Backed Rate Limiting (v3.34.0) — 2026-04-24

- [x] Redis 7 Alpine StatefulSet + Service in taxlens-db namespace (64Mi, allkeys-lru)
- [x] redis_client.py: async connection pool, lazy init, graceful fallback when REDIS_URL unset
- [x] Token bucket via Redis Lua script (atomic refill + consume, 2-min TTL auto-cleanup)
- [x] Daily/monthly counter via Redis Lua script (window-based reset)
- [x] IP rate limiting via Redis sorted set sliding window
- [x] Health endpoint reports redis_enabled, redis_ok, redis_latency_ms
- [x] Graceful Redis shutdown in lifespan
- [x] Full backward compatibility: no REDIS_URL = pure in-memory (unchanged behavior)
- [x] 960/960 unit tests (31 new), 65/65 E2E tests passing

**New files:**
- `app/redis_client.py` — async Redis client with Lua scripts
- `charts/taxlens-db/templates/redis-statefulset.yaml` — Redis 7 Alpine StatefulSet
- `charts/taxlens-db/templates/redis-service.yaml` — ClusterIP service
- `tests/test_wave55_redis_rate_limit.py` — 31 tests (6 client, 3 bucket, 3 counter, 5 fallback, 4 redis, 4 ip, 3 plans, 3 k8s)

**Modified files:**
- `app/rate_limiter.py` — Redis-first with in-memory fallback for all rate limit methods
- `app/main.py` — version 3.34.0, Redis health in /health, Redis close in lifespan

### Wave 54 — MCP OAuth 2.0 Token Endpoint (v3.33.0) — 2026-04-24

- [x] POST /oauth/token: client_credentials, authorization_code (PKCE S256), refresh_token grants
- [x] Token response: access_token, token_type, expires_in, scope, refresh_token
- [x] Refresh token rotation (old invalidated on each use)
- [x] Scope enforcement: intersection of client scopes × requested × VALID_SCOPES
- [x] Authorization code creation helper (for admin/authorization UI)
- [x] Token cleanup function (deletes expired tokens)
- [x] Token scope introspection (validate_token_scopes for route-level checks)
- [x] V007 migration: indexes on oauth_tokens(client_id, expires_at) and (token_type, client_id)
- [x] OAuth endpoint exempt from tenant context + rate limit middleware
- [x] 929/929 unit tests (33 new), 65/65 E2E tests passing

**New files:**
- `app/oauth.py` — OAuth 2.0 token endpoint (3 grant types, PKCE, cleanup, introspection)
- `app/db/flyway/migrations/V007__oauth_token_indexes.sql` — 2 new indexes
- `tests/test_wave54_oauth.py` — 33 tests (5 utilities, 3 validation, 3 client_credentials, 6 auth_code, 4 refresh, 2 code creation, 2 cleanup, 4 scope validation, 4 integration)

**Modified files:**
- `app/main.py` — version 3.33.0, mount oauth_router, add /oauth/token to EXEMPT_PATHS
- `app/middleware/tenant_context.py` — add /oauth/token to _SKIP_PATHS
- `tests/test_wave34_infrastructure.py` — version 3.33.0
- `tests/test_flyway.py` — migration count 6→7

### Wave 53 — Form 2210 Schedule AI Annualized Installment Method (v3.32.0) — 2026-04-24

- [x] QuarterlyIncome dataclass: 5 tuples of 4 floats (wages, business, other, deductions, withholding)
- [x] IRS annualization factors: 4.0 (Q1), 2.4 (Q2), 1.5 (Q3), 1.0 (Q4)
- [x] Per-period annualized income and tax computation
- [x] Required installment comparison: AI vs regular (25% per quarter)
- [x] Penalty reduction: uses lower of two methods automatically
- [x] `sched_ai_used`, `sched_ai_penalty_reduction` on TaxResult
- [x] Schedule AI PDF via ReportLab (Parts I + II + penalty comparison)
- [x] Summary includes schedule_ai section when AI method is beneficial
- [x] Full stack: engine + API (quarterly_income dict) + MCP + PDF
- [x] Full backward compatibility: no quarterly_income = no Schedule AI
- [x] 896/896 unit tests (16 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave53_schedule_ai.py` — 16 tests (4 basic, 3 factors, 1 business, 2 comparison, 4 summary/PDF, 2 backward compat)

**Modified files:**
- `app/tax_engine.py` — QuarterlyIncome dataclass, TaxResult Schedule AI fields, annualized computation
- `app/pdf_generator.py` — generate_schedule_ai(), generate_all_pdfs() hook
- `app/tax_routes.py` — quarterly_income in TaxDraftRequest, schedule_ai in file_map
- `app/mcp_server.py` — quarterly_income param in _build_inputs() and compute_tax_scenario()
- `app/main.py` — version 3.32.0

### Wave 52 — Form 8606 Nondeductible IRA Basis Tracking (v3.31.0) — 2026-04-24

- [x] Nondeductible contribution auto-computed from phaseout (total contributions - IRA deduction)
- [x] Prior-year basis carryforward input (`prior_year_ira_basis`)
- [x] Pro-rata rule: nontaxable % = total_basis / (year_end_value + distributions + conversions)
- [x] IRA distribution taxable amount adjusted via pro-rata (line 4b reduced)
- [x] Roth conversion Part III: basis portion nontaxable, remainder taxable
- [x] Backdoor Roth pattern: nondeductible + immediate conversion with $0 remaining = 100% nontaxable
- [x] Remaining basis carryforward after distributions/conversions
- [x] Form 8606 PDF via ReportLab (Parts I + III)
- [x] Summary includes form_8606 section when basis > 0
- [x] Full backward compatibility: no new params = no Form 8606
- [x] 880/880 unit tests (16 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave52_form8606.py` — 16 tests (4 nondeductible, 4 pro-rata, 3 Roth conversion, 4 summary/PDF, 1 backward compat)

**Modified files:**
- `app/tax_engine.py` — TaxResult Form 8606 fields, compute_tax new params, pro-rata computation
- `app/pdf_generator.py` — generate_form_8606(), generate_all_pdfs() hook
- `app/tax_routes.py` — 3 new TaxDraftRequest fields, form_8606 in file_map
- `app/mcp_server.py` — 3 new params in _build_inputs() and compute_tax_scenario()
- `app/main.py` — version 3.31.0

### Wave 51 — Schedule 1/3/E PDF Generation (v3.30.0) — 2026-04-24

- [x] Schedule 1 (Form 1040) — Additional Income and Adjustments to Income
- [x] Part I: business income, rental, unemployment, alimony, gambling, K-1 ordinary
- [x] Part II: SE deduction, HSA, IRA, student loan, educator expenses, alimony paid
- [x] Schedule 3 (Form 1040) — Additional Credits and Payments
- [x] Part I: foreign tax credit, CDCC, education credits, Saver's, energy credits
- [x] Part II: refundable AOTC, EITC
- [x] Schedule E — Supplemental Income and Loss (Rental Real Estate)
- [x] Per-property breakdown (address, rents, expenses, net income)
- [x] Totals + passive activity loss notation
- [x] Conditional generation: simple W-2 returns skip all three schedules
- [x] Added to forms_generated and file_map for PDF download
- [x] ReportLab-drawn with DRAFT watermark (consistent with K-1 summary pattern)
- [x] 864/864 unit tests (20 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave51_schedule_pdfs.py` — 20 tests (7 Schedule 1, 6 Schedule 3, 5 Schedule E, 2 backward compat)

**Modified files:**
- `app/pdf_generator.py` — generate_schedule_1(), generate_schedule_3(), generate_schedule_e(), generate_all_pdfs() hooks
- `app/tax_engine.py` — Schedule 1/3 in forms_generated (conditional)
- `app/tax_routes.py` — schedule_1, schedule_3, schedule_e in file_map
- `app/main.py` — version 3.30.0

### Wave 50 — Charitable Contribution AGI Limits (v3.29.0) — 2026-04-24

- [x] IRC §170 cash contribution limit: 60% of AGI
- [x] IRC §170 non-cash contribution limit: 30% of AGI
- [x] Overall charitable cap: 60% of AGI (combined cash + non-cash)
- [x] `charitable_carryforward` tracked on TaxResult for excess over AGI limits
- [x] `charitable_cash_before_limit` / `charitable_noncash_before_limit` preserve raw inputs
- [x] Carryforward appears in summary JSON when > 0
- [x] Zero AGI edge case: zero charitable allowed (no division error)
- [x] Statutory percentages: same for 2024 and 2025 (not inflation-indexed)
- [x] Full backward compatibility: small donations unchanged
- [x] 844/844 unit tests (17 new), 65/65 E2E tests passing

**New files:**
- `tests/test_wave50_charitable_limits.py` — 17 tests (4 cash, 3 non-cash, 5 combined, 4 edge cases, 1 backward compat)

**Modified files:**
- `app/tax_engine.py` — TaxResult charitable fields, §170 AGI limit logic in Schedule A section
- `app/tax_config.py` — CHARITABLE_CASH_AGI_LIMIT (60%), CHARITABLE_NONCASH_AGI_LIMIT (30%)
- `app/main.py` — version 3.29.0

## Post-Wave-73 Roadmap (2026-04-25)

All 73 waves complete. v3.52.0 deployed. Below is the prioritized roadmap from the platform reflection.

### 90-Day Priority (BLOCKERS + TCJA Sunset)

1. ~~**BLOCKER: Fix Solo 401(k) / SEP-IRA mismodeling**~~ — **RESOLVED in Wave 74 (v3.53.0)**. Added SEP-IRA, Solo 401(k), SIMPLE IRA as Schedule 1 line 16 above-the-line deductions. SE tax unaffected by retirement contributions.

2. ~~**BLOCKER: PII encryption for SSNs**~~ — **RESOLVED in Wave 77 (v3.56.0)**. Added `pii.py` module with Fernet encryption + masking. SSNs redacted in result.json "input" section at storage boundary. Graceful degradation: masks to last 4 when no encryption key configured.

3. **TCJA sunset 2025 vs 2026 comparison engine** — Tax Cuts and Jobs Act provisions expire end of 2025: brackets revert to 2017 rates, SALT cap ($10K) removed, QBI deduction (§199A) expires, CTC drops from $2,000 to $1,000, standard deduction roughly halves. Build `_YEAR_2026_SUNSET` config and comparison endpoint. This is the #1 planning question every client will ask in 2025.

4. ~~**QBI SSTB field on BusinessIncome**~~ — **RESOLVED in Wave 75 (v3.54.0)**. Added is_sstb + w2_wages_paid to BusinessIncome. SSTB QBI phases to $0 above threshold.

5. ~~**compare_scenarios should return marginal rates**~~ — **RESOLVED in Wave 76 (v3.55.0)**. Both REST and MCP compare_scenarios now return effective_rate and marginal_rate per scenario. Fixed latent bug where main.py accessed non-existent TaxResult attrs.

6. ~~**Audit risk should show passing checks**~~ — **RESOLVED in Wave 76 (v3.55.0)**. Added PassingCheck dataclass + passing_checks list to AuditRiskReport. Every check that doesn't trigger a flag records a passing check with category, description, and norm values.

### 6-Month Priorities

7. **PTET (Pass-Through Entity Tax) framework** — #1 state-level planning move for S-corp/partnership owners. 20+ states offer PTET elections that convert SALT-capped personal deductions into uncapped entity-level deductions. Need: entity-level computation, credit-on-K-1 flow, state election tracking.

8. **Carryforward tracking system** — Charitable contribution carryforward, NOL carryforward, capital loss carryforward, AMT credit carryforward, passive activity loss carryforward. Currently `charitable_carryforward` is tracked but not consumed in subsequent years. Need persistent per-filer carryforward state.

9. **Entity type optimization engine** — Compare sole prop vs S-corp vs C-corp for a given business profile. Reasonable compensation analysis for S-corp. This is the highest-value advisory feature for business owners.

10. **State fillable PDF templates** — Currently only IL has a fillable PDF. All other states use ReportLab summary pages. Add official state templates for top-10 states (CA, NY, NJ, PA, NC, GA, OH, VA, MA, MD).

11. **Mega backdoor Roth modeling** — After-tax 401(k) → in-plan Roth conversion. Needs employer plan limits (§415(c) $70,000 total) minus employee deferrals and employer match. High-value for high-income savers.

12. **IL PPRT (Personal Property Replacement Tax)** — 1.5% on S-corp/partnership income earned in IL. Not currently modeled. Affects every IL business owner.

### 18-Month Vision

13. **E-file integration** — MeF XML generation for federal + state. This is the ultimate goal — advisory without filing is half the product.
14. **Entity tax returns (1120, 1120-S, 1065)** — Currently individual-only. Business entity returns open the CPA market.
15. **Lifetime tax optimizer** — Multi-year Roth conversion ladders, Social Security timing, RMD planning, estate tax integration.
16. **API marketplace** — Third-party integrator access with per-call billing. The MCP + OAuth infrastructure is ready.
17. **Real-time law tracking** — Automated tax law change detection and constant updates when new Rev. Proc. or legislation passes.

### Known Gaps by Severity

**Correctness (wrong answers):**
- ~~Solo 401(k)/SEP modeled as Schedule C expense~~ (FIXED v3.53.0 Wave 74)
- ~~QBI missing SSTB classification for high-income phaseout~~ (FIXED v3.54.0 Wave 75)
- No SEP-IRA or SIMPLE IRA contribution limits (only traditional IRA modeled)
- Reasonable compensation not enforced for S-corp QBI
- PTET elections not modeled (affects state tax for 20+ states)

**Completeness (missing features):**
- No carryforward consumption (charitable, NOL, capital loss, AMT credit, passive)
- No entity comparison (sole prop vs S-corp vs C-corp)
- No TCJA sunset comparison (2025 vs 2026 law)
- No mega backdoor Roth pathway
- No state fillable PDFs (except IL)
- SSNs stored in plaintext (PII risk)

**Scale (production readiness):**
- Webhook delivery is simulated (always 200) — needs real httpx delivery with retries
- Metering buffer is in-memory only — needs Redis Streams for multi-replica
- No e-file capability (MeF XML generation)
- No entity tax returns (1120, 1120-S, 1065)
- **Tax engine:** All planned features complete (53 waves shipped)
