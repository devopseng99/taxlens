# TaxLens — Key Technical Decisions

Updated: 2026-04-23 (v3.14.0 API + v2.6.0 Portal)

## Architecture

1. **Separate tax engine from routes** — `tax_config.py` (constants), `tax_engine.py` (computation), `pdf_generator.py` (PDF output), `tax_routes.py` (API). Clean separation allows unit testing engine without HTTP.

2. **pypdf fillable templates (not ReportLab canvas)** — Uses `pypdf` to fill official IRS fillable PDF forms via `PdfWriter(clone_from=reader)` + `update_page_form_field_values()`. Templates stored in `app/templates/`. Replaced the original ReportLab canvas approach which generated custom-drawn PDFs. Official IRS forms are legally compliant and visually identical to paper filings. Summary page still uses ReportLab (custom report, no IRS equivalent).

3. **`clone_from=reader` required for AcroForm** — `PdfWriter()` + `append_pages_from_reader()` drops the AcroForm dictionary, making `update_page_form_field_values()` fail. Must use `PdfWriter(clone_from=reader)` to preserve form fields.

4. **OpenFile-matched f1040 template** — The 26f25 tax-refs `f1040.pdf` (229 fields) has different field names than OpenFile's embedded version (155 fields). We use the OpenFile-matched version whose field names align with the YAML configuration at `pdf/2025/IRS1040/en/configuration.yml`. Same SHA as OpenFile production binary.

5. **Standard vs Itemized auto-choice** — Engine always computes both and picks the higher deduction automatically. Schedule A PDF always generated for reference.

6. **LTCG/QD preferential rate stacking** — Qualified dividends + net long-term gains taxed at 0/15/20% rates, stacked on top of ordinary income in the bracket. Short-term gains taxed as ordinary income.

7. **Self-employment tax (Schedule SE)** — 15.3% on 92.35% of net SE income. SS portion capped at wage base minus W-2 SS wages. 50% deductible above-the-line. This matches IRS calculation method.

8. **QBI deduction (Section 199A)** — Simplified: 20% of qualified business income, capped at taxable income. Full phase-out rules for high earners not implemented (would need SSTB classification, W-2/UBIA limits).

9. **Draft storage on PVC** — Each draft gets a unique directory under `{STORAGE_ROOT}/{tenant_id}/{username}/drafts/{draft_id}/`. PDFs + result.json stored together. Multi-tenant path isolation.

10. **OCR-first, manual-supplement** — W-2 and 1099-INT data extracted from Azure OCR results. All other income/deduction types entered manually via API. This allows hybrid automated+manual filing.

## Testing

11. **20-scenario smoke test suite** — `tests/smoke_test_tax_drafts.sh` with 20 scenarios covering all 4 filing statuses, business income, investments, deductions, CTC, crypto, multi-business, retired couples. Re-runnable for regression after any engine changes.

12. **No W-2 in smoke tests** — Test cases don't use OCR W-2 documents (would require stored OCR files). Instead they test the computation engine directly with manual income inputs. OCR path tested separately via upload+analyze flow.

13. **Playwright E2E for UI + PDF validation** — Headless Chromium via central Playwright server (WebSocket). Tests tab navigation, draft listing, PDF download headers. Note: headless Chromium triggers download for PDFs instead of inline render — not a bug, Content-Disposition is correct. Programmatic header verification used instead.

14. **Schedule 2 + Form 8959 + Form 8960 conditional generation** — These forms are only generated when their respective taxes are triggered: Schedule 2 when SE tax, NIIT, or Additional Medicare Tax > 0; Form 8959 only when Additional Medicare Tax > 0; Form 8960 only when NIIT > 0. Schedule 2 line 21 (total other taxes) flows to 1040 line 23. Field mappings derived from labeled PDF inspection (no tooltips on IRS PDFs).

15. **Form 8959 withholding reconciliation** — Part V computes excess Additional Medicare Tax withholding (W-2 box 6 minus regular 1.45% Medicare) which can offset total tax. Threshold reduction for SE income: if W-2 wages exceed the filing-status threshold, there's zero remaining threshold for SE income.

## Strategic Architecture

16. **MCP server over custom chat UI** — Don't build a chat interface (that's rebuilding Claude/ChatGPT). Instead, expose the tax engine as an MCP (Model Context Protocol) server. Any MCP-capable client (Claude Desktop, Claude Code, custom agents) can call `compute_tax`, `compare_scenarios`, `optimize_deductions` as native tools. The value is the computation engine, not the conversation layer.

17. **Modular plug-and-play design** — Tax engine should be a product-agnostic service: REST API for direct integration, MCP for agentic access. Multi-state support via pluggable state config modules (not monolithic switch statements). Design for reuse across products — the tax engine is the business asset, the interface layer is interchangeable.

18. **Multi-state as pluggable modules** — Each state's tax config is a standalone module (`state_configs/ca.py`, `state_configs/ny.py`) with rate tables, bracket definitions, exemptions, and form metadata. A generic `compute_state_tax()` dispatcher loads the appropriate module. Adding a new state = adding one config file, no engine changes.

19. **Multi-state worker computation order** — Nonresident returns computed first, then resident return with credits for taxes paid to other states. Credit formula: `min(tax_paid_to_other_state, resident_tax * (other_state_income / total_income))`. Reciprocal agreements skip the nonresident return entirely.

20. **W-2 state wage extraction** — `StateWageInfo` dataclass captures per-state wages from W-2 OCR `StateTaxInfos` array entries. Falls back to days-worked allocation when W-2s lack state breakdowns. Both paths produce the same `{state: wages}` dict for state tax computation.

21. **Generic state PDF for non-IL states** — IL uses fillable `il1040.pdf` template. All other states get a ReportLab-generated summary page showing income allocation, tax computation, withholding, and refund/owed. Adding fillable templates for specific states is a drop-in replacement via `_STATE_TEMPLATE_MAP`.

22. **1099-B as structured import, not OCR** — Brokerage consolidated statements contain multi-page transaction tables that OCR cannot reliably parse row-by-row. Accept JSON/CSV structured data instead. Plaid (Wave 10) will provide this structured data from connected brokerages.

23. **Auto-detect form type from Azure doc_type** — The `prebuilt-tax.us` auto-detect model returns `doc_type` (e.g., `tax.us.w2`, `tax.us.1099Div`). We map this to a simplified `form_type` string stored in `ocr_result.json`, enabling downstream parsers to route documents automatically without user specifying the document type.

