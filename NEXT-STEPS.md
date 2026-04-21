# TaxLens — Next Steps

Updated: 2026-04-20 (v0.7.0)

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
- [x] 6 new unit tests for Schedule 2 form generation logic
- [x] 58 total unit tests passing (49 engine + 9 auth)

## Ready to Build

### AMT (Alternative Minimum Tax)
- Would need AMT exemption amounts, phase-out, and preference items
- Complex but relevant for high-income business owners

### Enable Auth in Production
- Generate API keys, set TAXLENS_API_KEYS env var
- Update frontend to send X-API-Key header

### Wave 7 — Multi-State Support (Modular)
- Pluggable state config modules (`state_configs/{state}.py`)
- Generic `compute_state_tax()` dispatcher (flat + graduated models)
- Wave 1 states: IL (existing), CA, NY, TX, FL, PA, NC, GA, NJ, OH (~60% US pop)
- Generic ReportLab state summary PDF for states without official fillable templates
- Backward compat: `il_*` fields remain as aliases into `state_results["IL"]`

### Wave 8 — Agentic Intelligence (MCP Server)
- **NOT a custom chat UI** — expose tax engine as MCP server
- MCP tools: `compute_tax`, `compare_scenarios`, `estimate_impact`, `list_documents`, `get_draft`, `optimize_deductions`
- Any MCP client (Claude Desktop, Claude Code, custom agents) gets native tax tools
- REST API remains for direct integration; MCP adds agentic layer for free
- Tax optimization: scenario comparison (filing status, itemized vs standard, estimated payments)
- Multi-document correlation: auto-match W-2s to employers via MCP resources

### Enable Auth in Production
- Generate API keys, set TAXLENS_API_KEYS env var
- Update frontend to send X-API-Key header

### AMT (Alternative Minimum Tax)
- Would need AMT exemption amounts, phase-out, and preference items
- Complex but relevant for high-income business owners
