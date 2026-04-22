# TaxLens — Next Steps

Updated: 2026-04-22 (v2.0.0)

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

## Wave 11 — Remaining (Deferred)

### 11.5 — Migrate Routes to Dolt
Tax draft, document, and Plaid routes still use file-based storage for metadata. With Dolt repos ready, route handlers should read/write metadata through the repository layer. PVC keeps PDFs/docs, Dolt tracks metadata. Path changes from `{username}/` to `{tenant_id}/{username}/`.

**Status:** Deferred. Routes work in both modes via middleware fallback. Priority is lower than OAuth.

### 11.6 — MCP OAuth 2.0
Implement `OAuthAuthorizationServerProvider` backed by Dolt. PKCE + authorization code flow. Scopes: compute, drafts, documents. Auto-mounts `/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/revoke`. Required for Claude Desktop to connect as an OAuth client (instead of manual API key).

**Status:** Deferred. API key auth is working. OAuth layers on top once provisioning is battle-tested.

## Wave 12 — A2UI Tenant Portal

Lightweight SSR portal (FastAPI + Jinja2 + HTMX) for tenant management. Separate namespace `taxlens-portal` on mgplcb05. Talks to TaxLens API over ClusterIP. Memory: 48Mi request / 96Mi limit.

**Key deliverables:**
- Login with API key, encrypted session cookie
- Dashboard with stats (users, drafts, docs, Plaid)
- Tax drafts list/detail/PDF download
- MCP-driven computation forms (auto-generated from tool schemas)
- Dolt history timeline with row-level diffs and rollback
- OAuth client management with Claude Desktop config snippet
- Admin views: all-tenant list, create, suspend, system health

## Wave 13 — Git-Backed Claude Support Agent

Separate service in `taxlens-agent` namespace on mgplcb03. Claude API (Anthropic SDK) with tenant-scoped MCP tool access. Git-backed JSONL conversations. SSE streaming. Memory: 128Mi request / 256Mi limit.

**Key deliverables:**
- Git conversation store (JSONL + auto git commit per message)
- MCP tool proxy to taxlens-api (tenant-scoped)
- Claude conversation engine with tax support persona
- Chat widget in A2UI portal (floating panel, SSE, markdown)
- Admin oversight API (read conversations, search, stats)

## Wave 14 — Billing, Metering & Launch

Stripe billing, usage metering, rate limiting, self-service onboarding.

**Key deliverables:**
- Metering: usage_events (append-only) + usage_daily (aggregated) in Dolt
- Rate limiting: in-memory token bucket per tenant, 3 plan tiers
- Stripe integration: checkout, webhook, portal, metered add-ons
- Self-service: Stripe checkout → webhook → auto-provision tenant
- Monitoring: Prometheus metrics, per-tenant usage, anomaly detection
- Documentation: API reference, MCP integration guide, onboarding walkthrough

### Plan Tiers

| Feature | Starter ($29/mo) | Professional ($99/mo) | Enterprise ($299/mo) |
|---------|-------------------|-----------------------|----------------------|
| API calls/min | 30 | 120 | 600 |
| Computations/day | 50 | 500 | Unlimited |
| OCR pages/month | 100 | 1,000 | 10,000 |
| Agent messages/day | 100 | 500 | Unlimited |
| MCP OAuth clients | 2 | 10 | Unlimited |
| Plaid connections | 5 | 50 | Unlimited |
| Dolt history | 30 days | 1 year | Unlimited |
