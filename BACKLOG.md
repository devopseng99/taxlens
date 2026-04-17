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

## Next Work Items

### 1. Wave 6 — Agentic Intelligence
Chat interface, tax optimization, multi-doc correlation. See NEXT-STEPS.md.

### 2. Enable Auth in Production
Generate API keys, set TAXLENS_API_KEYS in K8s secret, update frontend to send header.

```bash
# Generate a key:
python3 -c "from auth import generate_api_key; print(generate_api_key())"
# Set in K8s:
kubectl create secret generic taxlens-api-keys -n taxlens --from-literal=keys="tlk_xxx,tlk_yyy"
```

### 3. Schedule 2 PDF (Form 8959/8960)
Formal Schedule 2 for NIIT and Additional Medicare Tax. Currently embedded in 1040 line 23.

### 4. Multi-State Support
Currently Illinois-only. Add configurable state tax computation.
