# TaxLens — Key Technical Decisions

Updated: 2026-04-17

## Architecture

1. **Separate tax engine from routes** — `tax_config.py` (constants), `tax_engine.py` (computation), `pdf_generator.py` (PDF output), `tax_routes.py` (API). Clean separation allows unit testing engine without HTTP.

2. **pypdf fillable templates (not ReportLab canvas)** — Uses `pypdf` to fill official IRS fillable PDF forms via `PdfWriter(clone_from=reader)` + `update_page_form_field_values()`. Templates stored in `app/templates/`. Replaced the original ReportLab canvas approach which generated custom-drawn PDFs. Official IRS forms are legally compliant and visually identical to paper filings. Summary page still uses ReportLab (custom report, no IRS equivalent).

3. **`clone_from=reader` required for AcroForm** — `PdfWriter()` + `append_pages_from_reader()` drops the AcroForm dictionary, making `update_page_form_field_values()` fail. Must use `PdfWriter(clone_from=reader)` to preserve form fields.

4. **OpenFile-matched f1040 template** — The 26f25 tax-refs `f1040.pdf` (229 fields) has different field names than OpenFile's embedded version (155 fields). We use the OpenFile-matched version whose field names align with the YAML configuration at `pdf/2025/IRS1040/en/configuration.yml`. Same SHA as OpenFile production binary.

5. **Standard vs Itemized auto-choice** — Engine always computes both and picks the higher deduction automatically. Schedule A PDF always generated for reference.

6. **LTCG/QD preferential rate stacking** — Qualified dividends + net long-term gains taxed at 0/15/20% rates, stacked on top of ordinary income in the bracket. Short-term gains taxed as ordinary income.

7. **Self-employment tax (Schedule SE)** — 15.3% on 92.35% of net SE income. SS portion capped at wage base minus W-2 SS wages. 50% deductible above-the-line. This matches IRS calculation method.

8. **QBI deduction (Section 199A)** — Simplified: 20% of qualified business income, capped at taxable income. Full phase-out rules for high earners not implemented (would need SSTB classification, W-2/UBIA limits).

9. **Draft storage on PVC** — Each draft gets a unique directory under `{STORAGE_ROOT}/{username}/drafts/{draft_id}/`. PDFs + result.json stored together. Private per-user via path isolation.

10. **OCR-first, manual-supplement** — W-2 and 1099-INT data extracted from Azure OCR results. All other income/deduction types entered manually via API. This allows hybrid automated+manual filing.

## Testing

11. **20-scenario smoke test suite** — `tests/smoke_test_tax_drafts.sh` with 20 scenarios covering all 4 filing statuses, business income, investments, deductions, CTC, crypto, multi-business, retired couples. Re-runnable for regression after any engine changes.

12. **No W-2 in smoke tests** — Test cases don't use OCR W-2 documents (would require stored OCR files). Instead they test the computation engine directly with manual income inputs. OCR path tested separately via upload+analyze flow.

13. **Playwright E2E for UI + PDF validation** — Headless Chromium via central Playwright server (WebSocket). Tests tab navigation, draft listing, PDF download headers. Note: headless Chromium triggers download for PDFs instead of inline render — not a bug, Content-Disposition is correct. Programmatic header verification used instead.

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
| il1040.pdf | IRS 26f25 | 30651b... | Official byte-match |
