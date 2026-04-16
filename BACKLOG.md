# TaxLens + OpenFile Integration Backlog

Updated: 2026-04-16 02:45 CDT

## Azure Budget Tracker
- **Tier:** F0 Free (500 pages/month)
- **Used:** 4 pages (2x W-2, 2x 1099-INT)
- **Remaining:** 496 pages
- **Rule:** Do not exceed 20 pages in testing this session

---

## Wave 5 — Tax Form Generator [COMPLETED]
- [x] Created tax_config.py — 2025 federal brackets (Single/MFJ/HoH/MFS), IL flat tax, SALT cap, CTC, LTCG rates
- [x] Created tax_engine.py — Full computation: income, AGI, standard vs itemized, brackets, capital gains, CTC, IL-1040
- [x] Created pdf_generator.py — ReportLab PDFs: Summary, Form 1040, Schedule A/B/D, IL-1040
- [x] Created tax_routes.py — 5 API endpoints: create draft, get summary, download PDF, list PDFs, list drafts
- [x] Wired into main.py, added reportlab==4.1.0
- [x] Built, deployed, and tested (Helm revision 5)
- [x] Validated 3 filing scenarios:
  - Single: $44,640 income, standard deduction, $3,708 net refund
  - MFJ: $57,540 income (w/ investments), standard beats itemized, $7,525 net refund
  - HoH: $47,940 income, itemized ($32k > $22.5k std), CTC zeroes tax, $8,345 net refund
- [x] 20 PDF files stored on PVC across 3 drafts
- [x] All PDFs downloadable via HTTPS at dropit.istayintek.com

## Wave 5b — Business Income Support [COMPLETED]
- [x] Added SE tax constants (15.3% rate, 92.35% factor) and QBI deduction (20%) to tax_config.py
- [x] Added BusinessIncome dataclass with Schedule C computation (gross receipts, COGS, 12 expense categories, home office)
- [x] Added Schedule SE computation (SS capped at wage base minus W-2 SS wages, Medicare uncapped)
- [x] Added QBI deduction (Section 199A, 20% of business income, simplified phase-out)
- [x] Wired BusinessIncomeInput in tax_routes.py to convert and pass to compute_tax()
- [x] Added Schedule C PDF generator (per-business detail + total)
- [x] Added Schedule SE PDF generator
- [x] Updated Form 1040 PDF with business income line (8a), SE tax, QBI deduction (13)
- [x] Updated Summary PDF with business income, SE tax, QBI sections
- [x] Added schedule_c and schedule_se to PDF download endpoint file_map
- [x] Built, deployed, and verified (Helm revision)
- [x] Created comprehensive smoke test suite: 15 test cases all passing
  - TC01-03: Single/MFJ/HoH basic (no business)
  - TC04: Freelance developer ($125k gross, $110k net, $15.5k SE tax)
  - TC05: Rideshare driver + W-2 MFJ ($38k gross, $21.3k net)
  - TC06: Restaurant owner ($280k gross, $98.4k net, $13.9k SE tax)
  - TC07: Multiple businesses (marketing + photography)
  - TC08: MFS high earner (investments only)
  - TC09: HoH freelance writer + 3 dependents + CTC
  - TC10: MFJ dual-business couple + investments ($227k income)
  - TC11: Minimum wage / low income
  - TC12: High-income consultant ($350k, owes $48k)
  - TC13a-c: Original 3 scenarios revalidated

## Wave 6 — Agentic Intelligence [DEFERRED]
- Future: chat interface, tax optimization, multi-doc correlation

---

## Completed

### Wave 1 — Deploy OpenFile 26f25 ✓
- [x] Built + deployed localhost/openfile-api:26f25 + localhost/openfile-client:26f25
- [x] 5 pods running, factgraph ENABLED, 21 tax returns for 2025

### Wave 2 — Bridge TaxLens → OpenFile auto-fill ✓
- [x] bridge.py with W-2 field mapping, NetworkPolicy, correct PG password
- [x] Verified: W-2 OCR → populated_data → tax return a9b6e1a6

### Wave 3 — Full E2E validation ✓
- [x] 6/6 endpoints 200, full pipeline verified

### Wave 4 — Multi-form OCR test (1099-INT) ✓
- [x] Azure auto-detected 1099-INT, extracted Payer/Recipient/Box 1

### Wave 5 — Tax Form Generator ✓
- [x] Full tax computation engine: Federal 1040 + IL-1040
- [x] PDF generation: 1040, Schedule A/B/D, IL-1040, Summary
- [x] 3 filing scenarios validated: Single, MFJ, HoH
- [x] Supports: W-2, 1099-INT, dividends, capital gains (stock/crypto), mortgage, SALT, charitable, CTC
