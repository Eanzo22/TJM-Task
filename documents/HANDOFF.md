# Fakturama Image-to-Cash — implementation handoff

## Latest continuation (2026-10-04, Development)

### Published live UI profile

User requested including the ready-to-use live profile in the repository.
`code/config/live-profile.json` is now tracked through an explicit `.gitignore`
exception; other `live*.json` variants remain ignored. The included profile has
`calibrated:true` for the verified English/EUR UI at 1920×1080 and the tested
display scale. Its action/query mappings match the component builder and contain
no credentials or customer records. Normal `run` loads it directly. The builder
remains optional and defaults to false when replacing the supplied file.
This supersedes older notes below that the generated profile was ignored.

Work remains on **Development**. User asked to finish implementation with UIA,
simple UI date fallback and focused verification. The user requested committing
the completed implementation on Development; no push requested.
User authorized EUR and clearly labelled synthetic records in
`C:\Users\mmsss\Documents\Fakturama`. The approved old mixed-currency draft
WEB-2026-0714-A17 was discarded; do not ask again.

Implemented: complete clipboard selectors (Products six TSV columns, Debtors
nine via bounded single-row walk), fresh guarded double-click activation,
master forms and roles, payment/VAT definition inspection, Order line edits and
totals, source recipient snapshots, saved Documents verification, scoped linked
Invoice, paid/date/value entry and exact-number reopen verification. Native focus
is checked before keys; owned hidden-shell modals are discovered by bound PID and
known title. Product matching reads the blank-filter full catalogue.

Dates use the observed segmented UI and retained-value read-back. Grid geometry
is relative to freshly observed bounds, with calibrated header checks and bounded
outer-editor scrolling. Item-header hashing covers actual data headings and
excludes the unused scrollbar tail. Empty-grid detection uses the calibrated
top crop so footer changes cannot trigger Fakturama's empty-Copy exception.

**Fakturama address binding workaround:** initial Order Save must select Invoice
address. A newly added Delivery tab is bound only during that Save and may revert
the manually edited snapshot. Workflow checks both addresses after confirmed
Save, reapplies source text if needed, and performs one distinct journalled
`save_order:addresses` update. It verifies Documents and the full saved Order
before creating Invoice. Unknown Save outcomes stop; this is not a blind retry.

Live records: PO000002 → INV000001 passed save/reopen/payment checks at EUR42.84.
PO000003, reference CODEX-UIA-FULL-20261004-003, contains four ordered lines at
net619.00/VAT117.61/totalEUR736.61, date Jul14. Both saved source recipient
snapshots passed after the address update. Its linked Invoice INV000002 passed paid/save/reopen verification.
CUST000003 (CODEX TEST - Integrated UIA/Alex Example), Bank Transfer, VAT19%,
CODEX-LIVE-CHAIR-003 and CODEX-LIVE-MAT-003 are saved synthetic masters.

286 automated tests passed in12.83s; git diff --check passed. Generated `code/config/live-profile.json`
is ignored; use `scripts/build_live_profile.py` (false by default) and explicit
`--calibrated` only after reviewing the component mappings for this workspace.
All supplied component profiles remain false. `scripts/run_live_smoke.py` runs
a CODEX-labelled JSON through the same Workflow and mutation Journal.

Current private development continuation:
`code/evidence/private/continue_smoke.py`, log `continuation.log`, checkpoint
`live-smoke/51022fd06feb81056aa216fbe6654d11fda260b9103e57f5f295caeb9a0ecb7f/`.
It reconciles staged development observations and runs only unexecuted stages;
it is not a production resume feature. Inspect process/log/checkpoint before any
input; never repeat recorded mutations. The staged run is complete. A separate clean production Workflow run
also completed without intervention: **PO000004 → INV000003**, reference
CODEX-UIA-FULL-20261004-004, two lines, net570.00/VAT108.30/totalEUR678.30,
Order date Jul14, paid Bank Transfer Jul18 with full value678.30. Both source
addresses and all Invoice fields were verified after exact-number reopen.
Its checkpoint is `code/evidence/private/live-smoke/7e106fdde9a57cf665dbe52e0841e458d6aa516ccb1a84007b9b0f8704ee5f5a/checkpoint.json`,
log `code/evidence/private/clean-smoke.log`. Every recorded action returned;
the conditional address update has its own mutation key. No uncertain action
was retried in this clean run. Supported implementation work is complete;
do not create more test documents unless a new change requires verification.

