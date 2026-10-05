# UI profile and device calibration

Current implementation on Development, updated 5 October 2026. The adapter targets the observed English Fakturama 2.2.0 UI. The tracked `code/config/live-profile.json` is calibrated for the original 1920×1080 desktop and display scale; component `*.partial.json` files are development mappings, not standalone workflow profiles.

## Generate and measure on another device

From `code/` in CMD, with dependencies installed and Fakturama open:

```bat
..\.venv\Scripts\python.exe scripts\build_live_profile.py
..\.venv\Scripts\fakturama-cash.exe calibrate --profile config\live-profile.json --output config\live-local.json
..\.venv\Scripts\fakturama-cash.exe check-profile config\live-local.json
```

The builder combines reviewed mappings and replaces its output with `calibrated: false`. `--calibrated` asserts prior mapping review; it does not measure UI geometry. The guided command measures seven operator-opened tables: Orders, Invoices, VATs, payment terms, Product selector, Debtor selector, and Order items. Use an unlocked, unobstructed desktop and the same table sizes for empty/populated captures.

For each view, filter to zero results for the empty capture, then expose at least one existing authorized row. Review boundaries/columns and enter the complete result count, including off-screen rows. Calibration reads through the same runtime clipboard reader and compares that count. A populated row establishes row height, column locations, and copy behavior; its business values are not fixed expected values for later transactions. A completely empty workspace cannot satisfy the current command.

For items, manually prepare an unsaved New Order in Net/With VAT mode: capture it empty, then add one existing Product. Afterwards close the draft without saving, cancel dialogs, and clear filters. Calibration never creates/saves records or activates a result row, but it changes focus/selection and replaces the clipboard. For another editor title, pass `--order-editor "Exact pane title"`.

All seven tables must pass before `live-local.json` is atomically replaced and marked calibrated. Failed/cancelled sessions preserve an existing output. Captures, measurements, and an unfinished draft profile remain private under `code/evidence/private/calibration/`. The local output is ignored by Git. Use it with `run --profile config\live-local.json`; changed language/control labels require selector review as well as geometry calibration.

## Discovery and observations

Profiles contain `window_title_re`, `calibrated`, `timeout_seconds`, `actions`, and `queries`. Every required name in `workflow.ACTIONS` and `workflow.QUERIES` must be mapped. The current composed profile uses a 120-second UI timeout. `check-profile` checks completeness offline; it does not establish live correctness.

Paths are successive scoped name/type/automation-ID constraints. Each parent must resolve uniquely; ambiguous targets stop immediately. Relative label/bounds constraints locate unnamed controls from their current UIA geometry. Avoid volatile numeric SWT IDs and global labels repeated across editors. Reacquire controls after navigation. `click_bounds` uses the freshly observed control, not fixed desktop coordinates.

Scalar reads use value, text, native text, or toggle patterns with date/decimal/null transforms. `fields`, merged queries, and concatenated queries compose semantic records. `prepare` navigation is restricted to reviewed read-only operations. Observations must contain actual UI values; desired source values must never be substituted to pass a check.

Preflight activates/maximizes exactly one Fakturama window, checks safe foreground bounds, and rejects dirty editor tabs. It does not close/save them. Keep display scale and foreground stable during execution.

## Tables and row selection

SWT/NatTable grids expose no usable `DataItem` rows in the observed environment. `clipboard_rows` focuses the scoped grid and copies TSV, verifying focus, clipboard freshness/ownership, column count, and complete copy scope. Empty accessible children or blank/stale Copy do not imply zero results. Empty states require reviewed pixel fingerprints; the reader avoids Copy on a confirmed empty grid.

Products expose six raw columns; Debtor results expose nine and use a bounded single-row walk where necessary. Duplicate/empty cells remain significant. Optional total counts must equal the copied row count. Malformed data or a visible-only subset stops rather than authorizing missing-master creation. `copy_scope: unverified` is accepted only by the narrow `inspect-table` diagnostic.

Matched rows carry an internal token. Before selection, the adapter recopies the result set, verifies table identity/content/order, positions the row, and compares a single-row Copy. Order Debtor/Product selectors then invoke the scoped OK once through `ctrl_home_down_confirm`. Documents activation uses reviewed relative row geometry after the same row check; changed/off-screen rows stop.

`OpenClipboard` access-denied errors retry only the read for up to three seconds, with focus, sequence, and target ownership checks. Ctrl+C, OK, and Save are not replayed. Persistent blockage reports `table_read` review.

Item cell editing checks the SKU/index, ancestor viewport, data-header hash, and calibrated column positions. UIA outer-editor scrolling is supported; uncalibrated internal grid scrolling stops. Extra unused space on the right is accepted only with the identical data header and existing column positions; a narrower canvas or changed header stops. Empty items use the calibrated crop. Documents accept only the explicitly reviewed header variants, not arbitrary layout changes.

## Text entry and creation controls

`type_text` uses literal keyboard input into an enabled Edit, a distinct commit target, and retained-value read-back. Decimal comparison tolerates the observed presentation separator. Dates use verified numeric segments and post-blur read-back, leaving already-correct values untouched.

Product search uses `type_search`: focus the scoped Search Edit, type the literal SKU without Enter or button blur, reacquire the field, and require stable retained text. It never reopens or accepts the dialog. Exact matching and OK follow separately.

Before opening the Order, preflight reads **Preferences > Documents > immediately take over a clearly found item number**. The page's internal Text heading is Document Settings, not a TreeItem. If enabled, a journalled action unchecks it and invokes Apply once; read-back must confirm it is off. This persists the setting and prevents automatic single-result acceptance during search.

The installed Navigation View shortcuts can reopen existing masters. Missing Debtors use **New > New Debtor** and require blank Company/first/last fields. Missing Products resolve VAT first, then use **Data > Products > Create a new product** and require blank Name/Description. Proposed Customer ID is preserved; proposed Product Item Number is replaced with the source SKU. The Order stays open.

Missing payment methods are resolved while the fresh Debtor stays open. After exact term inspection/creation, its dropdown must expose the method once; otherwise stop before Debtor Save. Save recipes select Invoice address first to avoid the observed exception when Delivery is active. Order Save occurs once; saved-address rebinding is reported, not repaired with another Save.

## Address and relationship checks

Company/contact are shared Debtor fields. `document_addresses` checks each rendered heading against Company and each role's postal/optional fields against its source address independently. Source billing/delivery block names remain intact in extraction evidence. The parser accepts a separate matching contact line and Germany's `DE-` five-digit ZIP presentation; arbitrary extra lines or conflicting headings/postal values stop.

Order selection, Order pre/post-save checks, copied Invoice checks, and persisted Invoice checks use that same mapping. Billing and delivery locations need not equal each other. Optional missing address fields normalize to null; unpaid date/value normalize to null without inventing payment details.

The GUI exposes Order Date but no source Order number on Invoice. The workflow verifies the exact saved Order, invokes Invoice inside that pane, and checks copied values; the journal records this narrower relationship evidence. Reopening closes only the clean selected Invoice, filters Documents by its exact number, and verifies the persisted editor.

For commands and failure recovery, see [code README](../../code/README.md). For observed results rather than mapping assertions, see [verification](verification.md).
