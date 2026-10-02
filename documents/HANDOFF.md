# Fakturama Image-to-Cash — cloud task handoff

Prepared: 2026-10-03 (Africa/Cairo). This is a curated continuation summary, not an
import of the original chat history. Read this file and [the code README](../code/README.md)
before continuing. Inspect the actual checkout before assuming any described local
changes have reached the cloud repository.

## 1. Objective and working preferences

Implement the supplied **Fakturama Image-to-Cash Automation** take-home assignment:
extract a sales order from its image, validate it, then use Fakturama's Windows UI
to create an Order and its linked Invoice, resolving master data and verifying
persisted results. The design and implementation represent the user to an
interviewer: explain simply and do not promise features that are not implemented.

- Give the user **Windows CMD** commands, not PowerShell syntax.
- Keep code in `code/` and design/documentation in `documents/`.
- Add meaningful comments explaining non-obvious implementation and safety choices.
- Prefer small, understandable changes with regression tests.
- Preserve existing user changes and unrelated unsaved Fakturama editors.
- Distinguish simulated tests, user-observed live results, and unverified behavior.
- A request to investigate or explain does not authorize code/UI changes.
- Do not commit, push, upload private evidence, or create/send cloud tasks without
  the user's authorization. This handoff preparation did none of those things.

## 2. Current state — do not overstate completion

**This is not yet a working live end-to-end automation.**

| Area | Verified state |
| --- | --- |
| Business workflow and guards | Implemented; exercised with synthetic data and simulated UI |
| Real image extraction | A three-pass local `gemma3:4b` run passed validation and manual field review in this local workspace |
| Windows OCR and screenshot/UIA capture | Previously exercised on the actual assignment image and Fakturama |
| Order-header reads | User confirmed the live number, date, reference and dropdown values |
| Header reference and modes | First user-run write test successfully changed these; date stayed unchanged |
| Date entry | Two whole-text approaches failed live. Latest segmented-keyboard implementation is unit-tested, **not live-verified** |
| Full live UI mappings | Incomplete; do not mark either partial profile calibrated |
| Real Order-to-Invoice transaction | No successful end-to-end run demonstrated |
| Automated suite | Re-run during handoff preparation: **191 passed in 14.75s**; automated/simulated checks, not a live business transaction |

Some older documents, especially `implementation/verification.md` and
`implementation/requirements.md`, are historical snapshots. They still describe
extraction as unconfigured/unverified and contain older test counts. Those statements
do not reflect the later successful extraction described here. Do not silently
rewrite old evidence as though the earlier attempts had succeeded.

## 3. Repository and files to read

Local repository: `D:\TJM Task`; CLI working directory: `D:\TJM Task\code`.
Shared virtual environment: `D:\TJM Task\.venv` (Python 3.12 locally;
package requires Python 3.11+).

Base HEAD when this handoff was prepared:
`f9d689ef05f5e8ef2ae1ee6d3d7cb8ea073ec075`
(`Removed unnecessary comment in the outer README`).

The following date-fix changes were **uncommitted locally** before creating this file:

- `code/README.md`
- `code/config/order-header.partial.json`
- `code/src/fakturama_cash/cli.py`
- `code/src/fakturama_cash/header_test.py`
- `code/src/fakturama_cash/ui.py`
- `code/tests/test_order_header.py`
- `documents/implementation/order-header-mapping.md`
- New file: `code/src/fakturama_cash/date_entry.py`

These files must accompany the handoff to continue the latest implementation.
A cloud checkout of the base commit alone will not contain all the date fixes.

Key reading order:

1. [code/README.md](../code/README.md): setup, commands, limitations, workflow.
2. [Order-header calibration](implementation/order-header-mapping.md): current live debugging.
3. [UI profile guide](implementation/ui-profile.md): scoped selectors and adapter operations.
4. [Requirement checklist](implementation/requirements.md): assignment coverage, with the historical-status caveat above.
5. `code/src/fakturama_cash/cli.py`, `ui.py`, `header_test.py`, `date_entry.py`.
6. `extraction.py`, `table_crop.py`, `address_crop.py`, `windows_ocr.py`,
   `models.py`, `workflow.py`, `state.py` in the same package.
7. `code/tests/` for failure expectations and simulated behavior.

The authoritative local assignment is `documents/[EXTERNAL] Take home project 2026.docx`.
The original design, simplified design, simple-flow and detailed-workflow Word files
are preserved in `documents/`. Do not delete or replace those deliverables.
They are ignored by Git and may need to be supplied separately by the user.

## 4. Exact latest date-entry problem

The successful read-only inspection returned:

```json
{"no":"PO000002","date":"2026-10-02","reference":"","price_mode":"Gross","vat_mode":"With VAT"}
```

The requested header is the same proposed number, date `2026-07-14`, reference
`WEB-2026-0714-A17`, price mode `Net`, and VAT mode `With VAT`. Do not write or
hardcode the proposed number; require the user's observed number and preserve it.

Failure sequence:

