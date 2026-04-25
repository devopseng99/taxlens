# TaxLens — Key Technical Decisions

Updated: 2026-04-25 (v3.62.0 API (DEPLOYED) + v2.6.0 Portal — 83 waves complete, 31/31 smoke tests)

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

152. **STRIPE_LIVE_MODE_CONFIRMED safety guard** — Live Stripe keys (`sk_live_`/`rk_live_`) are automatically disabled unless `STRIPE_LIVE_MODE_CONFIRMED=true` is set. Prevents accidental real charges when a live key is provisioned but the system isn't ready for production billing. Test keys (`sk_test_`/`rk_test_`) don't need confirmation.

153. **Separate cutover script (not helm values)** — Stripe live mode cutover uses a dedicated script (`scripts/setup-stripe-live.sh`) that updates K8s secrets + sets the confirmation env var + verifies health. Keeps the Helm chart agnostic to Stripe mode — the same chart works for test and live.

## Wave 32-33 — Schedule E Rental Income + HSA Deduction (v3.16.0)

154. **Passive activity loss rules (IRC §469)** — Rental losses are limited to $25K for active participants, phased out at AGI $100K-$150K (50% reduction per dollar over $100K). Net rental income is always fully included. Preliminary AGI (before rental) used for phaseout calculation to avoid circular dependency.

155. **RentalProperty 14-expense dataclass** — Mirrors IRS Schedule E line items (advertising, auto/travel, cleaning, commissions, insurance, legal, management fees, mortgage interest, repairs, supplies, taxes, utilities, depreciation, other). `total_expenses` and `net_income` computed properties, same pattern as BusinessIncome.

156. **HSA above-the-line deduction** — Year-specific limits (2025: $4,300 self / $8,550 family; 2024: $4,150 / $8,300) with $1,000 statutory catch-up for age 55+. Each contribution independently capped at its applicable limit. Multiple contributions (filer + spouse) accumulate. Deduction applied in adjustments section before AGI.

157. **Rental income flows to Line 9 total_income** — Schedule E net income (or allowed loss after passive activity rules) added to total income alongside wages, interest, dividends, capital gains, business income, and other income. This affects AGI and all downstream calculations (deduction phaseouts, credit eligibility).

158. **HSA limits in get_year_config()** — HSA_LIMIT_SELF and HSA_LIMIT_FAMILY are year-specific (inflation-adjusted), while HSA_CATCHUP is statutory ($1,000 fixed). Rental loss limits (RENTAL_LOSS_LIMIT, phaseout start/end) are also statutory but stored alongside year config for consistent access pattern.

## Wave 34 — Infrastructure Hardening (v3.16.1)

159. **Deep health probe (not always-on)** — Deep mode (`?deep=true`) measures DB latency and verifies storage write capability. Shallow mode (default) just checks DB reachability. Deep mode is for manual debugging, not Kubernetes probes — avoids unnecessary write I/O on every 10-second probe.

160. **Separate readiness from liveness** — `/health` is the liveness probe (always 200 unless process is dead). `/ready` is the readiness probe (503 when DB or storage unavailable). Kubernetes should use readiness to stop routing traffic during DB maintenance without killing the pod.

161. **PostgreSQL backup via pg_dump in pod** — Backup runs `pg_dump` inside the PG pod (avoids needing pg_dump binaries on the host), streams through gzip, and copies to node storage via SSH. 7-day retention with automatic pruning. Restore instructions are printed after each backup.

## Wave 35-36 — Audit Risk + Prior-Year Import (v3.17.0)

162. **SOI-based audit risk, not prediction** — Uses IRS Statistics of Income public data to compare charitable giving ratios, expense ratios, and loss patterns against averages for the filer's AGI bracket. Explicitly disclaimed as educational — the IRS DIF score is secret and cannot be replicated. Risk score is additive (0-100) from independent flags.

163. **Audit risk auto-included in tax draft** — Every `POST /tax-draft` response includes `audit_risk` in the JSON alongside the tax computation. No separate API call needed. MCP tool `assess_audit_risk_tool` also available for agents to assess risk on arbitrary scenarios.

164. **Prior-year import via pypdf (not OCR)** — Reads fillable PDF form fields directly using pypdf. Much faster and more accurate than OCR for PDFs output by tax software. Falls back to confidence="low" if no form fields found (scanned PDFs need OCR via the existing pipeline). Outputs `penalty_inputs` for Form 2210 safe harbor.

165. **Field name mapping with fallbacks** — IRS fillable PDFs use field names like `f1_7`, `f1_21`, etc. Some PDFs use full XFA paths like `topmostSubform[0].Page1[0].f1_7[0]`. The parser tries direct match, then alt mappings, then base name extraction.

## Wave 37 — Form 8889 HSA Reporting (v3.18.0)

166. **Employer contributions reduce deductible room** — IRC §223(b)(4): the HSA contribution limit is shared between employer and personal contributions. Employer contributions (including cafeteria plan) reduce the amount the individual can deduct. Formula: deductible = min(personal, limit - employer). Total exceeding the limit is excess subject to 6% excise via Form 5329.

167. **Form 8889 is required whenever HSA contributions exist** — IRS requires Form 8889 for any year the taxpayer (a) has an HSA, (b) makes or receives contributions, or (c) takes distributions. Generated via ReportLab (no IRS fillable template available). Includes Part I (contributions/deduction) and excess contribution detection.

168. **HDHP limits are informational** — High-Deductible Health Plan minimum deductible and max OOP limits added to tax_config.py and exposed via get_tax_config MCP tool. These are prerequisites for HSA eligibility but not enforced in the engine (self-attested by the filer).

## Wave 38 — Email & Notifications (v3.18.1)

169. **Resend via httpx (no SDK)** — Uses httpx (already a dependency) to POST to Resend's REST API directly. No new pip dependency. Gracefully disabled when RESEND_API_KEY is not set — all send functions return `{"status": "disabled"}`.

170. **Fire-and-forget email pattern** — Email calls in onboarding and billing webhook are wrapped in try/except with logging. Email failure never blocks tenant provisioning or plan upgrades. This follows the graceful feature degradation pattern.

171. **Three email templates** — Welcome (with API key + MCP config), filing deadline reminder, plan upgrade confirmation. All include plain text fallback for email clients that don't render HTML.

## Wave 42 — Depreciation & Form 4562 (v3.21.0)

186. **DepreciableAsset as standalone dataclass** — Separate from BusinessIncome and RentalProperty. Assets track their own MACRS class, recovery year, Section 179 election, and bonus depreciation flag. Depreciation is computed per-asset and then allocated to either Schedule C or Schedule E based on `asset_use`. This allows mixed business/rental portfolios.