Image extraction already passed separately with three real local model passes
and manual source comparison. Synthetic JSON UI verification must be described
separately from a fresh combined image command. Limits: nonzero global
discount/shipping, arbitrary layouts, uncalibrated internal grid scrolling and
mixed-rate edge cases. Invoice GUI lacks source Order number; scoped follow-up,
Order date and all copied fields are the recorded relationship evidence.

## Historical handoff below

Earlier mapping status, approvals and test counts are historical and superseded
by this latest continuation.

Prepared: 2026-10-03 (Africa/Cairo). This is a curated continuation summary, not an
import of the original chat history. Read this file and [the code README](../code/README.md)
before continuing. Inspect the actual checkout before assuming any described local
changes have reached the cloud repository.

## Implementation continuation — 2026-10-04

User direction: continue implementation on **Development**, prefer UIA and simple
keyboard interaction, and keep live testing focused on code changes. Do not resume
extended manual fixture/Invoice testing as the main task.

Implemented in `code/src/fakturama_cash/clipboard_table.py` and `ui.py`:

- Custom-grid reading using UIA focus and Ctrl+A/Ctrl+C. TSV parsing preserves
  blanks, quoted multiline cells, row order and duplicates. Stale/foreign clipboard
  data, bad columns, truncated values and unknown empty results stop the read.
- `select_copied_row`: re-read the complete table, compare content/order and UIA
  runtime identity, then position with Ctrl+Home/Down and activate once. Tokens
  are consumed before activation. This operation is simulated-test verified;
  its live row-navigation mapping remains uncalibrated.
- `type_text`: literal keyboard entry with escaped shortcut characters, a separate
  focus/commit target, and retained-value read-back (including decimal amounts).
- Dates already at the target value are left untouched; other dates retain the
  existing guarded UI keyboard/segment approach and blur verification.
- Preflight rejects dirty editor tabs before beginning another business workflow.
  Root discovery handles UIA off-screen reports and binds to one observed window
  per adapter, avoiding repeated desktop enumeration and accidental retargeting.

Added `inspect-table` and `config/table-copy.partial.json`. The real Products list
copied seven TSV cells: SKU, name, description, picture, stock, gross, raw VAT
object text. The hidden picture cell and raw VAT object mean the visible headings
alone are insufficient to infer clipboard column positions. No OCR was added.

Live command succeeded with `status: observed_table`, the test product SKU and
full description, gross `10.0`, and `business_writes: false`. Evidence is local:
`code/evidence/private/table-inspection/c335c3012b4946a4b8a7a0b02a1ff6ec.json`.
The observed stock was literal `null`; do not silently turn it into zero. VAT
remains `vat_raw`, not a fabricated numeric tax rate.

Final suite: **237 passed in 13.17s**, project virtual environment, fresh temporary
directory; `git diff --check` passed. No commit or push. Existing local edits from
the earlier continuation are preserved.

Next implementation: calibrate the debtor/product selector's copied columns and
keyboard activation, establish full off-screen copying and reliable zero-result
handling, then wire those recipes into the business profile. The supplied list
mapping has `copy_scope: unverified`: only `inspect-table` accepts it, never the
workflow or row selection. Full Order-to-Invoice automation is still incomplete.
See [the UI profile contract](implementation/ui-profile.md) for the new operations.

## Latest recovery and read-back — 2026-10-03

The user cleared the error by switching away from the tab and back. On the next
inspection, calibration Order `PO000001` was already saved (the assistant did not
perform that save). Closing its clean tab and reopening from Documents verified
reference `CODEX-UI-CALIBRATION-ONLY`, date 2026-10-03, Test Buyer address, one
unit of the calibration product at EUR 10.00, zero VAT/shipping/discount, total
EUR 10.00. No modal error occurred during this read-back.

The older unsaved `WEB-2026-0714-A17` draft now also shows a calibration product
row in EUR while its totals remain USD zero. Its number is also `PO000001`.
Do not save it or use it for further monetary testing. The cause of the row
appearing in both editors is unproven; investigate editor/event scoping. The
earlier statement that this draft stayed unchanged is superseded by this finding.