24. **1099-DIV capital gain distributions as LTCG** — Box 2a from 1099-DIV (capital gain distributions) are treated as long-term capital gains and injected as a synthetic `CapitalTransaction` into Schedule D. This matches IRS rules — mutual fund capital gain distributions are always long-term regardless of holding period.

25. **additional_withholding param for non-W-2 withholding** — 1099-DIV (Box 4) and 1099-NEC (Box 4) federal withholding flows through a separate `additional_withholding` parameter to `compute_tax()`, added to `line_25_federal_withheld` alongside W-2 withholding. Keeps the W-2 summation clean while supporting any number of 1099 withholding sources.

26. **MCP mounted as raw ASGI Route, not Starlette sub-app** — Mounting FastMCP's `streamable_http_app()` as a Starlette sub-application causes double-lifespan conflict (FastAPI's lifespan and Starlette's compete for session_manager). Instead, FastAPI lifespan manages `mcp.session_manager.run()` directly, and `StreamableHTTPASGIApp(mcp.session_manager)` is mounted via `Route("/mcp", ...)` for minimal ASGI passthrough.

27. **DNS rebinding protection for MCP** — MCP SDK enables DNS rebinding protection by default, rejecting requests where the Host header doesn't match localhost. Production requires explicit `TransportSecuritySettings(allowed_hosts=["dropit.istayintek.com", ...])` to accept requests through the CF tunnel.

28. **Stateless MCP over StreamableHTTP** — `stateless_http=True` means no server-side session state between requests. Each MCP call is independent. This simplifies scaling (any pod can handle any request) and avoids session affinity requirements behind the load balancer.

29. **Plaid access_token encrypted with Fernet** — Plaid persistent access_tokens are encrypted at rest with Fernet (AES-128-CBC + HMAC) and stored on the PVC. The Fernet key is injected via K8s secret (`PLAID_FERNET_KEY`). This prevents plaintext credential exposure if the PVC is compromised.

30. **Plaid integration gracefully disabled** — When `PLAID_CLIENT_ID` or `PLAID_FERNET_KEY` are not set, `PLAID_ENABLED=False` and all Plaid endpoints return 503. The rest of the app functions normally. This allows the same image to run with or without Plaid credentials.

31. **Plaid investment_transactions for tax data, not statements** — The Plaid statements API (for downloading 1099 PDFs) is a premium product requiring special access. Instead, we use `investments/transactions/get` which provides sell transactions (→ Schedule D) and dividends (→ Schedule B) directly as structured data — no OCR needed. This is more reliable than OCR and available in the free sandbox tier.

32. **Plaid data stored as tax_data.json per item** — Each synced Plaid item gets `transactions.json` (raw API response) and `tax_data.json` (parsed CapitalTransactions + DividendIncome). TaxDraftRequest references items by ID and loads the parsed file, avoiding re-parsing on every draft computation.

## Multi-Tenant Database (Wave 11)

33. **Dolt over PostgreSQL for versioned data** — Dolt provides MySQL-compatible SQL with git-like version control (branch, merge, diff, log, rollback) built in. Every schema change and tenant mutation is automatically committed to Dolt's internal git log. This gives audit trails and per-tenant rollback without building custom versioning. Trade-off: smaller community than PostgreSQL, but the versioning benefit outweighs this for a multi-tenant tax platform where data provenance matters.

34. **aiomysql async driver** — Dolt speaks MySQL wire protocol. aiomysql provides async connection pooling (min=2, max=5) compatible with FastAPI's async handlers. No need for an ORM — raw SQL via repository pattern keeps queries transparent and Dolt-specific features (CALL dolt_commit, dolt_diff) accessible.

35. **Repository pattern over ORM** — Each table gets a dedicated repo module (`tenant_repo.py`, `user_repo.py`, etc.) with plain async functions wrapping parameterized SQL. This avoids ORM overhead, keeps Dolt-specific SQL (CALL dolt_commit, AS OF queries) first-class, and makes the data layer easy to test with mock patches.

36. **`plan_tier` not `plan` — MySQL reserved word** — `PLAN` is a reserved keyword in MySQL/Dolt. Using it as a column name causes cryptic syntax errors. Renamed to `plan_tier` across schema and all repository code. Lesson: always check MySQL reserved word list when naming columns.

37. **`key_prefix` VARCHAR(12) not VARCHAR(8)** — API keys use `tlk_` prefix (4 chars) + 8 chars of the key = 12 chars for the prefix. Original schema had VARCHAR(8) which caused silent INSERT failures in Dolt (no truncation, hard error). Always size VARCHAR to match the actual generated content.

38. **Graceful degradation: Dolt optional** — When `DOLT_HOST` env var is empty, the entire DB layer is skipped. Middleware sets `tenant_id="default"`, auth falls back to legacy `TAXLENS_API_KEYS` env var, routes use file-based storage. This allows the same image to run single-tenant (no database) or multi-tenant (with Dolt). Critical for zero-downtime migration.

39. **SHA-256 hashed API keys** — API keys stored as SHA-256 hashes, never plaintext. The raw key is shown exactly once at creation. Validation: hash the incoming key, compare against stored hash, join with tenants table to verify tenant is active. `last_used_at` updated on every successful validation for audit.

40. **Multi-tenant middleware extracts tenant context** — `TenantContextMiddleware` runs before every request. Validates X-API-Key header against Dolt, sets `request.state.tenant_id`, `tenant_slug`, `user_id`. Skips auth for /health, /docs, /openapi.json, /mcp paths. Admin routes use separate X-Admin-Key header.

41. **Admin key from K8s secret, not Dolt** — The platform admin key (`TAXLENS_ADMIN_KEY`) comes from a K8s secret, not the database. This avoids chicken-and-egg: you need the admin key to create the first tenant, but you'd need a tenant to authenticate against Dolt. External secret bootstraps the admin.

42. **Dolt version control on significant mutations** — Not every INSERT gets a Dolt commit. Commits happen on: schema migration, tenant creation, tenant suspension/activation. Individual API key creates and draft saves use autocommit (MySQL-level) but don't create Dolt version control commits. This keeps the Dolt log meaningful (not one commit per API call).

