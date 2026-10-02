# UI calibration contract

The supplied profile records observed control names only; **it is not calibrated or runnable**. Diagnostics observed SWT tables without accessible `DataItem` rows, although the screenshot showed their contents. An empty accessibility result must never be interpreted as an empty database.

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

These are generic adapter capabilities verified with simulated controls, not
completed Fakturama mappings. They do not enumerate inaccessible/virtualized
tables or prove all result rows have been read. Actual selectors, separate modal
dialogs and custom SWT table support still require live calibration.

Every parent segment must resolve uniquely. Use fresh diagnostics from the correct dialog/tab; do not use global labels repeated across editors. Avoid runtime-generated SWT IDs. Reacquire after navigation. `click_bounds` uses the current discovered control center, not stored desktop coordinates. UIA discovery retries missing controls for a bounded interval, but ambiguity stops immediately.

Scalar observations use a `path` with `read` set to `value`, `text`, or `toggle`; optional transforms are `decimal`, `date`, `blank-null`. `fields` nests observations. `rows` requires accessible rows, calibrated column names and a total-count observation proving the complete result set was read. Empty tables require an explicit empty indicator. `values` reads a calibrated dropdown's item texts. Open a dropdown when necessary; collapsed children cannot prove available choices.

## Required returned data

| Query | Required semantic data |
|---|---|
| environment | Explicit currency |
| documents | Complete candidate rows: type, no, company, reference, date, state, total |
| order | Proposed no, date, reference, price/VAT modes, both structured addresses, ordered lines, totals, discount, shipping |
| debtor_results | Company, first_name, last_name, zip, city; retain UI identity needed to select the exact row |
| payment_results | All fields returned by `payment_definition`, including zero terms and blank texts |
| debtor | Proposed customer_id and all `debtor_definition` fields, including separate delivery |
| product_results | SKU and UI identity needed for exact row selection |
| vat_results | Name, percentage value, E-Invoice code |
| product | SKU/name/description/gross/VAT/cost/stock |
| line | SKU/description/quantity/unit_net/vat_percent/discount_percent/source_net |
| invoice | Copied Order fields, order_no/order_date, proposed no/invoice_date/service_date, payment fields |
| invoice_methods | Complete available method names |

`source_net` in an observed line means the **displayed** line-net amount, not a copy of the input. Never populate observations with desired input values to pass verification. Optional absent address fields should normalize to null. Blank unpaid date/value should normalize to null; do not insert invented payment data.

## Before enabling a live profile

1. Use a disposable workspace, no unrelated dirty editors, and the expected EUR configuration. Do not automate changing the user's global currency settings.
2. Map toolbar Order, upper contact/Product selectors, current editor and follow-up Invoice menu; never use the green plus controls or toolbar Invoice.
3. Prove complete search results, including duplicates, zero results and virtualized/scrolled rows. Implement an OCR/vision fallback for the observed inaccessible grids; this is unfinished code, not just a JSON setting.
4. Implement distinct delivery-address editing and check roles. Preserve proposed numbers, dates, Standard VAT and unrelated master fields.
5. Exercise existing-master path first, then missing masters. Verify exact payment terms and fresh Debtor payment dropdown.
6. Verify Save-once behavior and persisted Documents rows, including uncertain outcomes and linked Invoice evidence.
7. Capture real evidence and update verification status. A passing completeness check only means mapping names exist, not that the mappings are semantically correct.

Navigation/search recipes must not create or save data. Otherwise they bypass the write-ahead mutation guard. Calibration profiles are trusted local code-like configuration and need review.
