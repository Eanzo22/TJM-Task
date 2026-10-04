# UI calibration contract

Supplied component profiles remain **calibrated:false**. The repository includes
`config/live-profile.json` with **calibrated:true**, verified for the observed
English/EUR UI at 1920×1080 and the tested display scale. The builder can regenerate
it; review and calibration are required for a different setup. Live Order/Invoice results are in the
latest handoff. SWT tables expose no `DataItem` rows, so calibrated clipboard
reads are used. Empty accessibility children never imply an empty database.

## Profile format

- `window_title_re`: must identify exactly one visible Fakturama window.
- `calibrated`: explicit operator sign-off after all mappings are completed and exercised.
- `actions`: every semantic action in `workflow.ACTIONS`, each a list of steps.
- `queries`: every name in `workflow.QUERIES`, each an observation specification.
- `timeout_seconds`: bounded observation timeout (default 10 seconds).

A step has `path` (successive scoped UIA name/type/automation-ID constraints), `operation` and optional `value`. Supported operations: `invoke`, `select`, `set`, `toggle`, `click_bounds`. `${input.external_reference}`, for example, is a dictionary lookup in workflow context, not executable code. `wait_query` waits for stable observations after a step but is not a business postcondition; the workflow owns those checks.

### Small navigation additions

Live preflight and `diagnose` now activate and maximize the main Fakturama window,
then verify maximization and stable foreground bounds. `check-profile` remains
read-only configuration checking and does not connect or resize the desktop.
Keep display scaling unchanged while a run is active.

Two navigation operations are available for calibrated recipes:

- `select_tab`: `path` must identify one enabled `TabItem`, scoped beneath the
  appropriate editor/tab container. It selects once, reacquires the control and
  verifies selection. Chain outer-tab then inner-tab steps for nested tabs.
  If SWT exposes a broken SelectionItem method, it first checks the tab again,
  then clicks that tab's current UIA bounds if selection is still needed.
- `scroll_to`: `path` identifies the scrollable panel; `target_path` is relative
  to that panel. `direction` is up/down/left/right (default down), and `max_steps`
  is 1–30 (default 8). It checks for a fully visible target, scrolls one page,
  reacquires the panel/target, and stops at the limit, timeout or scroll boundary.
  It requires UIA Scroll support. No coordinate/wheel fallback is assumed.

Queries, including nested `fields` groups, may contain a `prepare` list using
only these two operations. This lets billing and delivery groups open different
tabs before reading. Preparation may run for each snapshot during stable-value
polling: it must never save, type, create records or select a business result row.
Unsupported patterns or ambiguous targets stop with `review_required`.

These navigation operations are mapped in the current composed profile. Table
completeness is a separate contract, verified through copied rows and calibrated
boundaries as described below; navigation alone does not prove completeness.

Every parent segment must resolve uniquely. Use fresh diagnostics from the correct dialog/tab; do not use global labels repeated across editors. Avoid runtime-generated SWT IDs. Reacquire after navigation. `click_bounds` uses the current discovered control center, not stored desktop coordinates. UIA discovery retries missing controls for a bounded interval, but ambiguity stops immediately.

`below_label: "Items"` (or another observed Text label) narrows candidates to the
nearest control below the label with overlapping horizontal bounds. The label
must be unique in the scoped parent, and tied controls remain ambiguous. This
supports the unnamed existing-master icons without fixed screen coordinates;
calibrate the target dialog and distinguish these icons from green-plus actions.

Scalar observations use a `path` with `read` set to `value`, `text`, or `toggle`; optional transforms are `decimal`, `date`, `blank-null`. `fields` nests observations. `rows` requires accessible rows, calibrated column names and a total-count observation proving the complete result set was read. Empty tables require an explicit empty indicator. `values` reads a calibrated dropdown's item texts. Open a dropdown when necessary; collapsed children cannot prove available choices.

### UIA keyboard support for custom grids