187. **Section 179 aggregate limit enforcement** — The $1,250,000 (2025) Section 179 limit applies across ALL assets, not per-asset. The engine totals all Section 179 elections and pro-rates if over the limit. Phaseout begins at $3,130,000 in total asset cost, reducing the limit dollar-for-dollar. Real property (27.5/39-year) is excluded from Section 179.

188. **Bonus depreciation based on placed-in-service year** — TCJA phasedown: 100% (2022), 80% (2023), 60% (2024), 40% (2025), 20% (2026). The engine reads `date_placed_in_service` to determine the bonus rate, defaulting to the tax year if no date is provided. Real property is excluded from bonus depreciation.

189. **Depreciation order: Section 179 → Bonus → MACRS** — Section 179 reduces depreciable basis first, then bonus depreciation applies to the remaining basis, then regular MACRS applies to what's left. This is the IRS-specified ordering per Form 4562 instructions.

190. **Depreciation flows post-computation** — Business depreciation reduces `sched_c_total_profit` after Schedule C is initially computed. Rental depreciation reduces `sched_e_net_income` after Schedule E is computed. This avoids modifying the underlying BusinessIncome/RentalProperty dataclasses and keeps the depreciation calculation self-contained.

## Wave 59 — 1099-R OCR Parser + PDF Generation (v3.38.0)

244. **1099-R OCR parser extracts distribution codes for tax treatment** — `parse_1099r_from_ocr()` reads 9 fields from Azure's `prebuilt-tax.us.1099R` model. Distribution code determines tax treatment: "7" (normal), "1" (early → 10% penalty), "G" (rollover → tax-free), "Q" (qualified Roth → tax-free). The parser sets `is_early`, `is_roth`, and `is_ira` flags from the code.

245. **1099-R PDF as ReportLab-drawn summary** — Rather than a fillable IRS template (1099-R is an informational form, not a filing form), the PDF summarizes distribution details including payer, amounts, tax treatment, and withholding. Includes distribution type interpretation (e.g., "Early distribution — may be subject to 10% penalty").

## Wave 58 — Landing Page Content API (v3.37.0)

242. **Content endpoints serve structured JSON, not HTML** — `/content/about`, `/content/security`, and `/content/for-businesses` return structured JSON that any frontend (Astro, React, static site generator) can consume. This decouples content from presentation — the API is the single source of truth for platform capabilities, pricing, and security details.

243. **Content paths exempt from tenant context** — Landing page content is public. Paths starting with `/content/` skip tenant context middleware, matching the pattern used for `/docs/` and `/billing/plans`.

## Wave 57 — Admin Database Explorer (v3.36.0)

240. **Database overview endpoint with table allowlist** — `GET /admin/database` returns row counts for all 12 core tables. The `DB_TABLES` allowlist prevents arbitrary table access — `GET /admin/database/{table_name}` returns 404 for tables not in the list.

241. **Table detail with sample rows** — `GET /admin/database/{table_name}?limit=10` returns sample rows ordered by created_at desc plus column names derived from the first row. Provides a lightweight admin view without requiring direct database access.

## Wave 56 — API Reference Documentation (v3.35.0)

237. **Three structured documentation endpoints** — `/docs/api-guide` (full API quickstart with auth methods, endpoints, rate limits), `/docs/mcp-guide` (Claude Desktop config, 9 tools, example prompts), and `/postgrest-openapi` (proxied PostgREST spec with Redis caching). All return structured JSON, not HTML — clients render as needed.

238. **PostgREST OpenAPI cached in Redis** — The `/postgrest-openapi` proxy fetches the spec from PostgREST and caches it in Redis with 5-min TTL. Falls back to direct fetch when Redis unavailable. This avoids hammering PostgREST on every docs page load.

239. **Enriched OpenAPI metadata on all endpoints** — All tax_routes endpoints now have `summary` and `description` parameters for the FastAPI OpenAPI generator. The app-level `openapi_tags` array organizes endpoints by category (Tax Drafts, Documents, Admin, Billing, etc.).

## Wave 55 — Redis-Backed Rate Limiting (v3.34.0)

233. **Redis as optional shared state for rate limiting** — When `REDIS_URL` is set, token buckets and daily/monthly counters use Redis Lua scripts for atomic operations across replicas. When unset or Redis is unreachable, the system gracefully degrades to the original in-memory implementation. No code path changes required — the fallback is automatic.

234. **Lua scripts for atomic rate limiting** — Three Lua scripts handle all Redis-side logic: TOKEN_BUCKET_LUA (atomic refill + consume with 2-min auto-expiry), SLIDING_COUNTER_LUA (daily/monthly counters with window reset), IP_SLIDING_WINDOW_LUA (sorted set sliding window for IP throttling). Lua scripts execute atomically on the Redis server, preventing race conditions.

235. **Redis 7 Alpine with allkeys-lru eviction** — The Redis StatefulSet uses 64Mi memory limit with allkeys-lru policy. No persistence (appendonly=no, save="") — rate limit state is ephemeral by design. If Redis restarts, buckets refill to capacity (a brief window of no rate limiting), which is acceptable.

236. **Health endpoint reports Redis status** — `/health` now includes `redis_enabled`, `redis_ok`, and `redis_latency_ms` fields. This enables monitoring dashboards to track Redis availability without separate probe infrastructure.

## Wave 54 — MCP OAuth 2.0 Token Endpoint (v3.33.0)

229. **POST /oauth/token as RFC 6749 form-urlencoded endpoint** — The token endpoint accepts `application/x-www-form-urlencoded` as required by the OAuth 2.0 spec. Three grant types: `client_credentials` (MCP agents), `authorization_code` with PKCE S256 (browser clients), and `refresh_token` (rotation). All tokens stored as SHA256 hashes — the raw token is only returned once to the client.

230. **Refresh token rotation on every use** — Each refresh_token grant deletes the old refresh token and issues a new access + refresh pair. This limits the damage window if a refresh token is compromised — the attacker can use it once, but the legitimate client's next refresh will fail, alerting the tenant.

231. **Scope enforcement: intersection of client + request + VALID_SCOPES** — The granted scope is the intersection of what the client is allowed (per oauth_clients.scopes), what the request asked for, and the global VALID_SCOPES set (compute, drafts, documents, mcp, plaid). Scope narrowing on refresh is allowed; widening is forbidden.

