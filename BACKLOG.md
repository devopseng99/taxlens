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

## Next Work Items

### 1. NIIT + Additional Medicare Tax
Add 3.8% NIIT on investment income and 0.9% Additional Medicare Tax for high earners. Constants exist in tax_config.py. Affects TC08, TC10, TC12 (high-income scenarios).

```bash
# After implementing in tax_engine.py:
bash tests/smoke_test_tax_drafts.sh  # verify all 20 still pass (amounts will change for high earners)
```

### 2. Schedule C Expense Line-Item PDF Filling
Fill individual expense line fields in the Schedule C fillable template instead of summary-only.

```bash
# Verify field names:
python3 -c "import pypdf; r=pypdf.PdfReader('app/templates/f1040sc.pdf'); print([f.get('/T') for f in r.get_fields().values()][:30])"
```

### 3. W-2 OCR Fixture Tests
Create stored OCR JSON fixtures to test the full W-2 → compute → PDF pipeline without Azure.

```bash
# Extract fixture from existing OCR result:
kubectl exec -n taxlens deploy/taxlens-api -- cat /data/documents/hr1/<proc_id>/ocr_result.json > tests/fixtures/w2_sample.json
```

### 4. Authentication Layer
Add JWT auth with user management. Currently username is self-reported.

### 5. Wave 6 — Agentic Intelligence
Chat interface, tax optimization, multi-doc correlation. See NEXT-STEPS.md.
