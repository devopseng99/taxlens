# TaxLens — Key Technical Decisions

Updated: 2026-04-16

## Architecture

1. **Separate tax engine from routes** — `tax_config.py` (constants), `tax_engine.py` (computation), `pdf_generator.py` (PDF output), `tax_routes.py` (API). Clean separation allows unit testing engine without HTTP.

2. **ReportLab Canvas (not templates)** — Direct PDF generation via `reportlab.pdfgen.canvas` gives full control over IRS form layout without needing fillable PDF templates. Trade-off: more code but zero external template dependencies.

3. **Standard vs Itemized auto-choice** — Engine always computes both and picks the higher deduction automatically. Schedule A PDF always generated for reference.

4. **LTCG/QD preferential rate stacking** — Qualified dividends + net long-term gains taxed at 0/15/20% rates, stacked on top of ordinary income in the bracket. Short-term gains taxed as ordinary income.

5. **Self-employment tax (Schedule SE)** — 15.3% on 92.35% of net SE income. SS portion capped at wage base minus W-2 SS wages. 50% deductible above-the-line. This matches IRS calculation method.

6. **QBI deduction (Section 199A)** — Simplified: 20% of qualified business income, capped at taxable income. Full phase-out rules for high earners not implemented (would need SSTB classification, W-2/UBIA limits).

7. **Draft storage on PVC** — Each draft gets a unique directory under `{STORAGE_ROOT}/{username}/drafts/{draft_id}/`. PDFs + result.json stored together. Private per-user via path isolation.

8. **OCR-first, manual-supplement** — W-2 and 1099-INT data extracted from Azure OCR results. All other income/deduction types entered manually via API. This allows hybrid automated+manual filing.

## Testing

9. **Repeatable smoke test suite** — `tests/smoke_test_tax_drafts.sh` with 15 scenarios covering all 4 filing statuses, business income, investments, deductions, CTC. Re-runnable for regression after any engine changes.

10. **No W-2 in smoke tests** — Test cases don't use OCR W-2 documents (would require stored OCR files). Instead they test the computation engine directly with manual income inputs. OCR path tested separately via upload+analyze flow.
