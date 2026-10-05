# Fakturama Image to Cash

A Python CLI that extracts one order image and creates a saved Order and linked Invoice through Fakturama's Windows UI. The current flow follows the assignment's Order-first sequence, with exact master-data matching and one Save per created record.

**Status — 5 October 2026, Development:** the latest image-driven transaction saved PO000011 and INV000005 at EUR 678.30. A final Invoice-reopen calibration stop was corrected and the existing saved transaction was verified read-only. No new transaction or extra Save was needed. The original checkpoint remains `review_required`; a clean image command after that correction is still a separate verification task. [Verification details](../documents/implementation/verification.md).

## Setup in Windows CMD

All examples below are for **CMD**, from the checkout's `code` directory. Adjust the checkout and image paths for your machine.

### 1. Install prerequisites and Python dependencies

- Windows with an unlocked interactive desktop and native Windows Python. This workspace uses Python 3.12; the package requires 3.11 or newer.
- Fakturama with the supported English UI and a backed-up disposable EUR workspace. Python and Fakturama must run at the same privilege level.
- Windows English (`en-US`) OCR language support. Python packages do not install that Windows capability.
- [Ollama for Windows](https://ollama.com/download/windows), the vision-capable `gemma3:4b` model, and a readable raster input image.

```bat
cd /d "D:\TJM Task\Implementation\TJM-Task\code"
if not exist ..\.venv\Scripts\python.exe py -3.12 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -e ".[test,ocr]"
..\.venv\Scripts\python.exe -m pip check
..\.venv\Scripts\fakturama-cash.exe --help
```

Use the Python version installed on your machine if it differs. Explicit executable paths avoid needing to activate the environment. Dependencies do not install Fakturama, Ollama, model weights, or Windows language support.

### 2. Start the vision service and configure this terminal

After installing Ollama, open a new CMD window so PATH is refreshed:

```bat
where ollama
ollama pull gemma3:4b
ollama ls
curl.exe --fail http://localhost:11434/api/tags
```

If the API is unavailable, start the Ollama app or run `ollama serve` in a separate terminal. Do not start a second server if port 11434 is already served.

In the CMD session that will run this project:

```bat
set "FAKTURAMA_VISION_URL=http://localhost:11434/api/chat"
set "FAKTURAMA_VISION_MODEL=gemma3:4b"
set "ORDER_IMAGE=C:\path\order.png"
dir "%ORDER_IMAGE%"
```

Replace `C:\path\order.png` with your actual full-page order image. Repeat these settings in every new CMD session. The CLI does **not** load `.env` automatically; `.env.example` documents variables only. The local service needs no token. A private remote endpoint can use `FAKTURAMA_VISION_TOKEN`; it receives the image, so use an appropriate authorized service and keep credentials out of Git.

### 3. CPU-only fallback for the observed GPU failure

Our local GPU-backed vision request returned HTTP 500 with `prediction aborted, token repeat limit reached`, or an error/incomplete response. The same model succeeded with CPU-only requests. If you encounter that failure, inspect the section's `endpoint-error.json` or `extraction-response.json` and the Ollama logs, then set:

```bat
set "FAKTURAMA_VISION_CPU_ONLY=1"
..\.venv\Scripts\fakturama-cash.exe validate "%ORDER_IMAGE%"
```

Keep this setting in the same session when running the workflow. It sends `options.num_gpu=0` on all three requests, preserving the model, image, schemas, and validation. It is an explicit workaround for the observed backend failure, not a guarantee for every HTTP 500. It does not retry a failed business action or bypass extraction checks.

CPU inference can take several minutes per pass. Each request has a **1200-second socket timeout**; the 10-second progress heartbeat is activity reporting, not a new request or an extended timeout. To restore normal model backend selection:

```bat
set "FAKTURAMA_VISION_CPU_ONLY=0"
```

### 4. Generate and calibrate a profile on this device

Open Fakturama, configure EUR, and use its English UI. Keep the desktop unlocked and the app unobstructed. Close or resolve unrelated unsaved editors yourself before a workflow; the program does not discard them.

The tracked `config\live-profile.json` is calibrated for the observed 1920×1080 setup and display scale. On another device, generate the mappings and measure the local tables:

```bat
..\.venv\Scripts\python.exe scripts\build_live_profile.py
..\.venv\Scripts\fakturama-cash.exe calibrate --profile config\live-profile.json --output config\live-local.json
```

The builder replaces `live-profile.json` and defaults to `calibrated: false`. Its `--calibrated` flag only asserts prior review; it does **not** discover or measure a new device. Use the guided command instead of toggling that flag to bypass layout checks.

Calibration prompts you to open seven views: Documents/Orders, Documents/Invoices, VATs, terms of payment, Product selector, Debtor selector, and Order items. For each, capture an empty state and a populated state at the same size, review row/column boundaries, and confirm the full result count including off-screen rows. The runtime clipboard reader must reproduce that count.

At least one existing authorized row is required in each view to measure row height and column positions and verify Copy behavior. These are calibration records, not expected values for future orders; their names and business values are not hardcoded. The current command cannot finish against a completely empty database. Prepare suitable records manually in a disposable workspace if needed; calibration itself never creates or saves them.

For items, use a temporary unsaved New Order in Net/With VAT mode: capture it empty, then manually add one existing Product for the populated capture. After calibration, close that draft without saving, cancel selectors, and clear search filters. Do not interact with the desktop during an automated run.

Success reports `calibrated_local_profile` and writes ignored `config\live-local.json`. Failed or cancelled calibration preserves an existing output. For another pane title, use `--order-editor "Exact pane title"`. Different control labels or column order need mapping review, not just geometry calibration. [UI contract](../documents/implementation/ui-profile.md).

### 5. Validate the image and run

Using the same CMD session and your device's calibrated profile:

```bat
..\.venv\Scripts\fakturama-cash.exe check-profile config\live-local.json
..\.venv\Scripts\fakturama-cash.exe ocr "%ORDER_IMAGE%" --out evidence\private\setup-ocr
..\.venv\Scripts\fakturama-cash.exe validate "%ORDER_IMAGE%"
```

Proceed only after the checks succeed and you have reviewed the extracted evidence against the image. `ocr` returns raw OCR, not approved order data. `validate` reports `validated_image` without changing Fakturama. `check-profile` checks configuration completeness offline, not live correctness.

```bat
..\.venv\Scripts\fakturama-cash.exe run "%ORDER_IMAGE%" --profile config\live-local.json
```

`run` extracts the image again before its UI workflow. On the original calibrated setup, use `config\live-profile.json` instead. You can set `FAKTURAMA_UI_PROFILE=config\live-local.json` to select the local profile for subsequent `run` commands in that session.

Exit code **0** means the reported command completed; **2** means review is required. Only `run` reports `complete` after saved Order and Invoice verification. Progress goes to stderr; the final success JSON goes to stdout. Two rising tones indicate success and a lower tone indicates failure for the live run/validation/calibration commands. Audio is best-effort; JSON and exit codes are authoritative. `--quiet` disables progress and sounds.

## Current workflow

1. Check profile completeness, extract items, addresses, and order/customer/payment fields in three separate vision requests, and validate dates, decimals, source consistency, and arithmetic before UI writes.
2. Acquire the run lock, verify EUR, and turn off **Preferences > Documents > immediately take over a clearly found item number** when enabled. Apply once and verify it is off so Product selection requires exact matching and OK.
3. Open New Order, preserve its proposed number, fill source date/reference, and select Net/With VAT. Keep it open while resolving masters.
4. Search the upper Debtor selector. Reuse one exact Company/first name/last name/billing ZIP/city match; ambiguity or conflict stops. If missing, open a blank Debtor through **New > New Debtor**, retain its proposed ID, fill contact/address/alias fields, and resolve an unavailable payment method while that Debtor stays open. Verify, Save once, return to the Order, re-search, and select with OK. Verify each populated address role.
5. For each source item, search the upper Product selector for its exact SKU. If missing, resolve the exact VAT name/rate/code S first, then use **Data > Products > Create a new product** to force a fresh form. Fill and verify the Product, Save once, return to the Order, re-search, and select with OK. Fill and verify quantity, description, net price, VAT, discount, and line net in source order.
6. Verify all Order fields and totals with zero overall discount/shipping, Save once, and verify its Documents row. Recheck the saved Order before invoking its scoped **Create a follow-up document > Invoice** action.
7. Preserve the proposed Invoice number/date/service date and verify copied fields. Require the exact payment method. For PAID, enter the source payment date and full total; for UNPAID, do not invent a date/value. Verify and Save once.
8. Verify the Invoice and the still-open source Order in Documents, reopen the exact Invoice, and read back full persisted fields and payment. Finish without creating further document types.

Fakturama shares Company/contact headings across the two address roles. Invoice and Delivery postal fields are verified independently against their source addresses; the locations do not have to match each other. Source address-block labels remain in extraction evidence.

## Failure review and recovery

The command exits with `review_required`, stage, reason, available expected/observed values, and an evidence path. There is no interactive Retry gate or automatic checkpoint resume. Create, Save, row acceptance, and payment writes are journalled before execution and are not blindly repeated after an uncertain outcome.

**Every explicit image run starts a new Order.** It does not deduplicate by image hash/customer/reference or continue the earlier draft. A new run after a saved transaction can create another transaction. Preserve the checkpoint and inspect the recorded identifiers first:

```bat
..\.venv\Scripts\fakturama-cash.exe reconcile "runs\<image-hash>\workflows\<attempt-id>\checkpoint.json" --profile config\live-local.json
```

Use the actual checkpoint path printed by the failed run. Older `runs\<hash>\checkpoint.json` paths are also readable. `reconcile` inspects persisted document rows for recorded identifiers; it does not verify every editor field or resume writes. If identifiers are missing, inspect source details manually. Resolve any unsaved draft before another run. Never delete a checkpoint to force a retry.

Private artifacts under `runs\<image-hash>` include:

- `extractions\<attempt-id>\`: section crops/OCR, requests, responses, combined `normalized.json`, and failure reports. A saved normalized file is not proof of successful validation.
- `workflows\<attempt-id>\`: `checkpoint.json`, `events.jsonl`, and UI evidence. Every attempt has its own directory.

The run-root `.active-run.lock` prevents concurrent workflows using that same directory. Remove it only after confirming its process ended and inspecting unfinished writes. Separate run directories/machines do not share a lock.

| Failure | Next step |
| --- | --- |
| Model unset / connection refused | Set variables in this CMD session and check the Ollama API |
| HTTP 500 / incomplete GPU response | Inspect server evidence, try the CPU-only step above, and revalidate |
| OCR / required fields / totals disagree | Review the source and extraction evidence; do not substitute guessed values |
| Table layout or header changed | Recalibrate on this device and use its local profile |
| No active desktop | Run on an unlocked interactive Windows desktop |
| Persistent clipboard contention | Close competing clipboard use and inspect evidence; the reader retries access only, not Save/OK |
| Address or saved-record mismatch | Inspect the actual master/document; no second repair Save is issued |

## Development and diagnostics

```bat
..\.venv\Scripts\python.exe -m pytest -q -o cache_dir=.pytest_runs\cache --basetemp .pytest_runs\current
..\.venv\Scripts\fakturama-cash.exe validate-json tests\fixtures\synthetic_order.json
..\.venv\Scripts\fakturama-cash.exe diagnose --out evidence\private\diagnostics
```

Tests and JSON validation perform no live business writes. The local pytest paths avoid this workspace's system-temp/cache ownership issue. `diagnose` activates/maximizes Fakturama and captures it without creating or saving records. `inspect-order` and `inspect-table` support narrower read-only mapping checks; use `--help` for their profiles/options. `test-order-header` changes a temporary draft but never saves. `scripts\run_live_smoke.py` is a developer-only synthetic UI workflow requiring a `CODEX-` test reference; it creates business records and is not the image input path.

| Module | Responsibility |
| --- | --- |
| `extraction`, `table_crop`, `address_crop`, `windows_ocr` | Native-resolution crops, OCR assistance, three vision passes |
| `models`, `normalize`, `matching`, `verification` | Schema, Decimal/date rules, exact matching and comparison |
| `ui`, `clipboard_table`, `item_table`, `config/` | Scoped UIA actions, complete copied rows, calibrated cell editing |
| `calibration`, `calibration_view` | Guided local measurements and copy-count review |
| `workflow`, `state`, `cli`, `progress`, `notifications` | Sequence, mutation journal, locking, reporting, and sounds |

## Limits and next three hours

Supported scope is EUR and the assignment's image layout/English UI. Nonzero document discount/shipping, other image layouts, mixed-rate rounding edge cases, and uncalibrated internal grid scrolling need further work. OCR/model agreement can still reproduce a shared character error. A stale Debtor payment dropdown stops before Debtor Save. Invoice linkage is evidenced by the exact saved Order's follow-up action, Order Date, and copied fields; this GUI exposes no source Order number.

With three more hours, I would spend one hour validating calibration and a clean current transaction on a second device, one hour improving read-only reconciliation and operator recovery guidance, and one hour improving vision failure/cancellation feedback, focused regression coverage, and the setup demonstration.

[Requirement coverage](../documents/implementation/requirements.md) · [UI contract](../documents/implementation/ui-profile.md) · [Verification](../documents/implementation/verification.md) · [Remaining work](../documents/implementation/remaining-issues-and-test-plan.md)