`clipboard_rows` is an alternative to accessible `rows`. It focuses the scoped
control through UIA, sends Ctrl+A/Ctrl+C, and parses the resulting tab-separated
text. It does not use OCR, fixed desktop coordinates or database access. The copy
must update the clipboard and be owned by the Fakturama process; stale content,
focus loss, mismatched columns/headers and truncated text stop the read. Copying
replaces the system clipboard. Quoted TSV cells may contain tabs/newlines;
empty cells and duplicate rows are preserved.

Illustrative query structure (not a live-calibrated mapping):

```json
{
  "path": [{"control_type": "Pane", "title": "Products"},
           {"control_type": "Pane", "leaf": true}],
  "clipboard_rows": {
    "columns": ["sku", "name", "description", "stock", "gross", "vat"],
    "copy_scope": "all_rows",
    "keyboard_selection": "ctrl_home_down_enter"
  }
}
```

`leaf: true` narrows discovery to controls with no accessible descendants; it is
still required to resolve uniquely. It is not a generic grid identifier. Scope it
beneath the observed list or selector dialog. Do not use it if that parent has
multiple leaf panes.

`copy_scope: all_rows` must be established by a live scroll/multiple-row check:
Ctrl+A/Ctrl+C must include off-screen rows and columns, not just visible cells.
If the grid cannot do this, this implementation is not applicable; leave its
mapping disabled. Optional `headers` contains the exact copied heading cells,
which are checked then removed. Omit it only when copying excludes headings.
Optional `total_count` uses the existing scalar-query format and must match the
copied row count. Zero rows always require an explicit `empty_indicator` and
`empty_text`; failed/blank copies never imply a missing master.

For selection, use an action step with `operation: select_copied_row`, `query`
equal to the result-query name, and `value: ${selected_product}` or
`${selected_debtor}`. Returned records carry an internal `_ui_row` token. The
adapter recopies and compares the complete result set and table runtime identity
before positioning with Ctrl+Home, one Down per preceding row, and Enter once.
This navigation must be independently calibrated as `ctrl_home_down_enter`.
Changed ordering/content, replacement tables, forged tokens and replay attempts
stop before activation. The workflow still verifies the resulting address/line.

Use `inspect-table QUERY --profile PATH --out evidence/private/table-inspection`
to exercise only the read in a partial profile. It accepts no navigation recipes
and does not activate a row or save. A successful copy is not proof of complete
live calibration.

The supplied `config/table-copy.partial.json` maps the observed Products list.
Its `copy_scope: unverified` is accepted only by `inspect-table`; ordinary workflow
reads and preflight reject it even if someone sets `calibrated: true`. Inspection
does not issue row-selection tokens. Product copy has six cells: SKU, name,
description, stock, gross price and VAT object. The earlier seventh cell was a
literal TAB in a fixture description, which was repaired. Raw TSV cannot escape
embedded tabs; malformed widths fail. `item_table.py` separately parses observed
item VAT fractions and negative discount fractions.

Live preflight also stops when any dirty editor tab (`*`) is open. It does not
close or save those editors. This prevents starting another transaction alongside
the unsaved mixed-currency editor observed during the earlier test.

### Text entry through keyboard events

`operation: type_text` targets an Edit and requires a distinct `commit_path`.
It selects the contents, types literal text, moves focus to the commit control,
and verifies the retained value. Keyboard syntax in the value is escaped;
embedded control characters/newlines are rejected. `transform: decimal` compares
formatted currency numerically (use the editor's observed decimal separator in
the input). This is useful for SWT fields where SetValue changes displayed text
without committing the underlying model. Date fields keep the existing segmented
keyboard implementation and post-blur read-back; already-correct dates are left
untouched.

## Required returned data

| Query | Required semantic data |
|---|---|
| environment | Explicit currency |
| documents | All Order and Invoice candidate rows: type, no, rendered customer, reference, date, state, total |
| order_header / order_addresses | Focused early checks, without copying the empty item grid |
| order | Proposed no, date, reference, price/VAT modes, both structured addresses, ordered lines, totals, discount, shipping |
| debtor_results | Company, first_name, last_name, zip, city; retain UI identity needed to select the exact row |
| payment_results / payment | List identity and row token; matching editor supplies full `payment_definition` fields |
| debtor | Proposed customer_id and all `debtor_definition` fields, including separate delivery |
| product_results | SKU and UI identity needed for exact row selection |
| vat_results / vat | List identity and row token; matching editor supplies percentage and E-Invoice code |
| product | SKU/name/description/gross/VAT/cost/stock |
| line | SKU/description/quantity/unit_net/vat_percent/discount_percent/source_net |
| invoice | Copied Order fields and order_date, proposed no/invoice_date/service_date, payment fields |
| invoice_methods | Complete available method names |

