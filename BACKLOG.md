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