1. `inspect-order` initially called `get_value()` on a ComboBoxWrapper. Fixed to
   use `selected_text()` and reject unreadable selection rather than return the label.
   The user subsequently confirmed successful live header reading.
2. First `test-order-header`: whole-text date replacement did not retain the new date.
   Reference/Net/With VAT were correct; no Save action was sent.
   Evidence: `code/evidence/private/order-header-test/2bcd19a7c8d74bb7ad956187e0df9ffe/`.
3. Added explicit date focus, replacement, blur to reference, and immediate date
   verification. It also failed live: expected `2026-07-14`, observed `2026-10-02`.
   Evidence: `code/evidence/private/order-header-test/0c2eaba306734e96aab5fdd05b7539fa/`.
   This attempt had `date_only: false`, began with empty reference/Gross, and stopped
   at date entry **before** reference or dropdown writes. Do not assume its state
   is the same as the first failed attempt.
4. Latest change replaces whole-value assignment with guarded numeric keyboard
   entry in `date_entry.py`. No live result for this version has been received.

Installed Fakturama 2.2.0's DocumentEditor class references Nebula CDateTime.
The installed pywinauto `set_edit_text` uses UIA SetValue. Both previous approaches
were observed to leave the old date. The exact internal reason is not proven.
Do not describe the initial focus hypothesis as an established fix.

Latest date method:

- Locate the scoped Date Edit and separate reference-field focus target.
- Focus reference, then date; verify focus.
- Parse the observed English `Oct 2, 2026`-style text and accessible selection offsets.
- Navigate with bounded right-arrow presses until the intended segment is selected.
- Type numeric digits using `vk_packet=False`; verify field focus and foreground
  ownership before and after every key. Do not automatically refocus after loss.
- Set day 1 when needed, then year/month/final day, checking intermediate values
  to handle month-end and leap-year transitions safely.
- Blur to reference without editing it; compare retained date, then the whole header.
- No Enter, clipboard paste, Save, automatic rollback or business-action retry.

Live risks to verify: SWT's exposed selection offsets/Text pattern, keyboard event
behavior, format/locale assumptions, timing and retention after blur. If a pattern
is missing, stop and gather evidence; do not replace the check with a guessed click.
Simulated controls now ignore SetValue even while focused, matching both live failures.

## 5. Commands for the next local verification

Keep the unsaved test Order open and start with inspection. These commands are for
the user's **local Windows CMD**, not a Linux cloud shell:

```bat
cd /d "D:\TJM Task\code"
..\.venv\Scripts\fakturama-cash.exe inspect-order
```

If number is still PO000002, reference is empty, and modes are Gross/With VAT:

```bat
..\.venv\Scripts\fakturama-cash.exe test-order-header --expected-number PO000002 --date 2026-07-14 --reference WEB-2026-0714-A17
```

Only if reference already matches and modes are Net/With VAT, explicitly repair just date:

```bat
..\.venv\Scripts\fakturama-cash.exe test-order-header --expected-number PO000002 --date 2026-07-14 --reference WEB-2026-0714-A17 --date-only
```

Both commands remain guarded calibration tests, not full-workflow resume. They
leave the Order unsaved and preserve unique before/after evidence. Success must be
`verified_unsaved_order_header`. Inspect failures; intermediate dates may remain.
Do not clear fields simply to bypass initial-state guards. Use the actual observed
number if it differs from the example and confirm the intended test editor first.

After live header verification, proceed incrementally to the debtor selector,
product selector, result tables, master-data forms, addresses, lines/totals, saved
Order read-back, linked Invoice and persisted payment verification. Do not attempt
the whole business flow while the mappings are incomplete.

## 6. Extraction and setup facts

- Install project with `pip install -e ".[test,ocr]"` from `code/`.
- Windows `en-US` OCR support must be installed separately from the WinRT pip extra.
- Local Ollama must run with the downloaded vision model `gemma3:4b`.
- In every new CMD session set:

```bat
set "FAKTURAMA_VISION_URL=http://localhost:11434/api/chat"
set "FAKTURAMA_VISION_MODEL=gemma3:4b"
```

- `.env` is not automatically loaded, and virtual-environment activation does not
  configure these variables. An optional remote service token must stay private.
- `validate` uses three sequential model calls: OCR-located item crop, focused
  address crop with OCR hints, full-image non-item/non-address fields.
- Exact address/source-customer-ID consistency checks and Decimal arithmetic
  reconciliation reject discrepancies. OCR assistance is not independent agreement
  between two readers. Both readers may still agree on a mistake.
- Each request has a 1200-second socket timeout. CPU inference can take minutes.
- Source input is a readable raster image, not DOCX/PDF/SVG directly. No fixture or
  manually corrected business values may replace extraction at runtime.
- `run` checks UI profile completeness before spending time on extraction.
  `config/live.json` is intentionally absent; partial profiles remain false.