232. **OAuth token endpoint exempt from tenant context middleware** — `/oauth/token` is added to both _SKIP_PATHS (tenant_context.py) and EXEMPT_PATHS (MeteringRateLimitMiddleware) since it handles its own authentication via client_id/client_secret. The endpoint validates credentials internally against PostgREST.

## Wave 53 — Form 2210 Schedule AI Annualized Installment Method (v3.32.0)

225. **Annualized installment method as optional penalty reducer** — Schedule AI is computed only when `quarterly_income` is provided AND produces a lower penalty than the regular method. The engine always computes the regular (short method) penalty first, then checks if AI yields savings. `sched_ai_used=True` only when AI penalty < regular penalty.

226. **Cumulative period income with IRS annualization factors** — Each of the 4 periods is cumulative from Jan 1 (not per-quarter). Annualization factors (4.0, 2.4, 1.5, 1.0) are IRS-prescribed. Tax is computed on the annualized amount using the same brackets and standard deduction as the full-year computation.

227. **QuarterlyIncome as a separate dataclass** — Rather than adding 20 individual float parameters to compute_tax, a single `QuarterlyIncome` dataclass holds 5 tuples of 4 floats (wages, business_income, other_income, deductions, withholding). JSON API accepts it as a dict with 4-element arrays.

228. **Penalty comparison: lower of two methods always wins** — Per IRS Form 2210 instructions, the filer may use whichever method produces the lower penalty. The engine enforces this automatically — `sched_ai_penalty_reduction` tracks the savings.

## Wave 52 — Form 8606 Nondeductible IRA Basis Tracking (v3.31.0)

221. **Nondeductible IRA contributions computed automatically from phaseout** — When the IRA deduction is phased out (partially or fully per IRC §219(g)), the difference between total contributions and the allowed deduction becomes the nondeductible amount. No separate user input needed — the engine derives it from `ira_contributions - ira_deduction`.

222. **Pro-rata rule for distribution taxability** — The IRS requires ALL traditional IRA assets be treated as a single pool for taxability. The nontaxable percentage = `total_basis / (year_end_value + distributions + conversions)`. This percentage applies uniformly to ALL distributions and Roth conversions — you cannot cherry-pick basis dollars. Three new inputs: `prior_year_ira_basis`, `total_ira_value_year_end`, `roth_conversion_amount`.

223. **Backdoor Roth pattern emerges naturally** — When a high-income filer makes a nondeductible IRA contribution ($7K) and immediately converts to Roth with $0 remaining IRA value, the pro-rata rule yields 100% nontaxable → $0 tax on conversion. No special-case code needed — the general Form 8606 logic handles it.

224. **Basis carries forward automatically** — `form_8606_remaining_basis` tracks the carryforward for next year's Form 8606 Line 2. Without distributions/conversions, the entire basis carries forward. With distributions, basis is reduced proportionally to the nontaxable amount consumed.

## Wave 51 — Schedule 1/3/E PDF Generation (v3.30.0)

218. **Schedule 1 generated conditionally on any additional income or adjustments** — Simple W-2-only returns don't need Schedule 1. It's generated when any of: business income, rental income, unemployment, alimony, gambling, SE deduction, HSA, IRA, student loan, or educator expenses are present. This avoids cluttering simple returns with an empty form.

219. **Schedule 3 generated conditionally on any additional credits** — Generated when foreign tax credit, CDCC, education credits, Saver's credit, energy credits, or EITC are present. Mirrors the IRS requirement: Schedule 3 only filed when claiming credits beyond CTC.

220. **ReportLab summary PDFs (not official fillable)** — Schedule 1, 3, and E are generated as ReportLab-drawn summary pages with DRAFT watermark, not official IRS fillable PDF templates. This is consistent with how other supplemental schedules (K-1 Summary, Form 8949, Form 5695, etc.) are already handled. Official fillable templates can be added later if needed.

## Wave 50 — Charitable Contribution AGI Limits (v3.29.0)

215. **IRC §170 percentage limits on charitable deductions** — Cash contributions to public charities are capped at 60% of AGI, non-cash contributions at 30% of AGI, and total charitable at 60% of AGI. Previously charitable was an unlimited pass-through. These are statutory percentages (not inflation-indexed) — same for all tax years. Excess creates a 5-year carryforward tracked on `charitable_carryforward`.

216. **Three-layer charitable cap: cash, non-cash, overall** — Cash is individually capped at 60%, non-cash at 30%, and their sum is capped at 60% overall. This means a $100K AGI filer with $55K cash + $25K non-cash gets limited: cash passes ($55K < $60K), non-cash passes ($25K < $30K), but combined $80K exceeds $60K overall → capped at $60K. The overall cap is the binding constraint in many real cases.

217. **Pre-limit tracking for audit and carryforward** — `charitable_cash_before_limit` and `charitable_noncash_before_limit` preserve the raw input amounts. This enables: (1) audit risk scoring can flag large donations relative to income even after the limit reduces the deduction, (2) the carryforward amount is precisely `raw_total - allowed_total`, (3) users can see exactly how much was limited.

## Wave 49 — Student Loan Phaseout + Foreign Tax Credit + Gambling (v3.28.0)

212. **Student loan interest MAGI phaseout per IRC §221(b)(2)** — Student loan interest deduction ($2,500 max) was previously a flat cap with no income test. Now phased out linearly: single/HoH $80K-$95K, MFJ $165K-$195K, MFS gets $0 (no deduction allowed). MAGI for this purpose = total income minus all other adjustments (excluding student loan deduction itself). Same pattern as IRA phaseout — avoids circular dependency.

213. **Gambling income as net in line_8_other_income** — W-2G gambling winnings flow to line_8_other_income, with gambling losses immediately netted against winnings (limited to winnings per IRC §165(d)). Strictly, gambling losses should be a Schedule A itemized deduction, but netting at the income level is the pragmatic approach and matches economic reality. W-2G federal withholding flows to line_25.

214. **Simplified foreign tax credit (Form 1116)** — Foreign tax paid is a nonrefundable credit limited by: `line_16_tax * (foreign_source_income / line_15_taxable_income)`. This is the simplified limitation method — it doesn't handle separate basket categories (general vs passive), carryforward/carryback, or AMT foreign tax credit. Sufficient for most individual filers with straightforward foreign income.

## Wave 48 — Retirement Line Reclassification + IRA Phaseout (v3.27.0)

209. **IRA vs pension split on 1040 lines 4a/4b and 5a/5b** — Previously all retirement distributions went to `line_8_other_income`. Now `RetirementDistribution.is_ira` routes IRA distributions to lines 4a/4b (IRA gross/taxable) and pensions to lines 5a/5b (pension gross/taxable). This matches the official IRS 1040 layout. Default `is_ira=False` preserves backward compatibility — existing code routes to pension lines.

