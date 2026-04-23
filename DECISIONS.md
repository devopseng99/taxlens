# TaxLens — Key Technical Decisions

Updated: 2026-04-22 (v3.1.2)

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
