# TaxLens — Next Steps

Updated: 2026-04-17 (v0.8.0)

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

## Ready to Build

### Wave 9 — Extended OCR Parsers (Next)
Parse all common tax document types so users can upload any form and auto-fill computation.

**New parsers:**
- `parse_1099div_from_ocr()` — Azure `prebuilt-tax.us.1099DIV` → DividendIncome dataclass
  - Box 1a (ordinary dividends), 1b (qualified), 2a (cap gain dist), 4 (withheld), 5 (199A)
- `parse_1099nec_from_ocr()` — Azure `prebuilt-tax.us.1099NEC` → BusinessIncome
  - Box 1 (NEC → gross_receipts), Payer.Name → business_name, Box 4 (withheld)
- `parse_1098_from_ocr()` — generic `prebuilt-document` → float (mortgage interest)
  - Box 1 simple extraction
- `parse_1099b_from_structured()` — JSON/CSV import → list[CapitalTransaction]
  - NOT OCR — brokerage tables too complex for OCR. Structured import from Plaid or manual

**Tasks:** 9 new parsers/handlers, 15+ unit tests, 4 OCR fixture tests, TaxDraftRequest extensions

### Wave 8 — Agentic Intelligence (MCP Server)
Expose tax engine as MCP server via StreamableHTTP at `/mcp`.

**Tools:** compute_tax, compare_scenarios, estimate_impact, optimize_deductions, list_documents, get_draft, upload_document
**Resources:** taxlens://drafts/{username}, taxlens://states, taxlens://documents/{username}

### Wave 10 — Plaid Financial Institution Integration
Auto-import W-2s, 1099s, investment transactions from banks/brokerages via Plaid Link.

**Flow:** Create link token → user authenticates → exchange token → sync investments + statements → auto-OCR downloaded PDFs → merge into tax computation

### Enable Auth in Production
Generate API keys, set TAXLENS_API_KEYS env var, update frontend.

### AMT (Alternative Minimum Tax)
AMT exemption amounts, phase-out, preference items. Complex but relevant for high-income business owners.