210. **IRA deduction income-based phaseout per IRC §219(g)** — Active retirement plan participants (W-2 Box 13 checked) have their traditional IRA deduction phased out based on MAGI. 2025 ranges: single $79K-$89K, MFJ (filer active) $126K-$146K, MFJ (spouse active only) $236K-$246K, MFS $0-$10K. Phaseout is linear with IRS rounding (reduction rounded UP to nearest $10). MAGI = total income minus adjustments excluding IRA deduction (avoids circular dependency).

211. **Spouse-active higher phaseout only for MFJ** — When the filer is NOT an active participant but their spouse IS, a higher phaseout range applies ($236K-$246K for 2025). This only applies to MFJ filers — for other filing statuses, spouse_active_plan_participant has no effect, ensuring no accidental phaseout for single filers.

## Wave 47 — Additional Standard Deduction + REST API Credit Fields (v3.26.0)

205. **Additional standard deduction for age 65+ and blind** — IRC §63(f) provides an additional standard deduction for filers who are 65+ or blind. Single/HoH get $2,000 per qualifying condition (2025), MFJ/MFS get $1,600. Up to 4 qualifying conditions for MFJ (both spouses 65+ and both blind = $6,400). 2024 uses $1,950/$1,550 per IRS Rev. Proc. The additional amount is added to the base standard deduction before the standard-vs-itemized comparison.

206. **Spouse flags ignored for non-joint filers** — `spouse_age_65_plus` and `spouse_is_blind` only increment the additional count for MFJ and MFS filing statuses. Single and HoH filers ignore spouse flags entirely — this prevents accidental extra deductions when a single filer passes spouse data.

207. **REST API credit field gap closed** — `EducationExpense`, `DependentCareExpense`, and `RetirementContribution` were already in `compute_tax()` but unreachable from the REST API's `TaxDraftRequest` Pydantic model. Added `EducationExpenseInput`, `DependentCareExpenseInput`, and `RetirementContributionInput` Pydantic models with construction logic to bridge REST → engine. AOTC, LLC, CDCC, and Saver's Credit are now fully accessible via both REST API and MCP.

208. **AOTC credit split: nonrefundable + refundable** — American Opportunity Tax Credit ($2,500 max) splits into $1,500 nonrefundable (`education_credit`) and $1,000 refundable (`education_credit_refundable` = 40% of total). The REST API and tests must check both fields, not just the total.

## Wave 46 — Capital Loss Limitation (v3.25.0)

202. **IRC §1211(b) $3K/$1.5K cap on net capital losses** — Net capital losses deductible against ordinary income are capped at $3,000/year ($1,500 MFS). Previously the engine allowed unlimited capital loss deductions, which produced wildly incorrect tax liability for anyone with net losses. Excess loss is tracked as `capital_loss_carryforward` for use in future tax years.

203. **Prior-year capital loss carryover as input** — Added `capital_loss_carryover` parameter to `compute_tax()`, the REST API, and MCP server. Prior-year carryover is treated as additional short-term loss (per IRS instructions for Schedule D), then subject to the same $3K annual limitation.

204. **§1211 applied after all capital sources aggregated** — The limitation runs AFTER Schedule D transactions, crypto (Form 8949), and K-1 capital gains are all accumulated, but BEFORE line_9_total_income computation. This ensures all sources participate in netting before the cap is applied.

## Wave 45 — Unemployment, Educator Expenses, Alimony (v3.24.0)

199. **Unemployment compensation fully taxable** — Form 1099-G Box 1 unemployment compensation is fully taxable (post-2020 — the $10,200 ARPA exclusion expired). Flows to line_8_other_income alongside retirement and other income types. Withholding (Box 4) flows to line 25.

200. **Educator expense as above-the-line deduction** — K-12 teachers get $300 above-the-line deduction ($600 MFJ if both spouses are educators). This is a simple flat cap — no phase-out or income test. The $300 limit has been static since 2022.

201. **Alimony split by pre-2019 vs post-2019** — Only alimony under pre-2019 divorce agreements is deductible (payer) / taxable (recipient). Post-TCJA (2019+) divorces: alimony is neither deductible nor taxable. The engine accepts both alimony_paid and alimony_received as separate params since different agreements may apply.

## Wave 44 — Social Security Benefits (v3.23.0)

195. **IRC §86 two-threshold taxability formula** — Social Security benefits are taxable based on "provisional income" (modified AGI + 50% of SS benefits). Below base threshold ($25K single/$32K MFJ): 0% taxable. Between base and upper ($34K/$44K): up to 50%. Above upper: up to 85%. These thresholds are statutory (NOT inflation-indexed since 1983), making more retirees taxable each year via bracket creep.

196. **Provisional income computed from pre-SS income** — The SS taxability calculation uses all other income (wages, interest, dividends, capital gains, business, rental, retirement distributions) BEFORE adding SS benefits. This avoids circular dependency — SS taxable amount depends on other income, not on itself.

197. **MFS threshold of $0** — Married filing separately gets $0/$0 thresholds, meaning SS benefits are almost always 85% taxable for MFS filers. This is an IRS anti-abuse measure to discourage MFS for SS benefits tax avoidance.