Debtor Company and product Description were repaired through focused keyboard
text entry, Tab, and current-editor Save. Both masters were closed and reopened
from their lists: Company `CODEX TEST - Selector Calibration`, Description
`Synthetic UI calibration fixture. Not an assignment product or a real sale.`,
and product price EUR 10.00 all survived. Existing saved Order snapshots retain
the earlier address and blank line description; no Order edit was saved.

Next: resolve the older unsaved mixed-currency draft before a linked-Invoice
smoke test from the saved calibration Order. Do not discard its changes without
the user's approval. Root-cause resolution, repeatable automated selection,
duplicate/scroll handling and the project's live date writer remain unverified.
All profiles remain uncalibrated. Continue on **Development**.

## Local continuation update — 2026-10-03 (earlier observations)

The active checkout is `D:\TJM Task\Implementation\TJM-Task`, on **Development**
tracking `origin/Development`, not master. Continue on Development. The inspected
HEAD was `02550d089577616f5a6d3edb0f137a4b1646e986`; the working tree was clean
before this continuation, and the latest `date_entry.py` was present.

The Windows Computer Use helper initialized successfully in this continuation.
An assistant-operated live test retained the date `2026-07-14` after blur and
verified reference `WEB-2026-0714-A17`, Net, With VAT, and unchanged proposed number
`PO000001`. The existing Order remains **unsaved**. This used Computer Use key
events and visual segment inspection, not the project's pywinauto CLI, and does
not verify its selection-offset checks or the full workflow. See
[the live test record](implementation/live-computer-use-test-2026-10-03.md).

Continuation testing opened, searched and cancelled both existing-master selectors:
`Select the address` with `Northstar`, and `Select a product` with `CHR-ERG-01`.
The header stayed unchanged, and no address or item was inserted. Both grids
looked empty but exposed no accessible rows, result count or explicit zero-result
indicator. This is not a calibrated missing-master result. Preferences > General
initially showed Currency locale `Afghanistan` and a dollar-formatted example.

After explicit user approval to use this disposable workspace, Currency locale
was changed to Germany and applied. The saved preference is `de/DE`; new editors
display euros. Product `CODEX-UI-TEST-001` was saved at EUR 10.00, Free of Tax,
with name `CODEX TEST - Selector Calibration`. Debtor `CUST000001` (the proposed
ID), Test Buyer, Test Street 1, 00000 Test City, was saved. Its Company field
appeared populated before save but was blank in the selector and inserted address;
repair and verify it using keyboard input before treating this fixture as complete.

Positive exact-ID searches displayed both saved records, but accessible rows and
counts were still absent. Debtor selection populated a **separate unsaved Order**,
reference `CODEX-UI-CALIBRATION-ONLY`, date 2026-10-03, Gross/With VAT. Both drafts
have proposed number `PO000001`; distinguish them by reference, never number alone.
The original `WEB-2026-0714-A17` draft was preserved.

Selecting the product into the calibration draft raised **Internal Error:
Currency mismatch: EUR/USD**. The app log locates it in
`DocumentSummaryCalculator.calculate` line 345 via `Money.subtract`; displayed
EUR 10.00 totals do not establish a successful insertion. Neither Order nor any
Invoice was saved. Computer Use did not reliably dismiss the error; the user was
asked to dismiss it manually while keeping both drafts open. Next: resolve this
mixed-currency state, repair/read back the test masters, then repeat the insertion
in a fresh EUR draft. A restart may clear cached currency values, but that is a
hypothesis and requires an explicit disposition of both unsaved drafts first.

Added 12 synthetic table-reader/workflow regression cases in
`code/tests/test_ui_tables.py`. The complete suite passed **203 tests in 10.42s**
using this checkout's Python 3.12 virtual environment outside the assistant's
sandbox and a fresh temporary root. Earlier launcher/temporary-directory errors
were execution-environment problems, not application test failures. See the live
test record for commands and the [selector calibration notes](implementation/selector-calibration.md)
for the next implementation and live-test work. All profiles remain uncalibrated.

The sections below preserve the earlier handoff and historical failures. Their
helper-failure and pending-date statements describe that earlier session; the
project's automated date writer still requires a separate live verification.

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
