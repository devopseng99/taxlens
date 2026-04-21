# TaxLens — Next Steps

Updated: 2026-04-21 (v0.9.0)

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

## Ready to Build

### Wave 10 — Plaid Financial Institution Integration
Auto-import W-2s, 1099s, investment transactions from banks/brokerages via Plaid Link.

**Flow:** Create link token → user authenticates → exchange token → sync investments + statements → auto-OCR downloaded PDFs → merge into tax computation

### Enable Auth in Production
Generate API keys, set TAXLENS_API_KEYS env var, update frontend.

### AMT (Alternative Minimum Tax)
AMT exemption amounts, phase-out, preference items. Complex but relevant for high-income business owners.