`source_net` in an observed line means the **displayed** line-net amount, not a copy of the input. Never populate observations with desired input values to pass verification. Optional absent address fields should normalize to null. Blank unpaid date/value should normalize to null; do not insert invented payment data.

## Before enabling a live profile

1. Use a disposable workspace, no unrelated dirty editors, and the expected EUR configuration. Do not automate changing the user's global currency settings.
2. Map toolbar Order, upper contact/Product selectors, current editor and follow-up Invoice menu; never use the green plus controls or toolbar Invoice.
3. Prove complete search results, including duplicates, zero results and virtualized/scrolled rows. For inaccessible grids, first calibrate the UIA keyboard/copy reader described above. It cannot be enabled on grids that copy only a visible subset or do not expose a reliable empty indication.
4. Implement distinct delivery-address editing and check roles. Preserve proposed numbers, dates, Standard VAT and unrelated master fields.
5. Exercise existing-master path first, then missing masters. Verify exact payment terms and fresh Debtor payment dropdown.
6. Verify each intentional Save and persisted Documents rows, including address rebinding, uncertain outcomes and linked Invoice evidence.
7. Capture real evidence and update verification status. A passing completeness check only means mapping names exist, not that the mappings are semantically correct.

Navigation/search recipes must not create or save data. Otherwise they bypass the write-ahead mutation guard. Calibration profiles are trusted local code-like configuration and need review.

## Composed English UIA profile (2026-10-04)

`scripts/build_live_profile.py` composes master forms, definitions, selectors and
document mappings into the tracked `config/live-profile.json`. Rebuilding defaults
to an uncalibrated result and replaces the supplied profile; `--calibrated` is an
explicit mapping review assertion. Normal `run` uses the supplied file directly.
The user authorized the EUR synthetic workspace on Development.

`select_tree` explicitly selects Orders or Invoices. `documents` combines both
categories rather than inheriting the view's previous filter. Copies include
off-screen rows. Exact empty-grid fingerprints prevent triggering Fakturama's
empty-Copy exception. Reopening an Invoice searches its exact number before
verified row activation.

`type_address` writes canonical multiline snapshots and reads them after blur.
The contact editor has global Company/first/last names, so master verification
checks postal fields and address roles; per-address recipient names are verified
in the document itself. Additional/specification/district lines are preserved.

`edit_item_cell` verifies the copied SKU at the intended index, intersects ancestor
viewport bounds, scrolls the discovered editor through UIA ScrollPattern, and
double-clicks the calibrated cell. A transient editor's committed value is checked
through a new grid copy. An unobserved internal grid scroll or changed header stops.

Save recipes select Invoice address first. Fakturama otherwise raised an internal
exception when saving with Delivery address selected. Dates use the observed
segmented keyboard UI and post-blur verification. Unchecked paid controls return
null date/value without reading hidden fields.

The UI exposes Order Date on the linked Invoice but no source Order number.
The recipe invokes Invoice inside the exact saved Order pane, rechecks that Order,
and verifies all copied values. The journal records that narrower relationship
evidence; it never invents a relationship identifier.

Product search reads the complete catalogue with a blank filter, then exact-matches the SKU. It avoids the observed SWT search-field activation problem. Selection still requires a fresh row token and verified row before double-click.

A newly added Delivery address tab lacks its text binding until initial Save. Saving with Delivery selected raised an internal exception. Initial Save therefore selects Invoice address. The workflow then checks both saved snapshots; if rebinding changed them, it reapplies the source addresses and makes one distinct `save_order:addresses` update. Both saves have separate mutation keys and Documents verification. This is a deliberate update after a confirmed Save, not a retry.
