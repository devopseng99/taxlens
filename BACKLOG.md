# TaxLens + OpenFile Integration Backlog

Updated: 2026-04-17

## Azure Budget Tracker
- **Tier:** F0 Free (500 pages/month)
- **Used:** 4 pages (2x W-2, 2x 1099-INT)
- **Remaining:** 496 pages
- **Rule:** Do not exceed 20 pages in testing this session

---

## Wave 5c — Official IRS PDF Templates [COMPLETED]
- [x] Replaced ReportLab canvas PDFs with pypdf fillable IRS templates
- [x] Added pypdf==4.3.1 to requirements.txt
- [x] Rewrote pdf_generator.py — `_fill_pdf()` using `PdfWriter(clone_from=reader)` + `update_page_form_field_values()`
- [x] Sourced 8 official IRS/IL fillable PDF templates (6 byte-match IRS 26f25, 2 match OpenFile production)
- [x] Fixed AcroForm dictionary loss bug (clone_from vs append_pages_from_reader)
- [x] Swapped Schedule B from accessible variant to official (identical field names)
- [x] Deleted f1040sb_accessible.pdf (obsolete)
- [x] Expanded smoke test suite: 12 original + 5 new custom cases + 3 revalidation = 20 total
- [x] New test cases: nurse+tutor MFJ, retired couple, gig worker multi-platform, real estate agent HoH, MFS crypto trader
- [x] Created 5 custom filing drafts for hr1 user matching new test cases
- [x] All 20 smoke tests passing
- [x] Validated all PDFs: proper sizes (100KB-1MB for IRS forms), correct content-type/disposition
- [x] Playwright E2E: UI tabs, PDF headers, inline viewing verification
- [x] Frontend redesign: tabbed interface, smoketest panel, draft management
- [x] Built, deployed, verified (podman build → ctr import → helm upgrade)

## Completed (Prior)

### Wave 5b — Business Income Support ✓
- [x] Schedule C, SE tax, QBI deduction, 15-scenario smoke test

### Wave 5 — Tax Form Generator ✓
- [x] Full tax computation engine: Federal 1040 + IL-1040, PDF generation

### Wave 4 — Multi-form OCR test (1099-INT) ✓
- [x] Azure auto-detected 1099-INT, extracted Payer/Recipient/Box 1

### Wave 3 — Full E2E validation ✓
- [x] 6/6 endpoints 200, full pipeline verified

### Wave 2 — Bridge TaxLens → OpenFile auto-fill ✓
- [x] W-2 OCR → populated_data → tax return

### Wave 1 — Deploy OpenFile 26f25 ✓
- [x] Built + deployed, factgraph ENABLED, 21 tax returns for 2025

---

## Wave 6a — Surtaxes + Tests + Auth [COMPLETED]
- [x] NIIT (3.8% on net investment income for AGI > threshold)
- [x] Additional Medicare Tax (0.9% on earnings above threshold)
- [x] Schedule C home office line, Schedule D proceeds/cost basis columns
- [x] 43 pytest unit tests (brackets, LTCG, SE, NIIT, Medicare, CTC, IL, OCR, E2E)
- [x] 9 auth unit tests
- [x] 4 OCR fixture tests (W-2 parse, high earner surtaxes, 1099-INT, combined pipeline)
- [x] API key auth layer (X-API-Key header, TAXLENS_API_KEYS env var)
- [x] All 20 smoke tests passing with surtax changes
- [x] 5 hr1 custom drafts recreated
- [x] Built, deployed, verified (v0.6.0)

