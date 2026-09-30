# Verification and evidence — 2026-09-29

## What actually ran

- Created a local virtual environment and installed the project editable.
- Executed the pytest suite: **64 passed in 11.49 seconds**. Tests use synthetic JSON and a fake UI; they never submit data to Fakturama.
- `python -m compileall -q src` completed without errors. `pip check` reported no broken requirements.
- `validate-json tests/fixtures/synthetic_order.json` returned two items and total 678.30. This is synthetic validation, not image extraction.
- Ran the project's `diagnose` command against the real open Fakturama instance. Captured the accessibility tree, Value/Toggle observations where supported, and a real screenshot.
- Ran Windows English OCR on the supplied full-page Sales Order Input image. Retained raw text and word bounding boxes. No model-generated or manually corrected business data was substituted.
- No Order, Invoice, Debtor, Payment, VAT or Product was created or saved by this implementation during live verification.
- Attempted `run` with the actual source image and partial profile: exited with `review_required` at extraction because `FAKTURAMA_VISION_MODEL` was unset. Separately, `check-profile` listed missing action/query mappings as expected.

Test dependency versions installed: Pydantic 2.13.5, pywinauto 0.6.9, Pillow 12.3.0, pytest 9.1.1, WinRT projections 3.2.1. Installation does not prove compatibility with every Fakturama control.

## Annotated live diagnostic capture

The original screenshot is unmodified. These captions annotate its observed state; they do not claim automation created the displayed records.

![Actual existing Fakturama state, read-only diagnostic](../../code/evidence/private/diagnostics/fakturama.png)

1. **Existing document tabs:** related Order and Invoice tabs were already open. They were not created by this run and were preserved.
2. **Address and tax discrepancy:** the existing visible invoice showed Georgia and Free of Tax, inconsistent with the supplied image's Germany and VAT. This is a warning, not a completed result.
3. **Amounts and payment:** the existing visible invoice displayed a dollar-denominated 570.00 total and was unpaid. The source image requires EUR with VAT and paid information. No settings or record values were changed to hide that mismatch.
4. **Accessibility limitation:** header controls were exposed, but the captured tree had no `DataItem` controls for the visible tables. The UI adapter therefore refuses to infer that the tables contain no records.

Private originals (paths relative to `code/`):

- `evidence/private/diagnostics/fakturama.png`
- `evidence/private/diagnostics/fakturama-uia.json`
- `evidence/private/source-ocr/ocr.json`
- `evidence/private/source-ocr/ocr.txt`

These ignored files exist locally but will not appear in a clean clone. Inspect/redact and obtain permission before attaching real screenshots to an interview submission. The Markdown image will be absent in a clone without the private evidence directory.

## OCR findings

The OCR correctly recognized many labels, addresses and amounts, but misread a SKU suffix (`01` as `OI`), interpreted one discount incorrectly, and omitted percentage cells. Using arithmetic to guess the missing tax/discount or changing an ambiguous SKU would violate the input requirements. Raw OCR therefore remains a diagnostic, not an approved extraction path.

## Live end-to-end status

**Not executed successfully.** The real image is available, but the configured vision model is missing, no local model service responded, and the live UI profile is incomplete. A safe validation/preflight stop is an observed failure condition, not a successful automation demonstration. Existing related records and settings also require a disposable test workspace before business writes.

## Local repository note

Git was initialized, but nothing was staged or committed. Source files are ready for review; private artifacts and the existing Word files remain ignored and preserved. On this machine the new `.git` directory is owned by the sandbox account, so ordinary Git reports dubious ownership. Changing its owner was denied. A scoped command works without changing global settings:

```powershell
git -c safe.directory='D:/TJM Task' status --short
```

Use the same scoped option for reviewed Git operations, or have the workspace owner correct the directory ownership. Do not disable Git's ownership checks globally.
