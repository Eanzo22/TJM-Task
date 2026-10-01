# Table-crop extraction experiment

Date: 2026-10-01. Status: successful on the supplied image in one local run;
not integrated into the production extraction path.

## What changed

Added `code/tools/experiment_table_crop.py`, a standalone diagnostic script.
Windows OCR locates the ITEMS label, all eight column headings, and NET TOTAL.
The script stops if these anchors are missing, duplicated, or vertically inconsistent.
It saves a full-width crop at the original resolution and asks local `gemma3:4b`
to extract only the item table using the existing Line model's string-decimal schema.
OCR values are not substituted for model output. Expected answers are not included
in the request. There are no UI actions, retries, arithmetic repairs, or updates
to the main extractor. The existing 1200-second timeout is preserved.

This is a deliberately limited detector for the supplied single-table layout,
not a general document/table detection system.

## Observed result

Source: the original `image9.png` extracted from the assignment document.
SHA-256: `dccd74e337dfe5a5677366c004c98742d18cdb2444c5fdc90aba38ecc239ba67`.
Fresh OCR produced crop bounds `(0, 1357, 1489, 1815)`: 1489 x 458 pixels.
Those coordinates are recorded evidence, not fixed coordinates in the detector.

| SKU | Description | Qty | Unit | Unit net | Discount | VAT | Line net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CHR-ERG-01 | Ergonomic Desk Chair | 2 | pcs | 250.00 | 10% | 19% | 450.00 |
| MAT-DESK-02 | Anti-Fatigue Desk Mat | 3 | pcs | 40.00 | 0% | 19% | 120.00 |

Both rows, their order, and all eight fields per row were visually compared with
the original-resolution crop and match. The model reported no extraction issues.
The unchanged line arithmetic gives 450.00 and 120.00 respectively.
The model reported 266.42 seconds; the whole script took approximately 4m35s.
This is not a controlled speed benchmark; tests were running concurrently.

Evidence is preserved locally under
`code/evidence/private/table-crop/trial-20261001-01/`: OCR, crop image, crop metadata,
request instructions/schema, raw response, normalized items, and arithmetic results.
This private evidence directory is excluded from Git.

## Verification and limits

- All 89 tests passed, including five new crop tests: scaling, missing header,
  duplicate anchor, displaced header, and incorrect section order.
- One successful source-image run does not establish reliability on other images.
- Passing arithmetic alone does not establish correct identifiers or text;
  this experiment included a manual source comparison.
- Customer, addresses, order reference, payment and document totals were not
  re-extracted by this table-only request. The earlier full-page address typo
  remains unresolved. No complete order was declared validated.
- Fakturama was not changed. Normal `validate` still uses the original full-page path.

## Reproduce in CMD

```bat
cd /d "D:\TJM Task\code"
set "FAKTURAMA_VISION_URL=http://localhost:11434/api/chat"
set "FAKTURAMA_VISION_MODEL=gemma3:4b"
..\.venv\Scripts\python.exe tools\experiment_table_crop.py ..\documents\qa_flow_source\source_unpacked\word\media\image9.png
```

Each invocation creates a new evidence directory. Add `--crop-only` to inspect
the detected crop without calling the model. An explicit `--out` must name a
directory that does not already exist, to preserve previous evidence.

## Proposed next step (not implemented)

Integrate separate table and non-table extraction only after checking the
non-table fields against the source, particularly exact address spelling.
Combine the independently extracted sections, preserve both raw responses, and
run the existing complete OrderInput validation and reconciliation. Any uncertainty
must still stop before UI writes. Do not use the known expected values as runtime data.