## Wave 6b — Schedule 2 / Form 8959 / Form 8960 [COMPLETED]
- [x] Downloaded official IRS fillable PDFs for Schedule 2, Form 8959, Form 8960
- [x] Inspected field names via labeled PDF generation (no tooltips on IRS PDFs)
- [x] Implemented `generate_schedule_2()` — Lines 4 (SE), 11 (Add'l Medicare), 12 (NIIT), 21 (total)
- [x] Implemented `generate_form_8959()` — Parts I-V (wages, SE, RRTA, total, withholding reconciliation)
- [x] Implemented `generate_form_8960()` — Parts I-III (investment income, expenses, NIIT computation)
- [x] Conditional generation: Schedule 2 when any surtax; 8959 only when Add'l Medicare; 8960 only when NIIT
- [x] Updated `forms_generated` in tax_engine.py and `file_map` in tax_routes.py
- [x] 6 new unit tests (58 total passing)
- [x] TC12 smoke test confirms: Schedule 2 + Form 8959 + Form 8960 generated for high-income filer
- [x] Built, deployed, verified (v0.7.0)

## Wave 7 — Multi-State Support [COMPLETED]
- [x] `app/state_configs/` — pluggable state config modules (one file per state)
- [x] `app/state_tax_engine.py` — generic dispatcher (flat, graduated, none)
- [x] 10 states: IL, CA, NY, NJ, PA, NC, GA, OH, TX, FL
- [x] Multi-state worker orchestration (nonresident + resident with credits)
- [x] Reciprocal agreement handling (IL↔WI/IA/KY/MI, NJ↔PA, PA↔OH/IN/MD/VA/WV)
- [x] StateWageInfo dataclass + W-2 OCR StateTaxInfos parsing
- [x] Days-worked allocation fallback
- [x] Generic ReportLab state PDF summary for non-IL states
- [x] IL backward compat (il_* fields, illinois_* JSON keys)
- [x] 42 new state tax unit tests (100 total passing)
- [x] 5 new smoke tests (TC21-TC25: CA, TX, PA, NJ→NY, IL→WI)
- [x] Built, deployed, verified (v0.8.0)

## Wave 9 — Extended OCR Parsers [COMPLETED]
- [x] DividendIncome dataclass + `parse_1099div_from_ocr()` (Box1a/1b/2a/4/5, flat + array formats)
- [x] `parse_1099nec_from_ocr()` → BusinessIncome + withholding (Schedule C + SE)
- [x] `parse_1098_from_ocr()` → mortgage interest (Schedule A)
- [x] `parse_1099b_from_structured()` → list[CapitalTransaction] (JSON import for brokerage)
- [x] TaxDraftRequest extended: div_1099_proc_ids, nec_1099_proc_ids, mortgage_1098_proc_ids, brokerage_transactions
- [x] additional_withholding param for 1099 Box 4 amounts
- [x] Auto-detect form type in Azure OCR flow (doc_type → form_type in ocr_result.json)
- [x] 5 test fixtures (1099-DIV flat/array, 1099-NEC, 1098, 1099-B)
- [x] 26 new unit tests (126 total passing)
- [x] 4 new smoke tests (TC26-TC29: dividends+brokerage, freelancer, homeowner, combined pipeline)
- [x] Built, deployed, verified (v0.8.5)

## Wave 8 — Agentic Intelligence (MCP Server) [COMPLETED]
- [x] MCP server (`app/mcp_server.py`) with 7 tools: compute_tax_scenario, compare_scenarios, estimate_impact, optimize_deductions, get_draft, list_user_drafts, list_states
- [x] 2 MCP resources: taxlens://states, taxlens://drafts/{username}
- [x] StreamableHTTP at `/api/mcp` via FastAPI ASGI mount (not Starlette sub-app)
- [x] DNS rebinding protection with TransportSecuritySettings (allowed_hosts)
- [x] stateless_http=True (no server-side session state)
- [x] FastAPI lifespan manages MCP session_manager.run()
- [x] 19 unit tests for MCP tool handlers (145 total passing)
- [x] Live verified: initialize, tools/list, compute_tax_scenario all working
- [x] Built, deployed, verified (v0.9.0)

## Next Work Items

### 1. Wave 10 — Plaid Financial Institution Integration
Auto-import W-2s, 1099s, investment transactions from banks/brokerages.

**Key deliverables:**
- Plaid Link flow (create-link-token → exchange → sync)
- Investment transactions → CapitalTransaction, dividends → DividendIncome
- Auto-download + OCR tax document PDFs from connected institutions

### 2. Enable Auth in Production
Generate API keys, set TAXLENS_API_KEYS in K8s secret, update frontend to send header.

```bash
# Generate a key:
python3 -c "from auth import generate_api_key; print(generate_api_key())"
# Set in K8s:
kubectl create secret generic taxlens-api-keys -n taxlens --from-literal=keys="tlk_xxx,tlk_yyy"
```
