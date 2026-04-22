# TaxLens — Next Steps

Updated: 2026-04-22 (v2.2.0)

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

## Wave 11 — Remaining (Deferred)

### 11.5 — Migrate Routes to Dolt
Tax draft, document, and Plaid routes still use file-based storage for metadata. With Dolt repos ready, route handlers should read/write metadata through the repository layer. PVC keeps PDFs/docs, Dolt tracks metadata. Path changes from `{username}/` to `{tenant_id}/{username}/`.

**Status:** Deferred. Routes work in both modes via middleware fallback. Priority is lower than OAuth.

### 11.6 — MCP OAuth 2.0
Implement `OAuthAuthorizationServerProvider` backed by Dolt. PKCE + authorization code flow. Scopes: compute, drafts, documents. Auto-mounts `/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/revoke`. Required for Claude Desktop to connect as an OAuth client (instead of manual API key).

**Status:** Deferred. API key auth is working. OAuth layers on top once provisioning is battle-tested.

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
