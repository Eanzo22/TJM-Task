# Remaining issues and focused verification

Updated 2026-10-04, Development. The historical Oct2 notes below describe earlier
blockers. UIA has since implemented selectors, missing masters, item editing,
document address snapshots, linked Invoice and payment persistence.

PO000002 → INV000001 passed save/reopen checks at EUR42.84. The larger four-line
PO000003 passed post-save checks at EUR736.61 after a distinct address update.
Its linked Invoice INV000002 passed paid/save/reopen checks. A separate clean
production Workflow run **PO000004 → INV000003** completed without intervention at
EUR678.30, including both saved addresses and reopened payment fields. No further
verification run is required for the current implementation.

286 automated tests passed. Address rebinding uses a separate confirmed update;
uncertain outcomes stop before Invoice. Native focus, complete clipboard reads,
item viewport guards and manual-recipient duplicate detection have coverage.

Known limits needing additional implementation only if scope expands:

- Nonzero overall discount/shipping and mixed-rate rounding edge cases.
- Other image/address layouts than the supported assignment layout.
- More lines requiring unobserved internal item-grid scrolling, large selectors
  needing off-screen activation, or other display scale/language.
- Invoice source Order number is absent from the GUI: use scoped follow-up,
  Order date and copied fields, and disclose the narrower relationship evidence.
- No automatic crash resume; reconcile each uncertain mutation before any action.

Image extraction passed separately with the real local model. A synthetic JSON
UI smoke run does not claim a fresh combined image-command demonstration.

## Historical extraction and blocker notes (2026-10-02)


Updated: 2026-10-02. The full live Order-to-Invoice cycle is not yet complete.

## Changes made

1. Items are extracted from a native-resolution table crop. Unit prices no longer
   depend on the full-page extraction that confused them with row totals.
2. Billing and delivery have a separate native-resolution crop and schema.
   The model receives fresh raw OCR lines as source evidence, not hardcoded answers.
   Model output must account for the address lines in the correct column; missing,
   invented or mismatched text stops the run. This is a consistency check, not
   independent proof: a model can copy an OCR mistake. Manual evidence review remains important.
3. A visible source CUSTOMER ID cannot silently become null. It is checked against
   the source OCR; it still does not replace Fakturama's automatically proposed ID.
4. `run` checks the UI profile before calling the model. An incomplete profile now
   fails immediately instead of consuming several minutes of extraction first.
5. Comments explain schema ownership, untrusted OCR data, native-resolution crops,
   no automatic value repair, source consistency and early preflight.

The crop-only address attempt still inserted an extra letter in the street name.
The new consistency check correctly stopped that attempt before any UI action.
The OCR-assisted address-only test passed in approximately 2m17s: both complete
addresses match the source, including `Beusselstrasse 44`. Evidence is preserved at
`code/evidence/private/address-check/ab843ac28d3d4318b4218bd3e88b998f/`.
The final combined image test passed in approximately 5m16s with
`validated_image`, two items and total `678.30`. Manual comparison of the saved
output against the source confirmed the reference/date, contact details, both
addresses, source customer ID `CUST-1007`, payment method/status/date, all item
fields and document totals. No model values were manually patched.

Evidence: `code/runs/dccd74e337dfe5a5677366c004c98742d18cdb2444c5fdc90aba38ecc239ba67/extractions/eb1a48f13ac445f7896186ddd63d11b2/`.
The complete regression suite passed **116 tests**; scoped `git diff --check`
also passed. Successful extraction is not a successful Fakturama transaction.

Address verification currently supports exactly four ordered lines in each column:
name, street, postal code/city, country. Extra or ambiguous layouts stop. It does
not reorder words or invent how additional lines map into optional address fields.

## What remains blocked

The Windows computer-use helper failed during initialization and failed again
after a reset. A later retry produced the same `helper_unknown_error: setup refresh
had errors` before initialization. No desktop inputs were issued in this work. Therefore no new live
Fakturama mapping was invented or marked calibrated.

The missing UI work is real implementation/calibration work, not a flag to toggle:

- Read all candidate rows in Fakturama's custom tables, including duplicates and
  scrolled rows. Empty accessibility children do not prove an empty table.
- Map debtor/product selection and both address editors using fresh UI observations.
- Map line editing, payment terms, VAT and missing-master forms.
- Verify follow-up Invoice creation from the saved Order and persisted document
  linkage/payment fields. Do not substitute the toolbar's unrelated new Invoice.

Keep `observed.partial.json` uncalibrated. A successful profile completeness check
alone would still not prove a successful live workflow.

## Steps to test now (CMD)

From a new CMD terminal:

```bat
cd /d "D:\TJM Task\code"
set "FAKTURAMA_VISION_URL=http://localhost:11434/api/chat"
set "FAKTURAMA_VISION_MODEL=gemma3:4b"
..\.venv\Scripts\fakturama-cash.exe validate "..\documents\qa_flow_source\source_unpacked\word\media\image9.png"
```

Expect three model passes: items, addresses, then contact/payment/header/totals.
The command does not change Fakturama. On success, inspect `normalized.json` in
the printed evidence directory against the original image. Raw responses and
request instructions are preserved under `table/`, `addresses/` and `fields/`.
On failure, inspect `review-required.json`; do not change expected totals or
source text merely to get a passing result.

For a faster address-only diagnostic:

```bat
..\.venv\Scripts\python.exe tools\check_address_extraction.py "..\documents\qa_flow_source\source_unpacked\word\media\image9.png"
```

This diagnostic uses fresh OCR and a real local model response. It cannot create
an Order or Invoice and does not count as a complete image validation.

## Steps before a live cycle

1. Restore working desktop inspection and use an unlocked desktop.
2. Open a disposable Fakturama test workspace, backed up and without unrelated
   unsaved editors. Confirm EUR is configured before testing.
3. Complete and exercise the missing mappings, then check the live profile.
4. Test an existing-master Order-to-linked-Invoice path first; verify both saved
   documents, amounts, addresses, proposed numbers and payment date/status.
5. Test missing masters, duplicate results, dropdown refresh and interrupted Save.
   Never repeat an uncertain write automatically.

Only then describe the project as a tested live end-to-end automation.