43. **SQL comment stripping before semicolon split in migration** — Schema SQL files have `--` comment lines. The migration parser splits on `;` first, then filters blocks starting with `--`. Problem: a comment block followed by a CREATE TABLE (no intervening `;`) makes the entire block appear to start with `--`, silently skipping the first table. Fix: strip comment lines BEFORE splitting on semicolons.

44. **Dolt StatefulSet with init container for `dolt init`** — Dolt requires a database directory to be initialized before the server starts. Init container checks for `.dolt` dir; if missing, runs `dolt init` + creates the database + creates the remote-access user. This is idempotent — subsequent pod restarts skip init when data already exists on the PV.

45. **busybox wait-for-dolt init container** — API deployment includes a busybox init container that loops `nc -z taxlens-dolt 3306` until Dolt is ready. This ensures the API pod doesn't start (and fail migration) before Dolt accepts connections. Simple, no additional dependencies.

## Wave 12 — A2UI Tenant Portal (v2.1.0→v2.2.0)

46. **SSR over SPA** — FastAPI + Jinja2 + HTMX instead of React SPA. Portal is a thin management layer, not a complex interactive app. SSR keeps the image under 96Mi and eliminates a build step. HTMX handles dynamic updates without full page reloads.

47. **Starlette 1.0 TemplateResponse API** — `templates.TemplateResponse(request, "template.html", {context})` — `request` is first positional arg, not inside the context dict. Breaking change from pre-1.0 Starlette. Failure mode: `TypeError: unhashable type: 'dict'` in Jinja2 cache.

48. **itsdangerous session cookies** — `URLSafeTimedSerializer` with `SESSION_SECRET` from K8s secret. 8-hour max age, secure=True, httponly=True. Simpler than JWT for a server-rendered portal where the server owns both creation and validation.

49. **Single-level subdomain for wildcard cert** — `taxlens-portal.istayintek.com` instead of `portal.taxlens.istayintek.com`. Wildcard cert `*.istayintek.com` only covers one level. Three-level subdomains fail TLS handshake silently.

50. **Jinja2 globals for config** — `templates.env.globals["config"] = {...}` to pass config values to all templates. Avoids repeating config in every route's template context.

## Wave 14 — Billing, Metering & Launch (v3.0.0)

58. **Async buffered metering** — `MeteringLogger` buffers usage events in memory (list of dicts) and flushes to Dolt every 30 seconds or when the buffer reaches 100 events, whichever comes first. This avoids per-request DB writes while keeping eventual consistency within a flush window. Uses `asyncio.Lock` for thread safety.

59. **Token bucket rate limiting (in-memory)** — Per-tenant rate limiting uses a token bucket algorithm for API calls/minute and daily counters for computations/OCR/agent messages. Plan-based limits loaded from Dolt and cached for 5 minutes. Good enough for single-replica; would need Redis-backed solution for multi-replica.

60. **Starlette middleware LIFO ordering** — `add_middleware()` calls execute in reverse order (last added = outermost). MeteringRateLimitMiddleware must be added FIRST (innermost), TenantContextMiddleware SECOND, CORS LAST (outermost). If reversed, `tenant_id` is None when rate limiter checks it, silently skipping all rate limiting.

