# TaxLens — Next Steps

Updated: 2026-04-17

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

## Ready to Build

### NIIT (Net Investment Income Tax)
- 3.8% surtax on investment income for high earners (>$200k single, >$250k MFJ)
- Constants already in tax_config.py, just needs computation in engine

### Additional Medicare Tax
- 0.9% on earnings above threshold ($200k single, $250k MFJ)
- Constants already in tax_config.py

### Schedule C Expense Detail in PDFs
- Currently shows summary (gross receipts, COGS, total expenses, net profit)
- Could fill per-line expense fields matching IRS Schedule C fillable form

### W-2 Integration in Smoke Tests
- Create stored OCR fixture files to test W-2 → computation pipeline
- Would validate the full upload → OCR → compute → PDF flow in tests

### AMT (Alternative Minimum Tax)
- Would need AMT exemption amounts, phase-out, and preference items
- Complex but relevant for high-income business owners

### Authentication
- Currently username is self-reported
- Implement JWT or session-based auth for multi-user security

## Wave 6 — Agentic Intelligence (Deferred)
- Chat interface for tax Q&A
- Tax optimization suggestions (e.g., "itemize vs standard", "estimated payment recommendations")
- Multi-document correlation (auto-match W-2s to employers)
- Year-over-year comparison
