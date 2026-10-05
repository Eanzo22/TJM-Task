# Setup and run

All commands use **Windows CMD** from this checkout's `code` folder. Adjust the checkout path on another machine. Current support is the assignment image layout, English Fakturama 2.2.0, and EUR.

The latest image transaction saved PO000011 / INV000005 at EUR 678.30 and passed persisted verification after the final reopen mapping was corrected. A fresh uninterrupted run with that correction still needs verification. The latest automated suite passed 414 tests. [Results](../documents/implementation/verification.md) · [Current workflow and code structure](../README.md#current-workflow).

## 1 Install the software

Install native Windows Python (3.12 was used; 3.11+ is supported), Fakturama, Windows English (`en-US`) OCR support, and [Ollama for Windows](https://ollama.com/download/windows). Use an unlocked desktop and the same privilege level for Python and Fakturama.

```bat
cd /d "D:\TJM Task\Implementation\TJM-Task\code"
if not exist ..\.venv\Scripts\python.exe py -3.12 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -e ".[test,ocr]"
..\.venv\Scripts\python.exe -m pip check
```

The Python packages do not install Fakturama, Ollama, its model, or Windows OCR language support.

## 2 Start and configure the vision model

Open a new CMD after installing Ollama:

```bat
ollama pull gemma3:4b
ollama ls
curl.exe --fail http://localhost:11434/api/tags
set "FAKTURAMA_VISION_URL=http://localhost:11434/api/chat"
set "FAKTURAMA_VISION_MODEL=gemma3:4b"
set "ORDER_IMAGE=..\documents\Live_Task.png"
```

If the API is unavailable, start the Ollama app or run `ollama serve` in a separate CMD. Keep only one server on port 11434. `ORDER_IMAGE` uses the included sample; replace it with your image path when needed.

Repeat the `set` commands in each new terminal. `.env` is not loaded automatically. No token is needed for local Ollama; a configured private service may use `FAKTURAMA_VISION_TOKEN`.

### CPU only fallback

The local GPU backend produced HTTP 500 / `prediction aborted, token repeat limit reached`, or an incomplete vision response. CPU-only inference succeeded with the same model. If you encounter that issue, set this **before validation and run**:

```bat
set "FAKTURAMA_VISION_CPU_ONLY=1"
```

This requests `num_gpu=0` on all three vision passes without changing validation. Keep it set in this CMD session. CPU inference is slower; each pass has a 1200-second socket timeout. The progress heartbeat does not restart requests. Restore normal backend selection with `set "FAKTURAMA_VISION_CPU_ONLY=0"`. For other errors, inspect the extraction response and Ollama logs.

## 3 Configure and calibrate the new machine

Calibration teaches the program where table rows and columns are on **your screen**. It does not train the LLM or create business records. Do this once for a new display/layout, and repeat it if that layout changes.

1. Open a backed-up test workspace in Fakturama. Use English, configure General preferences for EUR, maximize the main window, and keep display scaling unchanged.
2. In **File > Preferences > Documents**, uncheck **immediately take over a clearly found item number**, click Apply, and close Preferences. This keeps the Product selector open while you measure it.
3. Make sure the workspace has an existing Debtor, Product, VAT, payment term, saved Order, and saved Invoice. Their names do not have to match the sample. If a required list is empty, create a suitable test record manually before starting; the current calibration command cannot measure an entirely empty workspace.
4. Run the commands below. Follow CMD prompts to open each table, capture it empty and populated, then mark its screenshot in the review window.

```bat
..\.venv\Scripts\python.exe scripts\build_live_profile.py
..\.venv\Scripts\fakturama-cash.exe calibrate --profile config\live-profile.json --output config\live-local.json
```

The seven tables are **Orders, Invoices, VATs, payment terms, Product selector, Debtor selector, and Order items**, in that order. You open them manually; the command captures and checks them. See the [calibration walkthrough](../documents/implementation/calibration.md) for exact navigation and screenshot clicks.

5. After `calibrated_local_profile`, cancel open selectors, close the temporary Order without saving, and clear search filters. Check the output:

```bat
..\.venv\Scripts\fakturama-cash.exe check-profile config\live-local.json
```

Use **live-local.json** for this machine's runs. The builder's `--calibrated` flag does not measure anything and should not replace this walkthrough. The tracked profile was measured on the original 1920×1080 setup. Different UI labels or column order need mapping review too.

## 4 Validate and run

```bat
..\.venv\Scripts\fakturama-cash.exe ocr "%ORDER_IMAGE%" --out evidence\private\setup-ocr
..\.venv\Scripts\fakturama-cash.exe validate "%ORDER_IMAGE%"
```

Confirm `validated_image` and compare the extracted fields with the image. Neither command changes Fakturama. Then close unrelated unsaved editors, keep the desktop unlocked/unobstructed, and run:

```bat
..\.venv\Scripts\fakturama-cash.exe run "%ORDER_IMAGE%" --profile config\live-local.json
```

`run` extracts again before the UI workflow. Only `complete` means the saved Order and Invoice passed final verification. Exit code 0 means the reported operation completed; 2 means review is required. Progress goes to stderr and success JSON to stdout. Rising tones indicate success, a lower tone failure; `--quiet` disables progress and sounds.

## If the command stops

Read the reported stage/reason and evidence. Every new `run` starts a **new Order**, even for the same image; it does not resume or deduplicate. After possible writes, inspect the printed checkpoint:

```bat
..\.venv\Scripts\fakturama-cash.exe reconcile "runs\<hash>\workflows\<attempt>\checkpoint.json" --profile config\live-local.json
```

Replace the path with the one printed by your run. `reconcile` reads saved document rows; it does not resume or verify every editor field. Keep checkpoints and resolve unsaved drafts before deciding on another run. Uncertain Save/selection/payment actions are never automatically repeated.

| Problem | Action |
| --- | --- |
| Model unset or API unavailable | Repeat this CMD session's settings; check Ollama |
| Observed GPU vision failure | Enable CPU-only inference, then validate again |
| Layout/header changed | Repeat local calibration and use its output |
| Calibration has no populated rows | Prepare the missing test records manually; do not fake the review count |
| OCR, fields, addresses or totals disagree | Inspect the source and evidence; no guessed repair or second Order Save |
| No active desktop | Run in an unlocked interactive Windows session |

## Files and diagnostics

[Code structure and boundaries](../README.md#code-structure-and-boundaries) explains how modules connect. `config/live-local.json` and `evidence/private/` contain device-specific calibration. `runs/<image-hash>/extractions/<attempt>/` contains model evidence; `workflows/<attempt>/` contains checkpoints, events, and UI captures. These generated files are ignored by Git. One run-root lock prevents concurrent commands sharing that directory.

```bat
..\.venv\Scripts\python.exe -m pytest -q -o cache_dir=.pytest_runs\cache --basetemp .pytest_runs\current
..\.venv\Scripts\fakturama-cash.exe diagnose --out evidence\private\diagnostics
```

Tests use simulated UI and make no live writes. `diagnose` activates/maximizes Fakturama and captures it without saving. Other diagnostic commands are listed by `fakturama-cash.exe --help`.

With three more hours: check calibration/current flow on a second device, improve read-only recovery guidance, then improve vision error/cancellation feedback and record a short setup demonstration.

[Requirement coverage](../documents/implementation/requirements.md) · [UI mapping details](../documents/implementation/ui-profile.md) · [Remaining work](../documents/implementation/remaining-issues-and-test-plan.md)