61. **Stripe graceful degradation** — When `STRIPE_SECRET_KEY` is empty, `STRIPE_ENABLED=False` and billing endpoints return 503. Webhook verification raises RuntimeError. Same pattern as Plaid (decision #30). Allows the same image to run with or without Stripe.

62. **Self-service onboarding via Stripe webhook** — `checkout.session.completed` webhook triggers `provision_tenant()` which atomically creates: tenant record, admin user, API key, plan limits in Dolt, billing_customers record, and commits to Dolt. The raw API key is included in the Stripe checkout session metadata for retrieval post-purchase.

63. **Shared Jinja2Templates instance (portal)** — All portal route modules must import from a single `shared.py` instead of creating their own `Jinja2Templates`. Template globals (like `config`) are set once on the shared instance. Creating separate instances per-module drops the globals, causing `UndefinedError` in templates.

64. **CSS value collision in E2E assertions** — Checking for HTTP status codes like "500" in page content fails because CSS values (`font-weight: 500`, `height: 500px`) contain the same substring. E2E tests should check for semantic error text (`"internal server error"`) not status code numbers.

## Wave 13 — Claude Support Agent (v1.0.0)

51. **Git-backed JSONL over database** — Conversations stored as JSONL files in per-tenant git repos instead of Dolt tables. Git provides versioning, branching, and `git grep` search for free. JSONL is append-friendly with `fcntl.flock` for concurrent writes. Tradeoff: slower queries at scale (100+ tenants), but good enough for MVP.

52. **Separate service on mgplcb03** — Agent runs on control plane node (38% memory) to spread load from mgplcb05 (31%). Requires image import to mgplcb03 (not mgplcb05). The PV is local on mgplcb03.

53. **Non-streaming Claude API with tool use loop** — Uses `messages.create()` (not streaming) with a `while` loop for up to 5 tool call rounds. Each round: collect text + tool_use blocks, execute tools, append results, call Claude again. Simpler than streaming with tool use. SSE chunks are sent per-block, not per-token.

54. **MCP JSON-RPC proxy (not MCP SDK)** — Agent talks to TaxLens MCP via raw JSON-RPC over HTTP (initialize → tools/list → tools/call) instead of importing the MCP SDK. Keeps the agent image lightweight and avoids MCP SDK version coupling. Same pattern as the portal's compute.py.

55. **python:3.11-slim needs git package** — GitPython requires the `git` binary. `python:3.11-slim` doesn't include it. ImportError at startup: "Bad git executable." Fix: `apt-get install -y --no-install-recommends git` in Dockerfile.

56. **SSE via sse-starlette** — `EventSourceResponse` from `sse-starlette` for streaming chat responses. Events typed as `text`, `tool_use`, `tool_result`, `done`, `error`. Browser reads with `fetch + ReadableStream`, not EventSource API (POST not supported by EventSource).

57. **Rate limiting in-memory** — Simple dict-based token bucket per tenant. Prunes expired entries on each check. Good enough for single-replica deployment. Will need Redis-backed rate limiting if scaled to multiple replicas (Wave 14).

## Wave 15 — PostgreSQL + PostgREST Migration (v3.1.0)

65. **PostgreSQL + PostgREST over plain PostgreSQL** — Replaces Dolt with an isolated `taxlens-db` namespace running PostgreSQL 16 + PostgREST v12. PostgREST auto-generates a REST API from the schema, eliminates 7 repository files (~600 LOC) replaced by 1 thin HTTP client (~100 LOC), and enforces tenant isolation at the database level via Row-Level Security (RLS). The 64Mi PostgREST memory cost is negligible compared to Dolt's 256Mi, and query latency drops from 30s+ to <10ms.

66. **JWT + RLS role architecture** — 4 PostgreSQL roles: `authenticator` (PostgREST login), `app_anon` (validate_api_key RPC only), `app_tenant` (all tables via RLS — sees only own tenant's data), `app_admin` (bypasses RLS). JWT minted by the API after key validation, PostgREST enforces RLS automatically via `current_setting('request.jwt.claims')::json->>'tenant_id'`.

67. **db-flyway-admin migration engine** — Reusable Flyway-inspired migration module (`db/flyway/`) with versioned SQL files (V001-V004), SHA-256 checksums, schema_history tracking, CLI (`python -m db.flyway migrate|info|validate`). PostgreSQL DDL runs in transactions. Designed for reuse across projects.

68. **Auth cache: in-memory OrderedDict LRU** — 256 entries, 60s TTL, keyed by SHA-256 of API key. Eliminates repeated PostgREST roundtrips for the same key within the TTL window. OrderedDict provides O(1) LRU eviction by moving accessed keys to the end.

69. **PostgREST filter syntax over raw SQL** — PostgREST uses URL query parameters for filtering (e.g., `?status=eq.active&tenant_id=eq.abc`). This is less flexible than raw SQL but eliminates SQL injection by design and keeps the API client stateless. Complex queries use PostgreSQL functions exposed via `/rpc/`.

70. **SECURITY DEFINER for validate_api_key** — The `validate_api_key()` function runs as `app_admin` (bypasses RLS) but is callable by `app_anon`. This allows anonymous key validation without granting `app_anon` direct table access. The function returns only the minimum data needed (tenant_id, slug, user_id, key_id).

71. **Isolated taxlens-db namespace** — PostgreSQL + PostgREST run in their own namespace with NetworkPolicy restricting access to taxlens, taxlens-portal, and taxlens-agent namespaces only. This provides defense-in-depth: even if the API is compromised, the attacker can only reach PostgREST (which enforces RLS), not PostgreSQL directly.

72. **Graceful degradation preserved: DB_ENABLED from POSTGREST_URL** — Same pattern as Dolt (decision #38) but keyed on `POSTGREST_URL` env var. When empty, the app runs in file-only single-tenant mode. All DB operations guarded by `if not DB_ENABLED:` checks.

73. **Pure ASGI middleware over BaseHTTPMiddleware** — Starlette's `BaseHTTPMiddleware` wraps `call_next` in an anyio task group. When two stacked BaseHTTPMiddleware subclasses both do `await httpx_call()` (PostgREST), the nested task groups deadlock silently — requests hang indefinitely while health checks (which skip auth) keep passing. Converted both `TenantContextMiddleware` and `MeteringRateLimitMiddleware` to raw ASGI classes (`__call__(self, scope, receive, send)`). Response header injection done via `send` wrapper function.

74. **StatefulSet PVC naming: `data-{statefulset}-0`** — StatefulSet `volumeClaimTemplates` with `name: data` auto-creates a PVC named `data-{statefulset-name}-0` (e.g., `data-taxlens-pg-0`). The PV's `claimRef.name` must match exactly. Never combine `volumes[].persistentVolumeClaim` with `volumeClaimTemplates` for the same mount name — K8s creates both resources, and the PV may bind to the wrong one (in our case, it bound to a Harness PV from another namespace).

75. **PostgREST env var definition order** — Kubernetes `$(VAR)` expansion in env values requires the referenced variable to be defined earlier in the `env` list. `PGRST_DB_URI: postgres://authenticator:$(PG_PASSWORD)@...` fails with auth error if `PG_PASSWORD` is defined after it. Fix: move `PG_PASSWORD` (secretKeyRef) above `PGRST_DB_URI`.

76. **Namespace Helm ownership annotation** — If `kubectl create namespace` runs before `helm install` (which also tries to create the namespace), the install fails with "cannot re-use a name that is still in use." Fix: annotate the existing namespace with `meta.helm.sh/release-name` and label with `app.kubernetes.io/managed-by=Helm` before running `helm install`.

77. **PostgreSQL PGDATA subdirectory + chmod 777** — PG Alpine container (UID 999) sets `PGDATA=/var/lib/postgresql/data/pgdata` (subdirectory of mount). The mount point must be `chmod 777` on the host — `chown 999:999` alone is insufficient because the container's initdb creates subdirectories that may need group/other write bits depending on the storage driver.

## v3.1.2 — Logging Suppression

78. **Consistent WARNING-level logging across all services** — All 5 TaxLens pods now emit WARNING+ only. Pattern: (a) uvicorn `--log-level warning` in Dockerfile CMD, (b) Python `logging.basicConfig(level=logging.WARNING)` + explicit suppression of noisy third-party loggers (`httpx`, `httpcore`, `uvicorn.access`), (c) PostgreSQL `log_min_messages=warning` + `log_checkpoints=off` + `log_connections=off` + `log_disconnections=off` via container args, (d) PostgREST `PGRST_LOG_LEVEL=warn` env var. This eliminates high-frequency INFO-level disk writes (connection logs, checkpoint notifications, HTTP access logs) that were consuming disk on the memory-constrained cluster.

79. **Metering pseudo-tenant skip** — `MeteringLogger.log()` returns early for `tenant_id` values `default` and `__admin__` which don't exist in the `tenants` table. Without this, PostgREST returns FK constraint violations on `usage_events.tenant_id`. Health checks and admin endpoints set these pseudo-tenant IDs.

80. **CronJob aggregate_usage.py rewritten for PostgREST** — Original script used Dolt imports (`aiomysql`, `CALL dolt_commit`). Rewritten to use PostgREST HTTP API with admin JWT. Groups events by tenant+type+date, upserts into `usage_daily`, prunes events older than 30 days. Script now lives at `/app/scripts/aggregate_usage.py` inside the API image (added `COPY scripts/ /app/scripts/` to Dockerfile).

## Wave 16 — Feature Flags + Free Tier (v3.2.0)

81. **Per-tenant feature flags via `tenant_features` table** — Boolean columns for each gatable feature (`can_itemized_deductions`, `can_schedule_c`, `can_1099_forms`, etc.) rather than a single JSONB blob. Explicit columns enable RLS policies and PostgREST filtering without parsing JSON, and make the feature matrix self-documenting in the schema. Trade-off: adding a new feature requires a migration, but features change rarely and schema enforcement prevents typos.

82. **Free tier requires login — no anonymous tax access** — All tiers authenticate via API key (same mechanism). Tax data is PII governed by NIST SP 800-53 and IRS Publication 4557 (Safeguarding Taxpayer Data). No anonymous document upload, computation, or storage. The landing page's public tax estimator tools (Wave 18) are client-side-only JavaScript calculators that store nothing.

83. **Free tier allows document upload (NIST/IRS retention)** — `can_upload_documents=true` for all tiers. IRS requires taxpayers to retain supporting documents. Blocking uploads on the free tier would violate data retention requirements and degrade user trust. Instead, form-type gating (`allowed_form_types JSONB`) restricts what can be processed — free tier can only upload W-2s.

84. **Form-type gating via `allowed_form_types` JSONB column** — Free tier: `["W-2"]`. Starter: `["W-2","1099-INT","1099-DIV","1099-NEC","1099-MISC","1099-B"]`. Professional/Enterprise: `NULL` (all types). The OCR/upload pipeline accepts the document but returns 403 if the detected form type isn't in the tenant's allowlist. This is a soft gate — the document is not stored if rejected.

85. **`TIER_FEATURES` constant in rate_limiter.py** — Single source of truth for plan → feature mapping. Used by `provision_tenant()` during onboarding and `_sync_plan_limits()` on Stripe webhook plan changes. Keeps feature defaults out of the database — the DB stores the tenant's current features, not the tier templates.

86. **FeatureGateMiddleware as pure ASGI (same pattern as tenant_context.py)** — Runs after TenantContextMiddleware (needs `tenant_id`) and before MeteringRateLimitMiddleware. Blocks `/mcp` and `/plaid` path prefixes for tenants without those features. Skips admin, health, docs, billing, and onboarding paths. Uses a separate 256-entry LRU cache with 5-min TTL (same pattern as auth cache). Route-level checks use `request.state.features` for fine-grained gating.

87. **Self-service free signup without Stripe** — `POST /billing/onboarding/free` provisions a tenant with `plan_tier="free"` without requiring Stripe checkout. IP-based rate limiting (10 signups/hour per IP) prevents abuse. The endpoint is exempt from auth (tenant context middleware skip) since there's no tenant yet. Stripe is only involved for paid tier upgrades.

88. **Feature cache invalidation on admin updates** — `invalidate_cache(tenant_id)` called in admin PUT/POST feature endpoints and `_sync_plan_limits()` (Stripe webhook). Without explicit invalidation, upgraded tenants would wait up to 5 minutes for new features to take effect.

## Wave 17 — Landing Page on Cloudflare Workers (v1.0.0)

89. **Astro 6 SSR on CF Workers (not emDash CMS)** — emDash 0.6.0's SQLite adapter uses `better-sqlite3` native addon which fails on CF Workers runtime (`createRequire` undefined). Deployed pure Astro SSR instead. emDash CMS admin will be added later when `@emdash-cms/cloudflare` D1 adapter is available. Marketing pages don't need CMS — they're static Astro components.

90. **Workers Route over custom_domain** — `custom_domain: true` in wrangler.toml tries to create a new DNS record, conflicting with the existing CF tunnel CNAME. Workers Routes (`taxlens.istayintek.com/*`) intercept traffic on existing DNS records and take priority over CF tunnel routing. Route created via CF API (`POST /zones/{id}/workers/routes`).

91. **`nodejs_compat` compatibility flag required** — Astro's Cloudflare adapter uses `node:module` and other Node.js built-ins. Without `nodejs_compat`, the worker crashes with "No such module node:module".

92. **Signup page is client-side fetch, not SSR form** — The `/signup` form POSTs to `https://dropit.istayintek.com/api/billing/onboarding/free` via client-side `fetch()`. This avoids CORS issues (browser makes the request directly) and keeps the landing page stateless. The API key is displayed on success — users must save it before navigating away.

93. **Old taxlens-ui K8s nginx scaled to 0 (not deleted)** — The CF Workers landing page replaces the nginx static site. Scaled to 0 to reclaim 32Mi memory on mgplcb05. Kept as fallback in case CF Workers has issues — can scale back to 1 and remove the Workers Route.

94. **`CLOUDFLARE_ACCOUNT_ID` required alongside token** — The CF API token doesn't include `/memberships` scope, so wrangler can't auto-detect the account. Explicit `CLOUDFLARE_ACCOUNT_ID=9709bd1f498109e65ff5d1898fec15ee` env var required for all wrangler commands.

## Wave 18 — Free Tax Calculator Tools (v1.1.0)

95. **Client-side-only calculators — no server, no storage** — All 4 tools (refund estimator, filing status advisor, bracket visualizer, SE tax calculator) compute entirely in browser JavaScript. No API calls, no data stored, no PII collected. This avoids NIST/IRS compliance requirements for the public tools — actual tax filing (even free tier) requires login.

96. **2025 tax brackets hardcoded in client JS (not API)** — Bracket tables are embedded in each tool's `<script>` tag. This is intentional — these are marketing tools, not the production engine. The TaxLens API has the authoritative bracket tables. Keeping them separate prevents confusion and avoids needing API auth for read-only estimates.

## Wave 19 — Subscription Portal UX + Early Access (v3.3.0)

97. **Feature-aware dashboard via admin API** — Portal fetches tenant features from `GET /admin/tenants/{id}/features` on dashboard load. Features stored in Jinja2 template context, not session. Each feature renders as enabled (green checkmark) or locked (lock icon with tier requirement). This avoids caching stale feature flags — always reflects current state.

98. **Upgrade flow redirects to Stripe via API** — `/billing/checkout?plan=X` calls `POST /api/billing/checkout` with the target plan, which returns a Stripe checkout URL. Portal redirects the browser there. No Stripe keys in the portal — all payment logic lives in the API. Post-checkout success page at `/billing/success` refreshes features.

99. **Usage meters with color-coded progress bars** — Usage page builds meter data per resource (filings, documents, OCR pages, computations, users). Plan limits defined as constants in the portal route (`PLAN_LIMITS` dict). Colors: green (<70%), yellow (70-90%), red (>90%). Unlimited resources show a thin green bar at 10% width.

100. **Early access as opt-in toggles, not auto-enable** — Enterprise tenants (or admin-enabled) see `/settings/early-access` with checkbox toggles for beta features. Selected features saved to `early_access_features` JSONB array via admin API. This ensures beta features are explicitly opted into, not silently activated.

101. **Sidebar billing section added to base template** — New "Billing" section in sidebar with Usage, Early Access, and Plans & Upgrade links. CSS for progress bars, upgrade CTAs, and feature-locked cards added to `base.html`. Keeps all portal styling in one file (no separate CSS imports).

102. **65/65 E2E tests — 6 new Wave 19 tests** — T60-T65 cover billing upgrade page, usage page, early access page, feature flags API, dashboard feature gating, and sidebar navigation items. All tests pass against live deployment.

## Wave 20 — Production Hardening (v3.4.0 API + v2.6.0 Portal)

103. **DB password moved from values.yaml to K8s Secret** — OpenFile DB password was hardcoded in plain text in Helm values (committed to git). Replaced with `secretKeyRef` referencing `openfile-postgresql` secret. URL env vars (`TAXLENS_PORTAL_URL`, `TAXLENS_API_URL`, `TAXLENS_LANDING_URL`) added to deployment template for configurable URLs.

104. **Deep health check pings PostgREST** — `/api/health` now makes an HTTP GET to PostgREST root. Returns `"status": "degraded"` with `"db_ok": false` if PostgREST is unreachable. K8s probes will detect actual database outages instead of reporting healthy when DB is down.

105. **Daily PostgreSQL backup CronJob** — `taxlens-pg-backup` runs daily at 3 AM, `pg_dump --format=custom | gzip` to `/opt/k8s-pers/vol1/taxlens-backups/`. 7-day retention with `find -mtime +7 -delete`. Deployed via Helm in `taxlens-db` chart.

106. **Hardcoded URLs extracted to env vars** — 15+ instances of `dropit.istayintek.com`, `taxlens-portal.istayintek.com` across billing_routes.py, onboarding.py, admin_routes.py, main.py (CORS), mcp_server.py now read from `TAXLENS_PORTAL_URL`, `TAXLENS_API_URL`, `TAXLENS_LANDING_URL` with existing values as defaults.

107. **CSRF double-submit cookie** — Portal now generates HMAC-derived CSRF tokens from the session cookie. `set_csrf_cookie()` called on login, `verify_csrf()` available for POST form validation. CSRF cookie is `httponly=False` (must be readable by JS/forms) but `SameSite=Lax` + `Secure=True`.

108. **Security headers on all portal responses** — `SecurityHeadersMiddleware` adds: `Content-Security-Policy` (self + inline for HTMX), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.

109. **Branded error pages** — Portal exception handler now renders `error.html` template with base.html layout (sidebar, dark theme) instead of raw `<h1>404</h1>` HTML. Error titles mapped for 400, 403, 404, 500, 503.

110. **Azure OCR graceful degradation** — `ocr.py` now uses `os.getenv()` instead of `os.environ[]`. Adds `OCR_ENABLED` flag. Missing credentials return a clear `RuntimeError` instead of `KeyError` crash.

111. **V006 database indexes** — 7 new indexes on high-query columns: `api_keys(key_hash)`, `api_keys(status WHERE active)`, `oauth_tokens(token_hash)`, `usage_events(tenant_id, event_type, created_at)`, `billing_customers(tenant_id)`, `billing_customers(stripe_customer_id)`, `tenant_features(tenant_id)`.

## Wave 21 — Observability & Operations (v3.5.0 API)

112. **Prometheus metrics via prometheus-fastapi-instrumentator** — Exposes `/metrics` endpoint with `http_requests_total`, `http_request_duration_seconds` histogram, `http_request_size_bytes`. `/health`, `/metrics`, `/docs`, `/openapi.json` excluded from instrumentation to avoid noise. No auth on `/metrics` (internal only in production; CF tunnel doesn't expose it externally).

113. **X-Request-ID correlation middleware** — Pure ASGI middleware generates UUID4 hex per request. Accepts client-provided `X-Request-ID` header (for load balancer passthrough). Injected into `request.state.request_id` and response header. Placed between CORS and TenantContext in the middleware stack so all downstream middleware have access.

114. **Structured JSON logging with python-json-logger** — Root logger reconfigured with `JsonFormatter`. Every log line is valid JSON with `timestamp`, `level`, `logger`, `message` fields. Extra fields (request_id, tenant_id) can be passed via `extra={}`. Uvicorn access log disabled (`--no-access-log`) — Prometheus histograms replace it for latency/status monitoring.

115. **IP-based rate limiting on public endpoints** — `IPRateLimiter` class uses per-IP token buckets (same algorithm as tenant rate limiter). Applied to unauthenticated paths: `/health` (60 rpm), `/billing/plans` (30 rpm), `/billing/onboarding/free` (10 rpm). Max 4096 tracked IPs with FIFO eviction. Integrated into `MeteringRateLimitMiddleware`'s exempt-path branch.

116. **Middleware stack order updated** — Now 5 layers: CORS → RequestID → TenantContext → FeatureGate → MeteringRateLimit. RequestID is between CORS and TenantContext so every request gets an ID before auth validation, and the ID appears in error responses from auth failures.

## Wave 22 — Revenue Activation (v3.6.0 API)

117. **Stripe test mode activation** — `STRIPE_SECRET_KEY` (restricted test key `rk_test_*`) and `STRIPE_WEBHOOK_SECRET` stored in K8s secret `taxlens-stripe`. Stripe enabled in Helm values (`stripe.enabled: true`). Health endpoint now reports `stripe_mode: "test"` so test vs live is always visible.

118. **Webhook endpoint registered** — `we_1TPT6kGghEIUa3k8AK87ALmk` at `dropit.istayintek.com/api/billing/webhook`. Listens for: checkout.session.completed, customer.subscription.updated/deleted, invoice.paid, invoice.payment_failed. Webhook secret stored in K8s secret.

119. **Stripe products and prices created** — 3 products created via API after key permissions were updated: TaxLens Starter (`prod_UOGelXMZCrPHkV`, $29/mo `price_1TPU7uGghEIUa3k8ek4hg4Qc`), Professional (`prod_UOGeNG1PnY24NL`, $99/mo `price_1TPU7zGghEIUa3k8uQ672L8W`), Enterprise (`prod_UOGfQ7Zot1FTns`, $299/mo `price_1TPU85GghEIUa3k83hniJ6iq`). Price IDs stored in K8s secret `taxlens-stripe` and injected as env vars.

120. **Stripe mode detection** — `STRIPE_MODE` constant: "test" for `sk_test_`/`rk_test_` prefixes, "live" for other keys, "disabled" if empty. Exposed in `/api/health` response so operators can verify environment.

121. **Checkout flow verified end-to-end** — `POST /billing/checkout` with admin key creates a valid Stripe Checkout session URL. Session includes tenant_name and plan_tier in metadata for webhook-driven provisioning. Tested with starter tier — returns `checkout_url` pointing to `checkout.stripe.com`.

## Wave 23 — Tax Engine Completeness (v3.7.0 API)

122. **AMT (Form 6251) computation** — Alternative Minimum Tax added: SALT add-back from itemized deductions, AMT exemption with 25% phase-out above threshold ($626,350 single, $1,252,700 MFJ), 26%/28% two-bracket AMT rates, tentative minimum tax compared to regular tax. AMT only triggers when tentative minimum exceeds regular tax — most standard-deduction filers see $0 AMT.

123. **Education credits (Form 8863) — AOTC + LLC** — American Opportunity Tax Credit: 100% of first $2K + 25% of next $2K expenses = $2,500 max, 40% refundable. Lifetime Learning Credit: 20% of up to $10K expenses = $2,000 max, nonrefundable. Both phase out between $80K-$90K single ($160K-$180K MFJ). MFS cannot claim. Refundable portion added to total_payments (increases refund even if tax is $0).

124. **QBI phase-out with W-2 wage limitation** — Replaced simplified flat 20% with proper IRS rules. Below threshold ($191,950 single, $383,900 MFJ): full 20%. In phase-out range ($50K single, $100K MFJ): linear reduction of excess over W-2 wage cap. Above range: limited to greater of 50% W-2 wages or 25% W-2 wages + 2.5% UBIA. For Schedule C sole proprietors (no W-2 wages to themselves), QBI phases to $0 — this correctly represents IRS treatment.

125. **EducationExpense dataclass** — Per-student data class with student_name, qualified_expenses, credit_type ("aotc" or "llc"). Passed as `education_expenses` parameter to `compute_tax()`. Backward compatible — defaults to empty list.

## Wave 24 — EITC (v3.8.0 API)

126. **Earned Income Tax Credit (EITC) — Schedule EIC** — Full 2025 EITC implementation with phase-in, plateau, and phase-out ranges for 0, 1, 2, and 3+ qualifying children. Max credits: $649 (0), $4,328 (1), $7,152 (2), $8,046 (3+). Phase-in rates: 7.65%/34%/40%/45%. Phase-out rates: 7.65%/15.98%/21.06%/21.06%. MFJ gets higher phase-out start ($17,740/$29,200 vs $10,620/$22,080). Fully refundable — added to `line_33_total_payments`. EITC is the largest refundable credit in the US tax system.

127. **EITC disqualification rules** — MFS filers cannot claim EITC (IRS has limited exception for separated spouses, not implemented). Investment income (interest + dividends + capital gains) exceeding $11,600 disqualifies the credit entirely. This prevents high-wealth/low-wage filers from claiming.

128. **Earned income = W-2 wages + net SE taxable** — EITC earned income includes W-2 wages plus net self-employment taxable income (92.35% of Schedule C profit). Investment income, interest, and dividends are NOT earned income. Zero earned income = zero EITC regardless of filing status or dependents.

129. **EITC phase-out uses greater of AGI or earned income** — Per IRS rules, the phase-out income test uses the greater of AGI or earned income. This prevents filers with large above-the-line deductions (like SE tax deduction) from artificially lowering their phase-out income.

## Wave 25 — CDCC + Saver's Credit (v3.9.0 API)

130. **Child and Dependent Care Credit (Form 2441)** — AGI-based credit rate: 35% at $15K AGI, decreasing by 1% per $2K of AGI above $15K, floor at 20%. Max qualifying expenses: $3,000 for 1 dependent, $6,000 for 2+. Expenses capped at earned income. Nonrefundable — cannot exceed tax liability. Applied after education credits and before EITC in the credit ordering.

131. **CDCC rate computation** — Rate steps down in 1% increments: `max(20%, 35% - floor((AGI - $15,000) / $2,000))`. At AGI $43,000+, rate floors at 20%. This graduated structure benefits lower-income families more while still providing a benefit to moderate-income families.

132. **Retirement Savings Credit (Form 8880)** — Three-tier credit for IRA/401(k) contributions: 50% for AGI ≤ $23,750 (single), 20% for ≤ $25,750, 10% for ≤ $36,500, 0% above. MFJ thresholds doubled. Max eligible contribution $2,000 per person. Nonrefundable. Incentivizes low-income retirement saving.

133. **Credit ordering: CTC → Education → CDCC → Saver's → EITC** — Nonrefundable credits (CTC, education, CDCC, saver's) reduce tax liability sequentially before refundable credits (EITC, refundable AOTC) are added to payments. This ordering maximizes refundable credit value since nonrefundable credits can't generate a refund below $0.

## Wave 26 — Estimated Tax Penalty (v3.10.0 API)

134. **Estimated tax penalty (Form 2210 simplified)** — Applies when: (1) amount owed ≥ $1,000, AND (2) withholding + estimated payments < required annual payment, AND (3) prior year tax is known. Required payment = lesser of 90% current year tax or 100% prior year tax (110% if prior year AGI > $150K, $75K MFS). Penalty = underpayment × 8% annual rate. Added to amount owed.

135. **Prior year tax as optional parameter** — `prior_year_tax` and `prior_year_agi` are optional parameters to `compute_tax()`. First-time filers or users without prior year data get no penalty. This avoids false penalties while enabling accurate computation for returning filers. Prior-year import (future wave) will populate these automatically.

136. **Simplified short method over annualized** — Full Form 2210 supports annualized income installment method for uneven quarterly income. We implement the short method (same underpayment all 4 quarters) which covers the vast majority of filers. The annualized method is a future enhancement for self-employed with seasonal income.

## Wave 27 — Credit Form PDFs (v3.11.0 API)

137. **ReportLab for credit forms (not fillable IRS PDFs)** — The 6 new credit forms (Form 6251, 8863, Schedule EIC, 2441, 8880, 2210) use ReportLab-generated summary PDFs rather than official IRS fillable templates. IRS fillable PDFs for these forms have complex multi-page structures with conditional sections (e.g., Form 6251 has 7 lines of adjustments). ReportLab summaries show the key computation values clearly. Official IRS templates can be added later as a follow-up.

138. **Conditional PDF generation** — Each credit form is only generated when its credit/penalty is nonzero. This matches the existing pattern (Schedule SE only if SE tax > 0, Schedule D only if capital transactions exist). Prevents cluttering draft output with empty forms.

139. **Summary page credits section** — The branded cover page now includes a Credits section showing CTC, education credits, CDCC, Saver's, EITC, AMT, and estimated tax penalty. Previously only showed total tax and withholding without breaking out credits.

140. **Form 6251 and 8863 added to forms_generated** — Waves 23 added AMT and education credit computation but didn't add their form names to `forms_generated`. Fixed: engine now appends "Form 6251" (if AMT > 0) and "Form 8863" (if any education credit) to the list.

## Wave 28 — Structured Dependent Model (v3.12.0 API)

141. **Dependent dataclass with age-based eligibility methods** — Each `Dependent` record has `qualifies_ctc()` (under 17), `qualifies_eitc()` (under 19, 24 student, disabled), `qualifies_cdcc()` (under 13, disabled). Engine derives `num_ctc_children`, `num_eitc_children`, `num_cdcc_dependents` from the list. This replaces the naive assumption that all dependents qualify for all credits.

142. **Backward-compatible with num_dependents integer** — When no structured `dependents` list is provided, `num_dependents` is used as before. Empty `dependents=[]` triggers fallback to integer. Structured list overrides the integer count. Existing smoke tests, MCP tools, and portal calls continue working without modification.

143. **CTC doesn't waive age for disabled** — Unlike EITC and CDCC (which treat disabled dependents as qualifying regardless of age), CTC strictly requires under 17. Disabled adults 17+ qualify for the Other Dependents Credit (ODC, $500), not the full CTC ($2,000). ODC is not yet implemented; disabled dependents 17+ get no CTC until ODC is added.

144. **No-DOB assumes qualifying** — If `date_of_birth` is empty or invalid, `age_at_year_end()` returns -1 and all qualification methods return True. This prevents data entry gaps from accidentally disqualifying dependents and maintains backward compat with tests that don't set DOB.

## Wave 29 — Multi-Year Tax Config (v3.13.0)

145. **TaxYearConfig via get_year_config(year)** — All inflation-adjusted constants (brackets, deductions, EITC, AMT, QBI, Saver's, SS wage base) are stored in per-year dicts (`_YEAR_2024`, `_YEAR_2025`). `get_year_config()` returns a SimpleNamespace. Statutory rates (NIIT 3.8%, SE 15.3%, AOTC max $2,500) are constant across years and defined once at module level.

146. **compute_tax(tax_year=) parameter** — Engine accepts `tax_year` (default 2025) and loads year-specific config via `c = get_year_config(tax_year)`. All ~50 constant references in compute_tax() use `c.` prefix. Thread-safe — no module-level state mutation.

147. **Backward-compatible module-level exports** — `from tax_config import *` still works and exports 2025 constants. Existing tests, MCP server, state engine, and PDF generator continue using module-level names unchanged. Only `compute_tax()` uses the year-specific config object.

148. **2024 constants from Rev. Proc. 2023-34** — Full 2024 federal tax constants: brackets (single 10% at $11,600 vs 2025's $11,925), standard deduction ($14,600 vs $15,000), SS wage base ($168,600 vs $176,100), AMT exemption ($85,700 vs $88,100), QBI limit ($182,100 vs $191,950), EITC max 0-child ($632 vs $649), IL exemption ($2,625 vs $2,775).

149. **MCP parity via `_build_inputs` expansion** — Rather than creating separate MCP-specific engine wrappers, all new engine params (dependents, education, care, retirement, multi-state, penalty) are exposed through `_build_inputs()` dict-to-dataclass conversion. MCP clients send plain dicts, `_build_inputs` constructs the correct dataclass instances. Same pattern as the original implementation, just extended.

150. **`get_tax_config` as MCP tool (not just resource)** — Exposes tax brackets, deductions, credit limits, and penalty constants as a callable tool so agents can look up rules before computing. Also available as `taxlens://config/{year}` resource for MCP clients that support resource reads. Tool params (filing_status, tax_year) allow targeted lookups vs the resource which returns a single filing status.

151. **MCP tool signatures mirror engine params** — Every `compute_tax()` parameter is now accessible via MCP `compute_tax_scenario`. Agent clients get the same power as the REST API without needing to construct Pydantic models. The dict-based interface is more natural for LLM tool use.

## PDF Template Provenance

| Template | Source | SHA256 (first 8) | Match |
|----------|--------|-------------------|-------|
| f1040.pdf | OpenFile embedded | 0a7a54... | OpenFile production |
| f1040s1.pdf | OpenFile embedded | 2fe9bc... | OpenFile production |
| f1040sa.pdf | IRS 26f25 | c14acf... | Official byte-match |
| f1040sb.pdf | IRS 26f25 | dd1ec3... | Official byte-match |
| f1040sc.pdf | IRS 26f25 | ddf401... | Official byte-match |
| f1040sd.pdf | IRS 26f25 | 90564c... | Official byte-match |
| f1040sse.pdf | IRS 26f25 | 05bc2b... | Official byte-match |
| f1040s2.pdf | IRS irs-pdf | 64d867... | Official IRS 2025 |
| f8959.pdf | IRS irs-pdf | 13e640... | Official IRS 2025 |
| f8960.pdf | IRS irs-pdf | 9b323b... | Official IRS 2025 |
| il1040.pdf | IRS 26f25 | 30651b... | Official byte-match |
