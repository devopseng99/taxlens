# TaxLens — Key Technical Decisions

Updated: 2026-04-21 (v0.8.5)

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

14. **Schedule 2 + Form 8959 + Form 8960 conditional generation** — These forms are only generated when their respective taxes are triggered: Schedule 2 when SE tax, NIIT, or Additional Medicare Tax > 0; Form 8959 only when Additional Medicare Tax > 0; Form 8960 only when NIIT > 0. Schedule 2 line 21 (total other taxes) flows to 1040 line 23. Field mappings derived from labeled PDF inspection (no tooltips on IRS PDFs).

15. **Form 8959 withholding reconciliation** — Part V computes excess Additional Medicare Tax withholding (W-2 box 6 minus regular 1.45% Medicare) which can offset total tax. Threshold reduction for SE income: if W-2 wages exceed the filing-status threshold, there's zero remaining threshold for SE income.

## Strategic Architecture

16. **MCP server over custom chat UI** — Don't build a chat interface (that's rebuilding Claude/ChatGPT). Instead, expose the tax engine as an MCP (Model Context Protocol) server. Any MCP-capable client (Claude Desktop, Claude Code, custom agents) can call `compute_tax`, `compare_scenarios`, `optimize_deductions` as native tools. The value is the computation engine, not the conversation layer.

17. **Modular plug-and-play design** — Tax engine should be a product-agnostic service: REST API for direct integration, MCP for agentic access. Multi-state support via pluggable state config modules (not monolithic switch statements). Design for reuse across products — the tax engine is the business asset, the interface layer is interchangeable.

18. **Multi-state as pluggable modules** — Each state's tax config is a standalone module (`state_configs/ca.py`, `state_configs/ny.py`) with rate tables, bracket definitions, exemptions, and form metadata. A generic `compute_state_tax()` dispatcher loads the appropriate module. Adding a new state = adding one config file, no engine changes.

19. **Multi-state worker computation order** — Nonresident returns computed first, then resident return with credits for taxes paid to other states. Credit formula: `min(tax_paid_to_other_state, resident_tax * (other_state_income / total_income))`. Reciprocal agreements skip the nonresident return entirely.

20. **W-2 state wage extraction** — `StateWageInfo` dataclass captures per-state wages from W-2 OCR `StateTaxInfos` array entries. Falls back to days-worked allocation when W-2s lack state breakdowns. Both paths produce the same `{state: wages}` dict for state tax computation.

21. **Generic state PDF for non-IL states** — IL uses fillable `il1040.pdf` template. All other states get a ReportLab-generated summary page showing income allocation, tax computation, withholding, and refund/owed. Adding fillable templates for specific states is a drop-in replacement via `_STATE_TEMPLATE_MAP`.

22. **1099-B as structured import, not OCR** — Brokerage consolidated statements contain multi-page transaction tables that OCR cannot reliably parse row-by-row. Accept JSON/CSV structured data instead. Plaid (Wave 10) will provide this structured data from connected brokerages.

23. **Auto-detect form type from Azure doc_type** — The `prebuilt-tax.us` auto-detect model returns `doc_type` (e.g., `tax.us.w2`, `tax.us.1099Div`). We map this to a simplified `form_type` string stored in `ocr_result.json`, enabling downstream parsers to route documents automatically without user specifying the document type.

24. **1099-DIV capital gain distributions as LTCG** — Box 2a from 1099-DIV (capital gain distributions) are treated as long-term capital gains and injected as a synthetic `CapitalTransaction` into Schedule D. This matches IRS rules — mutual fund capital gain distributions are always long-term regardless of holding period.

25. **additional_withholding param for non-W-2 withholding** — 1099-DIV (Box 4) and 1099-NEC (Box 4) federal withholding flows through a separate `additional_withholding` parameter to `compute_tax()`, added to `line_25_federal_withheld` alongside W-2 withholding. Keeps the W-2 summation clean while supporting any number of 1099 withholding sources.

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
| f1040s2.pdf | IRS irs-pdf | 64d867... | Official IRS 2025 |
| f8959.pdf | IRS irs-pdf | 13e640... | Official IRS 2025 |
| f8960.pdf | IRS irs-pdf | 9b323b... | Official IRS 2025 |
| il1040.pdf | IRS 26f25 | 30651b... | Official byte-match |