Local source image:
`documents/qa_flow_source/source_unpacked/word/media/image9.png` (1489 x 2048).
SHA-256: `dccd74e337dfe5a5677366c004c98742d18cdb2444c5fdc90aba38ecc239ba67`.
Successful extraction evidence recorded earlier:
`code/runs/<image-sha256>/extractions/eb1a48f13ac445f7896186ddd63d11b2/`.

Manual QA reference from the assignment, **never a runtime fallback**:

- Order WEB-2026-0714-A17, 2026-07-14, EUR; source customer ID CUST-1007.
- Northstar Office GmbH; Marta Klein; alias NORTHSTAR-BERLIN.
- Billing: Friedrichstrasse 88, 10117 Berlin, Germany.
- Delivery: Northstar Office Warehouse, **Beusselstrasse 44**, 10553 Berlin, Germany.
- Bank Transfer; PAID; payment date 2026-07-18.
- CHR-ERG-01: quantity 2, unit net 250, discount 10%, VAT 19%, line net 450.
- MAT-DESK-02: quantity 3, unit net 40, discount 0%, VAT 19%, line net 120.
- Net 570.00; VAT 108.30; total 678.30.

## 7. Workflow decisions and remaining gaps

- Order first; preserve application-proposed IDs/numbers; create Invoice as an
  Order follow-up, not an independent Invoice. Verify copied values and linkage.
- Exact Debtor/SKU matching; duplicate/conflicting results stop instead of guessing.
- Payment refresh: user observed a new payment method missing from an already-open
  Debtor until reopening. The implemented missing-Debtor path resolves payment
  **before opening a fresh Debtor**. This is a disclosed sequencing deviation from
  the assignment, mocked rather than live-verified. Never discard unsaved Debtors.
- Decimal calculations and reconciliation are enforced. EUR only; nonzero overall
  discount/shipping tax allocation is unfinished and causes a review stop.
- New Product/VAT/payment/Debtor paths and persisted reads still need live calibration.
- SWT custom tables previously exposed no accessible DataItem rows. Empty UIA rows
  are not proof that a table is empty. Full enumeration/grid interaction remains a gap.
- Header selectors are scoped under exactly one visible `Pane` named `New Order`.
  Unnamed fields use fresh geometry relative to labels; no fixed screen coordinates
  or volatile numeric SWT IDs. Pane-title changes may require further calibration.
- Adapter includes verified tab-selection and bounded panel scrolling primitives;
  actual tab/scroll mappings and UIA patterns must still be observed.
- Capture restores/maximizes/activates Fakturama and checks foreground/bounds before
  and after. It uses screen-region pixels; always-on-top overlays can still obscure it.
- Diagnostic/header-test sounds are best-effort. JSON and exit codes are authoritative.
- Journal checkpoints precede uncertain mutations; never blindly repeat Save/create.
  `reconcile` is read-only inspection, not automatic resume.

## 8. Desktop helper versus project automation

The assistant's Computer Use helper is separate from the project's pywinauto CLI.
The user has been able to run local CLI tests while the assistant's helper failed.

Latest retry on 2026-10-03 used the installed computer-use skill version
`26.930.21537`. Initialization failed with:

```text
windows sandbox failed: helper_unknown_error: setup refresh had errors
```

Resetting the JavaScript session and retrying also failed (trusted Node process
exited unexpectedly). No live desktop action was performed in this retry.
Do not claim the plugin is simply disabled, launch hidden helper executables,
weaken security, or bypass computer-use skill restrictions with another UI driver.
Follow whichever computer-use skill is available in the destination environment.

A Codex cloud checkout does not automatically receive the user's running Windows
desktop, local Ollama on port 11434, files on drive D:, or desktop permissions.
Cloud work can inspect/edit code and run compatible simulated tests; live Windows
OCR/Fakturama verification needs the appropriate Windows environment or user-run checks.
No Linux/cloud test run has been verified in this handoff.

## 9. Tests and artifact availability

Local test command (no live UI writes or model calls):

```bat
cd /d "D:\TJM Task\code"
set "PYTEST_DEBUG_TEMPROOT=%CD%\.pytest_runs"
..\.venv\Scripts\python.exe -m pytest -q
```

`.gitignore` excludes `.venv/`, private evidence, `runs/`, `.env`, `*.docx`, `*.pdf`,
QA extraction directories and `code/config/live*.json`. A clean cloud checkout
therefore may lack the assignment, source image, screenshots, raw responses and
complete live profile. Ask the user to provide approved necessary artifacts;
do not force-add private folders or publish customer data/secrets.

## 10. Suggested first prompt for the cloud task

> Read documents/HANDOFF.md and code/README.md before changing anything. Confirm
> that the latest date_entry.py and associated changes are present in this checkout.
> Preserve unrelated changes. Continue the Fakturama take-home implementation with
> small, commented, tested changes and CMD instructions for the user. The latest
> date-entry approach and full UI workflow are not live-verified. First review the
> segmented date writer and available test/evidence gaps; do not claim simulated
> success proves live success. Do not run business writes, commit, push, or expose
> private evidence without the user's authorization.
