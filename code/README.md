# Fakturama Image-to-Cash

A guarded Python prototype for reading an order image and creating an Order followed by its linked Invoice through Fakturama's Windows UI.

**Status: not yet a working live end-to-end automation.** The business workflow and safety checks are implemented and tested with a fake UI. Live accessibility discovery and raw Windows OCR succeeded. The vision service is not configured, and the live UI profile is incomplete. `run` deliberately stops rather than using guessed selectors or business values.

The existing Part 1 Word design documents are preserved unchanged. The assignment remains the authoritative specification; the deviations and unfinished work below must be disclosed with this submission.

## Setup

Use Windows with Python 3.11+, an unlocked interactive desktop, and Fakturama running at the same privilege level as Python. Use a disposable Fakturama workspace for calibration. Back up its data first; do not use customer production data.

PowerShell, from the `code` directory. The shared virtual environment remains one level above it:

```powershell
py -3 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -e ".[test,ocr]"
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\fakturama-cash.exe --help
```

The `ocr` extra is optional. It uses Windows' installed English OCR language pack and is diagnostic only. The dependency configuration is in `pyproject.toml`; the environment used for testing is recorded in [verification notes](../documents/implementation/verification.md).

## Commands

No activation is required when using these explicit executable paths.

On this workspace, the existing system pytest temporary directory is owned by a different execution account. If plain `pytest` reports access denied during fixture setup, use a fresh local test directory:

```powershell
New-Item -ItemType Directory -Path '.pytest_runs' -Force | Out-Null
$testRun = Join-Path '.pytest_runs' ([guid]::NewGuid().ToString('N'))
..\.venv\Scripts\python.exe -m pytest -q --basetemp $testRun
```

```powershell
# Validate a clearly labeled synthetic fixture; no extraction and no UI writes.
..\.venv\Scripts\fakturama-cash.exe validate-json tests/fixtures/synthetic_order.json

# Capture the live window's accessibility tree and screenshot; read-only.
..\.venv\Scripts\fakturama-cash.exe diagnose --out evidence/private/diagnostics

# Raw OCR text and word bounds. NOT structured/validated extraction.
..\.venv\Scripts\fakturama-cash.exe ocr "C:\path\order.png" --out evidence/private/ocr

# List missing mappings without connecting to the desktop.
..\.venv\Scripts\fakturama-cash.exe check-profile config/observed.partial.json
```

### Image extraction and validation

The real structured extraction path sends the single image to an **Ollama-compatible `/api/chat` vision endpoint**, requests the Pydantic schema, preserves the response, and validates all required fields and arithmetic. It does not substitute the synthetic fixture. Configure a vision-capable model that is actually installed on your service:

```powershell
$env:FAKTURAMA_VISION_URL = 'http://localhost:11434/api/chat'
$env:FAKTURAMA_VISION_MODEL = '<your-installed-vision-model>'
..\.venv\Scripts\fakturama-cash.exe validate "C:\path\order.png"
```

This machine had no configured model and no service responding on port 11434. Service provisioning and a successful real-model extraction remain prerequisites. `.env.example` documents the variables; the CLI does **not** automatically load `.env`. An optional `FAKTURAMA_VISION_TOKEN` is supplied in the Authorization header, not logged. A remote endpoint receives the entire image; use only an approved service, with HTTPS and appropriate data permission.

The document's full-page **Sales Order Input** image was available and inspected. Its smaller Fakturama screenshots are UI references, not runtime inputs. Raw OCR of the full-page image was attempted; its SKU/percentage errors were not manually patched into runtime data.

### Full workflow — blocked until calibration is complete

```powershell
..\.venv\Scripts\fakturama-cash.exe check-profile config/live.json
..\.venv\Scripts\fakturama-cash.exe run "C:\path\order.png" --profile config/live.json
```

`config/live.json` is intentionally not supplied. Do not make the partial profile runnable merely by changing `calibrated` to true. Complete and verify all action/query mappings first; see [UI calibration](../documents/implementation/ui-profile.md).

Exit code 0 means the command's reported operation completed; 2 means review is required. A successful `diagnose`, raw `ocr`, or synthetic validation is **not** a successful Order/Invoice run. Only `run` can report `complete`, after persisted-state verification.

## How the implementation is organized

| Location | Responsibility |
|---|---|
| `extraction.py`, `windows_ocr.py` | Structured vision extraction; separate raw local OCR diagnostic |
| `models.py`, `normalize.py` | Strict schema, required fields, Decimal/date parsing and reconciliation |
| `matching.py`, `verification.py` | Exact master-data matching and expected-versus-observed checks |
| `ui.py`, `config/` | Scoped UIA discovery, bounded observations, profile-driven actions and evidence |
| `workflow.py` | Order-first sequence, missing masters, linked Invoice and final checks |
| `state.py` | Input hashes, write-ahead checkpoints, exclusive run lock and JSONL events |
| `cli.py` | Commands and structured review-required errors |
| `tests/` | Synthetic fixtures and explicitly simulated UI tests |

Comments explain non-obvious safety decisions rather than narrating every line.

## Workflow and manual intervention