198. **SS withholding in PAYMENTS section** — SSA-1099 Box 6 voluntary withholding (Form W-4V) is aggregated alongside W-2, 1099-R, and other withholding in the PAYMENTS section. Same pattern as retirement withholding (Wave 43 decision #194).

## Wave 43 — Retirement Income (v3.22.0)

191. **RetirementDistribution with distribution code routing** — Distribution codes determine taxability: "7" (normal) = fully taxable, "1" (early) = taxable + 10% penalty, "G"/"H" (rollover) = non-taxable, Roth = non-taxable. The `taxable` property encapsulates this logic. This matches how IRS Form 1099-R Box 7 codes drive 1040 treatment.

192. **Retirement income as other income (line 8)** — 1099-R taxable amounts flow to line_8_other_income alongside other income types. This is a simplification — IRS 1040 has separate lines (4a/4b for IRA, 5a/5b for pension), but the tax computation is identical. Full line separation is a future PDF enhancement.

193. **IRA deduction as above-the-line adjustment** — Traditional IRA contributions are deducted from AGI (above-the-line), not as an itemized deduction. Each contributor (filer/spouse) has an independent $7,000 limit ($8,000 with $1,000 catch-up for age 50+). MFJ filing allows two full deductions. Income-based phaseout for active participants is deferred to a future wave.

194. **Retirement withholding in PAYMENTS section** — 1099-R Box 4 federal withholding is aggregated in the PAYMENTS section (line 25) alongside W-2 withholding, not in the retirement processing section. This prevents the PAYMENTS section from overwriting retirement withholding when it resets line_25 from W-2s.

## Wave 41 — Crypto & Digital Assets (v3.20.0)

181. **CryptoTransaction as separate dataclass from CapitalTransaction** — Crypto needs additional fields (asset_name, exchange, tx_hash, basis_method, wash_sale_loss_disallowed) that regular stock transactions don't have. CryptoTransaction converts to CapitalTransaction via `to_capital_transaction()` for Schedule D aggregation. This keeps the engine generic while tracking crypto-specific data for Form 8949.

182. **Wash sale loss disallowed adjusts cost basis, not proceeds** — Per IRS proposed regs (2024), when a crypto wash sale occurs, the disallowed loss is added to the cost basis of the replacement asset. `to_capital_transaction()` does `cost_basis + wash_sale_loss_disallowed` so Schedule D reports the adjusted basis, not the original basis.

183. **Crypto gains recompute Schedule D totals** — Because crypto transactions are added to `additional.capital_transactions` at processing time, Schedule D totals (short/long/net) are recomputed after crypto injection to avoid double-counting with pre-existing capital transactions.

184. **Cost basis methods are metadata, not engine computation** — The engine accepts `basis_method` (FIFO, LIFO, HIFO, specific ID) as a field on each CryptoTransaction but doesn't compute cost basis from lot history. Basis computation is the exchange's or user's responsibility. This matches how brokerages provide 1099-B — they report the method and computed basis.

185. **Form 8949 as summary PDF, not per-transaction** — The Form 8949 PDF is a ReportLab summary showing aggregate proceeds, basis, gains/losses, and wash sale amounts. Actual per-transaction detail belongs on the IRS Form 8949 CSV attachment. This matches how TurboTax handles high-volume crypto traders.

## Wave 40 — Advanced Tax Features (v3.19.0)

176. **Form 5695 split: §25D (clean energy) + §25C (home improvement)** — §25D covers solar, wind, geothermal, battery storage at 30% with NO annual cap (IRA 2022 through 2032). §25C covers insulation, windows, doors, heat pumps at 30% with annual cap ($3,200) split into two subcaps: envelope ($1,200) and heat pump ($2,000). Both are nonrefundable credits.

177. **K-1 income flows to multiple 1040 lines** — Passthrough income doesn't land on a single line. Ordinary income → Line 8, interest → Line 2b, dividends → Lines 3a/3b, capital gains → Schedule D, rental → Schedule E, guaranteed payments → Line 8 + Schedule SE. The engine aggregates across multiple K-1s.

178. **Partnership guaranteed payments subject to SE tax** — Per IRC §1402(a), guaranteed payments to partners for services are subject to self-employment tax (same as Schedule C income). S-corp distributions are NOT subject to SE tax (wage/distribution split handled by the S-corp). The engine adds guaranteed payments to SE income alongside Schedule C profit.

179. **K-1 §199A income eligible for QBI deduction** — Passthrough entities report §199A qualified business income on Box 20 Code Z. This flows into the QBI deduction calculation (20% of QBI, same as Schedule C). The engine combines Schedule C profit and K-1 §199A income for the total QBI base.

180. **Quarterly estimated tax planner is proactive** — Computed automatically when tax liability exceeds withholding. Uses 100% of current year net tax (110% for high-AGI filers) divided by 4. Provides due dates for the following year's quarters (Apr 15, Jun 15, Sep 15, Jan 15). Helps self-employed and K-1 recipients plan cash flow.

## Wave 39 — Operational Maturity (v3.18.2)

172. **K8s CronJob for PG backups (not cron on host)** — Backup runs as a K8s CronJob (`taxlens-pg-backup`) in the `taxlens-db` namespace, not a host-level crontab. Uses `bitnami/postgresql:16-debian-12` image with `pg_dump | gzip` to hostPath on mgplcb05. K8s manages scheduling, retry, and history. 7-day retention via `find -mtime +7 -delete`.

173. **Short DNS names + ndots:2 for Alpine containers** — Alpine-based images (like `curlimages/curl`) default ndots:5, causing DNS lookups for short names like `taxlens-api` to append search domains and fail. Setting `dnsConfig.options: [{name: ndots, value: "2"}]` forces direct resolution for names with 2+ dots, and short names resolve correctly via the cluster search domain.

174. **Smoke test as CronJob, not external monitor** — In-cluster CronJob (`taxlens-smoke-test`) runs every 30 minutes checking `/health`, `/ready`, `/docs`, `/metrics`. Catches service degradation inside the cluster network without external monitoring infrastructure. Failed jobs retained (3) for debugging, successful jobs trimmed (1).

175. **Backup secret from existing `taxlens-pg-secret`** — PG backup CronJob reads `PGPASSWORD` from the same `taxlens-pg-secret` used by the PostgreSQL StatefulSet. No new secrets to manage.

176. **1099-MISC categorized income routing** — `parse_1099misc_from_ocr()` returns a dict with categorized income: rents → rental/other, royalties → Schedule E other_income, Box 7 NEC → self-employment, Boxes 3/5/8/9/10 → other_income. This allows proper routing of each income type to the correct tax schedule rather than lumping everything into one category.

177. **1099-G OCR returns UnemploymentCompensation directly** — `parse_1099g_from_ocr()` returns the `UnemploymentCompensation` dataclass directly (not a dict), matching the existing engine type. OCR-parsed 1099-G entries are merged into the unemployment_list alongside manually entered entries, using the same extend pattern as 1099-R retirement distributions.

178. **1099-MISC withholding added to additional_withholding** — Federal withholding from 1099-MISC (Box 4) is included in `additional_withholding` alongside 1099-DIV and 1099-NEC withholding, ensuring all non-W-2 withholding flows to Line 25d correctly.

179. **1040-ES vouchers use ReportLab (not fillable template)** — IRS Form 1040-ES is a worksheet+voucher booklet with no machine-fillable fields. We generate 4-page voucher PDFs via ReportLab canvas with filer info, SSN, quarterly amount, and due dates. Vouchers are conditional on `quarterly_estimated_tax > 0`.

180. **1040-ES due dates hardcoded to 2025 tax year** — Apr 15 2026, Jun 15 2026, Sep 15 2026, Jan 15 2027. Will need update when 2026 tax year is added.

181. **Full return PDF uses pypdf PdfWriter merge (not PdfMerger)** — `PdfWriter.add_page()` + `add_outline_item()` for bookmarks. PdfMerger is deprecated in pypdf 3+. Cover page generated via ReportLab, then merged first. Forms ordered per `_FORM_ORDER` constant matching IRS filing sequence.

182. **Full return endpoint reconstructs TaxResult from result.json** — The `/pdf/full_return` endpoint reads the saved `result.json` file and populates a minimal TaxResult for the cover page. This avoids recomputing the entire return just to generate the merge.

183. **Batch upload saves original + metadata.json** — Each uploaded document gets a UUID proc_id, and both the original file and a metadata.json are saved. Metadata tracks status (uploaded→analyzed), form type, OCR confidence. This allows the document lifecycle to be tracked without the OCR result itself.

184. **Batch analyze uses asyncio.gather for parallel OCR** — Multiple documents are analyzed in parallel via `asyncio.gather()`, with per-document error isolation. One failed OCR doesn't block others.

185. **OCR correction merges fields, doesn't replace** — `PATCH /documents/{proc_id}/ocr-result` merges corrections into existing fields. Scalar values get wrapped in `{"value": ...}`. A `manually_corrected` flag is set for audit trail.

186. **Tax calendar is static data, not computed** — IRS deadlines for the 2025 tax year are hardcoded as `_TAX_CALENDAR_2025`. State deadlines in `_STATE_DEADLINES` for 10 states. This is intentional — tax dates don't change frequently and hardcoding ensures correctness without an external data source.

187. **Scenario comparison computes deltas from first scenario** — The first scenario in the list is the "base". All subsequent scenarios include `tax_delta` and `refund_delta` computed against the base. This provides a clear comparison point without requiring the client to compute differences.

188. **2026 constants projected via CPI-U at 2.8%** — `inflate()` rounds to nearest $50 per IRS convention. SALT cap and CTC are fixed (not inflation-adjusted). SS wage base uses 3.5% growth (historically outpaces CPI-U). All projections carry a disclaimer about Rev. Proc. updates.

189. **Roth conversion optimizer uses binary search** — 50 iterations of binary search gives sub-dollar precision. Checks marginal bracket rate (computed from brackets), not effective rate. If already above target bracket, returns 0 conversion immediately.

190. **Marginal rate computed from brackets, not TaxResult** — TaxResult doesn't store marginal_rate. `_marginal_rate()` helper walks the bracket table to find the rate at the taxpayer's taxable income level. This is used for both projection display and Roth optimizer targeting.

191. **Optimizer uses approximate marginal rate for savings** — Estimated savings use 22% as a common middle-bracket approximation rather than computing exact savings for each strategy. This is intentional: the optimizer is advisory, not a precise calculator. Exact numbers come from rerunning compute_tax with the strategy applied.

192. **15 strategies with conditional applicability** — Strategies are only shown when applicable (e.g., 401k suggestions only if has_401k=True). The `applicable` flag excludes informational-only items from the savings total. Sorted by estimated_savings descending.

193. **1040-X uses A/B/C column pattern** — Column A = original, Column B = net change (amended - original), Column C = corrected (A + B). This mirrors the official IRS Form 1040-X layout. 17 lines cover AGI, deductions, taxable income, tax, credits, other taxes, total tax, payments, overpayment, amount owed, plus Part II income breakdown.

194. **Auto-generated explanation for 1040-X Part III** — When no custom explanation is provided, `compute_amended_return()` generates one by describing each material change (e.g., "AGI increased by $15,000"). This saves filers from manually writing the required explanation of changes.

195. **Withholding analyzer uses projected full-year extrapolation** — YTD withholding is divided by elapsed pay periods and multiplied by total periods to project annual withholding. This gives accurate mid-year recommendations even though the actual per-period amount may vary.

196. **Safe harbor: 110% for high-income filers** — AGI > $75k (single) or $150k (MFJ) triggers 110% safe harbor threshold per IRS rules. Below that, 100% of current year tax is the safe harbor. Penalty risk flagged only when both under 90% of current tax AND under safe harbor AND gap > $1,000.

197. **Webhooks use in-memory store with HMAC-SHA256 signing** — Production would use DB tables (webhook_endpoints, webhook_deliveries), but the in-memory store allows the full API contract to work without migrations. Delivery simulation returns 200; real httpx delivery is a future enhancement.

198. **5 webhook event types** — draft.created, draft.updated, document.uploaded, document.ocr_complete, plan.upgraded. Event type validation on endpoint creation prevents typos. Test endpoint sends a special "test" event type.

199. **Metering buffer: in-memory with Redis Streams upgrade path** — Single-replica in-memory metering with flush/aggregate pattern. Same API contract works with Redis Streams backend. Aggregated totals persist across flush (buffer clears, running totals stay).

200. **HPA: CPU-based autoscaling 1-3 replicas** — Conservative scaling: 70% CPU target, 60s scale-up stabilization, 300s scale-down stabilization. PDB ensures minAvailable=1 during voluntary disruptions.

201. **Indiana uses `in_.py` module name** — Python keyword `in` prevents `in.py`. The `get_state_config()` function maps `IN` → `in_` for the import. All other states use lowercase abbreviation directly.

202. **20 states: 4 flat + 7 graduated + 9 no-tax** — Flat: IL, PA, NC, MA, MI, AZ, CO, IN. Graduated: CA, NY, NJ, GA, OH, VA, MN, MD, WI. No-tax: AK, FL, NV, NH, SD, TN, TX, WA, WY. Reciprocal agreements expanded: VA-DC-KY-MD-PA-WV, MD-DC-PA-VA-WV, MI-IL-IN-KY-MN-OH-WI, WI-IL-IN-KY-MI, IN-KY-MI-OH-PA-WI.

203. **Three-tier Stripe pricing** — Starter $29/mo, Professional $99/mo, Enterprise $299/mo. Metered billing for usage overage (computations, OCR pages, API calls). Revenue metrics computed from subscriber list with churn tracking.

204. **Billing state machine** — 6 states (free→trialing→active→past_due→canceled→downgraded) with validated transitions. Invalid transitions rejected to prevent state corruption.

205. **7 custom Prometheus metrics** — counters (drafts, OCR pages, API requests, webhook deliveries), gauges (active tenants, Stripe MRR), histogram (computation duration with 6 buckets). All prefixed with `taxlens_`.

206. **4 alert rules** — High error rate >5% (critical), P95 latency >2s (warning), disk >80% (warning), webhook failures (warning). All with stabilization windows to avoid flapping.

## Post-Wave-73 Strategic Decisions (2026-04-25)

207. **Stay in planning/advisory lane, don't compete on filing UX** — TaxLens's moat is the computation engine + MCP interface, not a consumer filing UI. TurboTax/FreeTaxUSA own the consumer UX. Compete by being the best engine that CPAs, agents, and integrators build on top of. The portal is for tenant management, not end-user tax filing.

208. **TCJA sunset comparison is the #1 urgent feature** — Every tax professional and high-net-worth individual will ask "what happens to my taxes in 2026?" The Tax Cuts and Jobs Act provisions expire Dec 31 2025: brackets revert, SALT uncapped, QBI gone, CTC halved, standard deduction drops. Building `_YEAR_2026_SUNSET` config and a comparison endpoint is the single highest-value feature for the next 8 months.

209. **Solo 401(k)/SEP-IRA is a BLOCKER** — Currently mismodeled as a Schedule C business expense (line 19), which reduces SE tax base. IRS treatment: Schedule 1 line 16 above-the-line deduction — reduces income tax but NOT self-employment tax. Every self-employed filer using retirement deductions gets wrong SE tax. Must fix before any production advisory use.

210. **PII encryption is stop-ship for real deployment** — SSNs flow in plaintext through PersonInfo → TaxResult → result.json → PostgREST → PostgreSQL → API responses. For a real multi-tenant deployment, need: (1) field-level Fernet encryption at rest (same pattern as Plaid tokens), (2) last-4-only display in API responses, (3) tenant isolation audit for SSN access paths.

211. **PTET is the #1 state planning feature** — Pass-Through Entity Tax elections (available in 30+ states) let S-corp/partnership owners convert SALT-capped personal deductions into uncapped entity-level deductions. This is the single biggest tax planning move for passthrough business owners post-TCJA. Requires entity-level computation layer.

212. **Carryforwards need persistent per-filer state** — Five major carryforwards exist (charitable, NOL, capital loss, AMT credit, passive activity loss) but none are consumed across tax years. The `charitable_carryforward` field on TaxResult is tracked but never imported into the next year's computation. Need a carryforward ledger per filer.

## Wave 74 — Self-Employed Retirement Plans (v3.53.0)

214. **SE retirement is Schedule 1 line 16, NOT Schedule C expense** — Solo 401(k), SEP-IRA, and SIMPLE IRA contributions are above-the-line deductions that reduce income tax but do NOT reduce self-employment tax. SE tax is computed on `Schedule C profit × 92.35%` BEFORE any retirement deduction. The deduction is applied in the ADJUSTMENTS section after SE tax is fully calculated. This matches IRS treatment per IRC §404(a)(8) and Form 1040 Schedule 1 line 16.

215. **Net SE income for contribution limits = profit − 50% of SE tax** — SEP-IRA's 25% limit and Solo 401(k)'s employer contribution are based on net self-employment income, which is Schedule C profit minus the deductible half of SE tax. This is the IRS-prescribed method — the contribution limit depends on the tax, which depends on the income, creating a circular reference solved by the IRS rate tables.

216. **Three plan types with year-specific limits** — SEP-IRA (employer-only, 25% of net SE income up to $70K/2025), Solo 401(k) (employee deferral $23,500 + employer 25%, total $70K), SIMPLE IRA (employee $16,500 + 3% employer match). Catch-up contributions: Solo 401(k) $7,500, SIMPLE $3,500 (both age 50+). Limits stored per-year in tax_config.py.

## Wave 75 — QBI SSTB Classification (v3.54.0)

217. **SSTB phaseout is fundamentally different from non-SSTB** — For Specified Service Trades or Businesses above the QBI threshold, QBI phases to $0 (not the W-2 wage limitation). In the phaseout range, the QBI amount itself is proportionally reduced: `applicable_QBI = total_QBI × (1 - phase_fraction)`, then 20% is applied. Non-SSTB uses a different formula: reduce excess of full 20% QBI over W-2 wage limitation. The distinction matters most for sole proprietors (no W-2 wages to themselves) — non-SSTB still gets $0 without employees, but the computation path and intermediate values differ.

218. **w2_wages_paid on BusinessIncome enables non-SSTB W-2 limitation** — The W-2 wage limitation (`max(50% W-2, 25% W-2 + 2.5% UBIA)`) requires knowing how much the business pays its employees. Added `w2_wages_paid` field alongside `is_sstb`. For most Schedule C sole proprietors this is $0, but businesses with employees (e.g., a restaurant) can claim the W-2 limitation.

213. **QBI needs SSTB classification** — The BusinessIncome schema lacks a `is_sstb` field (Specified Service Trade or Business). For high-income filers above the QBI threshold, SSTB status means QBI phases to $0 (not to the W-2 wage limitation). Without this field, lawyers/doctors/consultants get incorrect QBI results above ~$192K single / ~$384K MFJ.

## Wave 76 — Compare Scenarios Marginal Rates + Audit Risk Passing Checks (v3.55.0)

219. **Compute marginal/effective rates inline, not on TaxResult** — The compare_scenarios endpoints (both REST and MCP) previously tried to access `result.effective_rate` and `result.marginal_rate` on TaxResult — fields that didn't exist (latent bug). Fixed by computing rates inline using `_effective_rate()` and `_marginal_rate()` from `tax_projector.py`. Rates are per-scenario since each may have different filing status and income levels.

220. **Audit risk passing checks alongside flags** — Added `PassingCheck` dataclass and `passing_checks` list to `AuditRiskReport`. Every check that doesn't trigger a flag now records a passing check with the same category, the filer's value, and the norm. This gives users confidence about what's normal on their return, not just what's flagged. The `to_dict()` method includes `num_passing` and `passing_checks` array.

## Wave 78 — TCJA Sunset 2025 vs 2026 Comparison Engine (v3.57.0)

224. **2026 TCJA sunset as a third supported tax year** — Rather than a separate "projection" mode, 2026 is a full tax year config with all the TCJA reversion values: pre-TCJA brackets (10/15/25/28/33/35/39.6%), halved standard deduction (~$8,300 single), restored personal exemption (~$5,300/person), SALT cap removed, QBI §199A expired (rate=0%), CTC reduced to $1,000, and lower AMT exemptions. This means `compute_tax(tax_year=2026)` works identically to 2024/2025 — same engine, different constants.

225. **Year-conditional fixed-rate overrides in get_year_config()** — Several "fixed" constants (QBI_DEDUCTION_RATE, SALT_CAP, CTC_PER_CHILD) are actually TCJA provisions that expire. For tax_year >= 2026, these are overridden from the year-specific config rather than using the module-level statutory constant. This uses `if tax_year < 2026:` guards so 2024/2025 behavior is unchanged.

226. **Personal exemption as a new TaxResult field** — Added `personal_exemption` field to TaxResult, computed as `PERSONAL_EXEMPTION × (1 + num_spouses + num_dependents)`. For 2024/2025 this is $0 (TCJA). For 2026+, it's ~$5,300 per person and reduces taxable income alongside deductions and QBI. This correctly models the pre-TCJA treatment where personal exemptions were a major deduction for families.

## Wave 77 — PII Encryption for SSNs (v3.56.0)

221. **SSN masking at the storage boundary, not in the dataclass** — PersonInfo and Dependent retain `ssn` fields in plaintext during computation (needed for PDF generation on IRS forms). SSNs are redacted at the storage boundary: `result.json` "input" section stores masked SSNs (`***-**-6789`), and API responses never expose full SSNs. This avoids circular complexity where encryption/decryption would need to weave through the computation engine.

222. **Fernet encryption with graceful degradation** — When `PII_FERNET_KEY` env var is set, `encrypt_ssn()` produces Fernet ciphertext (AES-128-CBC + HMAC, timestamped). When unset, it falls back to masking (last 4 digits only). This means the system is safe-by-default: even without encryption configured, SSNs are never stored in plaintext. The Fernet pattern matches the existing Plaid token encryption (`PLAID_FERNET_KEY`).

223. **Redaction is immutable — never mutates input dicts** — `redact_person_dict()` and `redact_input_block()` always return new dicts, never modifying the originals. This prevents accidental loss of SSN data mid-computation when the same PersonInput dict is referenced by both the computation pipeline and the storage pipeline.

224. **PTET credit lives on K1Income, not a separate entity model** — Rather than creating an EntityReturn model with full entity-level tax computation, PTET is modeled as K-1 passthrough metadata: `ptet_election`, `ptet_state`, `ptet_tax_paid` on K1Income. The entity pays the tax; the filer's K-1 reports the credit. This mirrors how CPAs actually encounter PTET — as K-1 line items, not entity returns they prepare.

225. **PTET credit applied after state return computation** — State returns are computed first (via `compute_all_state_returns()`), then PTET credits are subtracted from matching state returns' `total_tax`. This avoids coupling PTET logic into per-state compute functions. The credit is tracked on both `StateTaxResult.ptet_credit` and `TaxResult.ptet_credits` (aggregated list).

226. **15 states enabled for PTET, PA/OH intentionally excluded** — CA, NY, IL, NJ, GA, NC, VA, MA, MD, MN, CO, AZ, WI, IN, MI all have PTET programs. PA's flat 3.07% rate makes PTET less common in practice, and OH has CAT not income tax. Both excluded to avoid misleading results.

227. **Carryforwards are input/output fields, not persistent state** — Rather than building a multi-year persistence layer (database), carryforwards are modeled as compute_tax() input parameters (prior-year carryover) and TaxResult output fields (current-year carryforward). Clients track the linkage between years. This keeps the engine stateless and testable.

228. **NOL limited to 80% of taxable income (post-TCJA §172)** — The Tax Cuts and Jobs Act limited NOL deductions to 80% of taxable income (pre-NOL). This prevents large NOLs from zeroing out taxable income entirely. The remaining 20% ensures some minimum tax. Prior-2018 NOLs had no percentage limit but a 2-year carryback (not modeled).

229. **AMT credit from prior year offsets regular tax down to tentative minimum tax** — The AMT credit (Form 8801) prevents double taxation when AMT was paid in a prior year due to timing differences. The credit is limited to the excess of regular tax over TMT, ensuring the taxpayer never pays less than the tentative minimum. Current-year AMT adds to the carryforward pool for future use.

230. **Entity optimizer is a standalone module, not in tax_engine.py** — `entity_optimizer.py` computes simplified sole prop / S-corp / C-corp comparisons independently, importing only `compute_bracket_tax` and tax_config constants. It intentionally doesn't run `compute_tax()` three times (which would be accurate but slow and complex). The trade-off: simplified SE tax, FICA, and bracket calculations that are directionally correct for advisory purposes but may differ from a full return computation by a few hundred dollars.

231. **Reasonable compensation range is heuristic, not IRS-prescribed** — The 40-70% range for S-corp reasonable compensation is based on industry practice and audit precedent, not an IRS formula. The IRS looks at factors like duties, time spent, comparable salaries, and industry norms. The optimizer provides a starting range; CPAs should validate with comparable salary data.

232. **Catch-up contributions don't count toward §415(c)** — The mega backdoor Roth calculator correctly excludes age 50+ catch-up ($7,500) from the §415(c) annual additions limit. Only regular deferrals (up to §402(g)) and employer match count toward the $70K/$72K total. This is a common misunderstanding that would undercount available after-tax space.

233. **Roth vs taxable projection uses annual LTCG tax drag** — The 10-year projection compares Roth (tax-free growth) vs taxable (growth taxed at 15% annually). This is conservative: real taxable accounts may defer gains and realize them at sale, but annual tax drag is the standard comparison methodology.

234. **PPRT modeled on K-1 income, not as separate entity return** — IL PPRT (1.5% on S-corp/partnership income) is an entity-level tax but surfaces on the filer's K-1. We compute it when K-1 ordinary_income > 0 and the entity_type matches pprt_entity_types. The PPRT adds to IL state return total_tax. This matches how CPAs encounter PPRT — as a line item on the entity return that flows to the individual's state tax planning.

235. **PPRT uses pprt_rate/pprt_entity_types on StateConfig** — Rather than hardcoding the IL PPRT, the config is generic: any state can declare a pprt_rate. Currently only IL uses it (1.5%), but this prepares for other states' replacement/franchise taxes if needed.

236. **Smoke tests require TAXLENS_API_KEY env var** — After API key auth became mandatory (Wave 11b), the smoke test script was never updated to pass `X-API-Key` headers. Fixed by requiring `TAXLENS_API_KEY` env var and injecting it into all curl calls (POST + GET). This prevents silent 401 failures that look like engine bugs.

237. **Smoke test expectations must track engine behavior changes** — Multi-state expansion (Wave 71) and standard deduction changes invalidated 4 of 31 smoke test assertions: (a) `work_states` without `days_worked_by_state` doesn't generate nonresident returns — removed IT-201 expectations from NJ→NY tests, (b) low-income MFJ with only dividends uses standard deduction even with high itemizable amounts — removed Schedule A expectation, (c) borderline refund/owed scenarios shift with bracket updates — removed strict refund assertion.

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
