# Debtor and product selector calibration

Latest implementation (2026-10-04, Development): product selector Copy returns
six raw TSV fields; debtor Copy returns nine. The earlier seventh product field
was a literal TAB at the end of a fixture description, now repaired. Raw TSV
width mismatches fail. Product Ctrl+A includes off-screen rows. Debtor Copy is
single-selection, so a bounded Home/Down/End walk verifies every identity and the
last-row boundary. A fresh debtor selector needs a plain first-row selection
before walking; Ctrl+Home alone left no selection and Copy raised an exception.

Both selectors activate a uniquely matched row by double-click, after recopying
the result set and verifying the selected row. Enter raised an application error
and is not used. Exact observed empty-grid fingerprints avoid the empty-Copy bug.
Header fingerprints include the observed debtor selection-style variants.
`config/selectors.partial.json` and the composed profile contain these mappings.
The older observations below are historical and do not describe current readiness.
See [UI profile contract](ui-profile.md).

Observed through Windows Computer Use on 2026-10-03 (Africa/Cairo), from the
unsaved Order PO000001 in the Development checkout. These are live observations
for implementation; no complete selector profile is supplied or enabled.

## Observed navigation

| Operation | Live result |
| --- | --- |
| Upper existing-contact icon beside Addresses | Opens `Select the address` |
| Contact search | Unnamed Edit beside `Search:` accepted `Northstar` |
| Contact Cancel | Closed selector; invoice address stayed blank |
| Upper existing-product icon beside Items | Opens `Select a product` |
| Product search | Unnamed Edit beside `Search:` accepted `CHR-ERG-01` |
| Product Cancel | Closed selector; no item was inserted |

The green-plus icons are distinct actions and were not used. Maximizing the main
window exposed the item-selector controls more clearly. Both modal titles and
their Search/OK/Cancel controls appeared in the main window's accessibility
snapshot; the helper's window inventory did not list the modals separately.
Do not infer a pywinauto modal selector from this helper's `dialog` role without
checking its actual UIA ControlType and ownership.

## Grid observations and limits

Visible contact columns: No., First Name, Name, Company, ZIP, City. A horizontal
scrollbar indicated additional horizontal content; no claim is made about unseen
columns. Visible product columns: Item No., Name, Description, Stock, Price, VAT.

Both grids looked empty with the search blank and with the test search entered.
Their UIA trees exposed unnamed panes and horizontal scroll controls but no
DataItem rows, result count or explicit zero-result message. Blank pixels and
missing accessible rows do not satisfy the program's complete-result contract.
The current row reader correctly stops instead of returning an empty list.

The initial empty-grid test did not verify a positive match. The later authorized
fixture test below adds positive-search and debtor-selection evidence. Conflicting
matches, duplicates, vertically scrolled results and complete enumeration remain
unverified. The 12 new cases in
`code/tests/test_ui_tables.py` verify simulated fail-closed behavior only.

## Authorized positive-fixture continuation

The user approved the open workspace as disposable and authorized EUR plus clearly
labelled debtor/product fixtures. Germany was applied in General preferences; the
saved setting reads `PREFERENCE_CURRENCY_LOCALE=de/DE`. New editors display euros.

- Saved product: `CODEX-UI-TEST-001`, `CODEX TEST - Selector Calibration`, EUR 10.00,
  Free of Tax. A direct value assignment to price reverted to zero. Selecting its
  contents, typing `10`, and pressing Tab retained `10,00 €`; save removed the
  dirty marker, and the product selector subsequently showed EUR 10.00.
- Saved debtor: proposed ID `CUST000001`, Test Buyer, Test Street 1, 00000 Test City,
  default country United States. Company was assigned `CODEX TEST - Selector
  Calibration` but did not appear in the saved selector or inserted address.
  Keyboard repair and independent read-back are pending. Other fields persisted
  as verified by selector/address read-back.
- Exact-ID searches displayed the respective row. Both positive grids still
  exposed no accessible DataItem rows or complete count. This confirms that the
  current UIA reader cannot distinguish a populated grid from an empty one.
- Double-clicking the debtor row populated the invoice address in a separate
  unsaved draft, reference `CODEX-UI-CALIBRATION-ONLY`.
- Double-clicking the product row raised `Currency mismatch: EUR/USD` from
  Fakturama's total calculator. Displayed EUR 10.00 totals are partial state;
  product insertion and totals verification **failed**, and no Order was saved.

The separate draft and the original reference-test draft both propose `PO000001`.
Use reference plus editor scope to disambiguate. Do not run the date-only CLI
against the calibration draft. Product Description appeared populated in its
editor but blank in the selector; independently check whether it persisted.

## Next work in order

Recovery update: the user cleared the error by switching tabs. The calibration
Order was subsequently found saved and passed independent close/reopen read-back
at EUR 10.00. Keyboard repairs to debtor Company and product Description also
passed close/reopen checks. The older unsaved draft now shows a EUR item with USD
totals; resolve it before the next monetary test. A restart is not currently
established as necessary or sufficient. See the latest handoff and live record.

1. Run the guarded live date-only CLI check described in the
   [live record](live-computer-use-test-2026-10-03.md). Verify selected-segment
   support and retained date before claiming the Python writer works live.
2. Resolve the EUR/USD calculation error before further monetary tests. The EUR
   preference is persisted, but consistent document currency has not been proven.
   A restart is a candidate recovery, not a verified fix; preserve or explicitly
   resolve the two unsaved drafts before restarting.
3. Repair and independently read back the test debtor Company and product
   Description using keyboard input. Extend the test master data to include a
   unique match, duplicate/conflicting matches and enough rows to scroll. Use
   application-proposed identifiers and record each save outcome before repeating.
4. Capture positive and negative selector evidence. Implement a guarded visual
   grid reader for the inaccessible tables, including observed table bounds,
   column mapping, loading/empty-state handling and complete traversal. A zero-row
   OCR result alone must never mean no matches. Preserve duplicates and the
   observed row identity needed to select exactly one candidate.
5. Add stable, scoped selector-opening/search/cancel recipes and verify their
   postconditions live. Derive unnamed icon positions from current observed
   layout; do not persist screenshot coordinates or numeric SWT IDs.
6. Exercise existing-master selection and both addresses, then items/totals,
   saved Order read-back, follow-up Invoice linkage and persisted payment.

The full profile remains `calibrated: false` until these checks and the other
requirements in [the UI profile contract](ui-profile.md) are actually complete.