```mermaid
flowchart TD
  A[Read image] --> B{Required fields and totals valid?}
  B -- No --> R[Stop and report review required]
  B -- Yes --> C{UI profile ready and no prior transaction?}
  C -- No --> R
  C -- Yes --> D[Open Order; preserve proposed number; set header]
  D --> E{One exact Debtor?}
  E -- Conflict or duplicates --> R
  E -- Yes --> G[Select Debtor and verify both addresses]
  E -- Missing --> F[Resolve Payment then open fresh Debtor; fill and save once]
  F --> G
  G --> H{Next SKU exists exactly once?}
  H -- Conflict or duplicates --> R
  H -- Missing --> I[Resolve VAT; create Product; save once; reselect]
  H -- Yes --> J[Set line quantity/net/VAT/discount; verify]
  I --> J
  J -- More rows --> H
  J -- All rows --> K[Verify Order; save once; verify Documents row]
  K --> L[Create follow-up Invoice from same saved Order]
  L --> M{Copied values, linkage and payment method valid?}
  M -- No --> R
  M -- Yes --> N{Source says PAID?}
  N -- Yes --> O[Set paid, source date and full total]
  N -- No --> P[Leave paid clear; no invented date/value]
  O --> Q[Save Invoice once; verify persisted Invoice and open Order]
  P --> Q
  Q --> S[Complete; no further document types]
```

Any uncertain mutation or failed verification also goes to **Stop and report review required**. There is no unattended wait for a human and no automatic resume: the process exits with stage, reason, available expected/observed values, evidence location and a safe next action. Successful observations may be retried; saves, creation, and item insertion are not blindly repeated.

### Deliberate decisions and limits

- **Payment dropdown refresh:** the user observed that an already-open Debtor did not see a newly saved payment method until reopened. For a missing Debtor, this implementation resolves payment first, then opens a fresh Debtor while retaining the Order. This is an explicit sequencing deviation from the brief's keep-Debtor-open instruction. No unsaved Debtor is closed or discarded. The workaround is mocked, not live-verified.
- **Money:** Decimal throughout; line net and Product gross round half-up to two decimals. VAT is rounded per VAT-rate subtotal. Source totals must match exactly, and the UI must independently match before saving. This policy has not yet been verified against Fakturama for mixed-rate/fractional edge cases.
- **Input scope:** EUR only. Ambiguous three-digit decimal/grouping strings and numeric floats are rejected. PAID requires a source date; missing payment status is not treated as unpaid. Nonzero overall discount/shipping stop until their tax treatment is implemented. Unsupported payment mappings stop when creation is needed.
- **Identity:** company, first name, last name, ZIP and city must match a single Debtor result; SKU identifies a Product. Payment terms and VAT definitions are checked for conflicts. Matching ignores whitespace/case, not punctuation. Existing product prices are not silently trusted: the transaction line is set and checked against the image.
- **Reruns:** both image and normalized-input fingerprints are checked. Persisted same-company/reference candidates stop even if the date or total differs. Reference alone is not treated as globally unique. This conservative rule can require review for legitimate repeated references.
- **UI:** no fixed screen coordinates. Dynamic bounds clicks are supported only for uniquely discovered UIA controls. OCR-based custom-grid reading/clicking, robust popup selection, and separate delivery-address calibration remain unfinished. The complete live workflow is consequently unavailable.

## Evidence and recovery

Run artifacts are private and ignored by Git:

- `runs/<image-sha256>/extractions/<attempt-id>/`: original model response, extracted text, normalized JSON and extraction failure report.
- `runs/<image-sha256>/checkpoint.json`: write intentions/outcomes, verified stage and known document identifiers.
- `runs/<image-sha256>/events.jsonl`: timestamped workflow events; screenshots/UIA trees at important transitions and failures.
- `evidence/private/diagnostics/`: actual read-only Fakturama capture, not a successful business execution.
- `evidence/private/source-ocr/`: actual raw OCR observations of the supplied image.

After a timeout, do not rerun, delete the checkpoint, or repeat Save. Inspect Fakturama's Documents list, the known numbers, source company/reference/date/total and linked documents. With a calibrated profile, this command is read-only:

```powershell
..\.venv\Scripts\fakturama-cash.exe reconcile "runs\<hash>\checkpoint.json" --profile config/live.json
```

It prints matching persisted identifiers for human inspection; it does not prove all fields or resume work. If no identifier was recorded, search manually by source details. Only remove a stale `.active-run.lock` after confirming its process ended and reconciling unfinished writes. Use one process and one run directory per Fakturama workspace; cross-directory/multi-machine locking is not implemented.

See [requirement coverage](../documents/implementation/requirements.md) and [actual verification/evidence notes](../documents/implementation/verification.md). Review private screenshots before sharing: they may contain customer data. Git ignores are not a substitute for checking staged files.

## If I had 3 more hours

1. **90 minutes:** finish the existing-master live path in a disposable workspace, especially complete result-grid enumeration, fresh visual grounding, editor scoping and separate delivery addresses. Verify Order-to-Invoice linkage and persisted payment fields.
2. **45 minutes:** connect an available vision model, validate the actual image field-by-field, and test a second layout and unclear text. Keep uncertainty a review condition.
3. **45 minutes:** run missing-payment/VAT/Product/Debtor and interrupted-save cases live; capture a short annotated demonstration and revise this checklist to reflect only observed results.

These are priorities, not a promise that all integration gaps fit within three hours. Reliable live execution comes before adding more features.
