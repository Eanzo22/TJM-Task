# First mapping group: Order header

Status: header read-back confirmed by the user's live inspection on 2026-10-02.
The first live write test changed reference/modes but retained the old date.
The follow-up live test also rejected whole-text replacement despite verified
focus. Segmented keyboard entry now has regression coverage (191 tests passed,
2026-10-03); successful live date verification is still pending.
Based on the user's `code/evidence/private/mapping-order/` screenshot and UI tree.
The user's inspection returned PO000002, 2026-10-02, an empty reference, Gross,
and With VAT. The computer-use helper could not initialize in the assistant's
session, so the assistant has not performed the live write test.

## Mapped fields

All paths are scoped to one visible `Pane` named `New Order`.

| Field | How it is located | Handling |
| --- | --- | --- |
| Proposed number | Unnamed Edit immediately to the right of `No.` | Read only; no write recipe |
| Date | Unnamed Edit immediately to the right of `Date` | Verify selected segment, type numeric keys, blur to reference and verify retained ISO date |
| Customer reference | Edit named `Cust.Ref.` | Read/write source reference |
| Price mode | Unique unnamed ComboBox inside the Order pane | Read; draft selection is Net |
| VAT mode | ComboBox named `VAT` inside the Order pane | Read; draft selection is With VAT |

The `to_right_of` selector uses current accessible label/control bounds, not saved
pixel coordinates or numeric SWT IDs. It rejects duplicate labels, tied candidates,
and fields separated by another label. This prevents a missing number field from
accidentally resolving to the date field farther along the same row.

The dedicated profile is `code/config/order-header.partial.json`. It remains
`calibrated: false`. `order_header` is deliberately not named `order`: the full
workflow also needs addresses, lines and totals, which this small query cannot read.
The action draft includes no Save, no creation and no proposed-number replacement.
If an edit changes the pane title, lookup must stop; title behavior needs live checking.

## Read-only live check

Leave the blank New Order editor open, then use CMD:

```bat
cd /d "D:\TJM Task\code"
..\.venv\Scripts\fakturama-cash.exe inspect-order
```

This command reads only the five header fields. It does not switch tabs, maximize,
fill, save, call the model, or enable the live profile. Each successful observation
is saved separately under `code/evidence/private/order-header-inspection/`.
Compare the returned values with the visible editor. Gross is expected for the
blank Order in the original capture: inspection does not change it to Net.

## Controlled, unsaved header-fill check

Use a disposable test workspace and leave that same New Order open. Run in CMD:

```bat
..\.venv\Scripts\fakturama-cash.exe test-order-header --expected-number PO000002 --date 2026-07-14 --reference WEB-2026-0714-A17
```

The values above are explicit assignment test inputs, not an extraction fallback.
This command does not call the model or change production workflow behavior.

1. Validate the restricted mapping before connecting. Only the observed header
   paths and four known edits are allowed; no save, number edit or extra actions.
2. Activate/maximize Fakturama and save the initial header observation.
3. Require the expected proposed number, an empty reference, Gross and With VAT.
4. Find all four enabled destinations before attempting any edit.
5. Record write intent, fill date/reference, select Net/With VAT, then read back
   all five fields and compare with the expected values, including the number.
6. Save a unique evidence record and play the success/failure tone. No Save action
   is sent. Full profile calibration remains false.

Success returns `verified_unsaved_order_header`. Evidence is stored under
`code/evidence/private/order-header-test/<attempt-id>/`. If a write or read-back
fails, partial changes may remain. Inspect the editor and evidence; there is no
automatic retry or rollback. Do not save the test Order. A second run against a
filled reference intentionally stops rather than overwriting it.

## Selector icons: identified, not enabled

The capture shows an upper image control beside Addresses for existing contact
selection and another upper image control beside Items for product selection.
They are unnamed Image nodes; the nearby green-plus controls are different actions.
Do not use temporary numeric IDs or unverified icon clicks as production selectors.
These need live inspection/tooltip or dialog evidence before their behavior can be
calibrated. The current profile does not claim either selector mapping is complete.

The next requested evidence is the output of `test-order-header`. Once its live
read-back matches, continue with the debtor selector and then the product selector.

## Date-only repair after the first live test

The recorded failure showed the date stayed at 2026-10-02 while the reference,
Net mode and With VAT were correct. Inspection of the installed DocumentEditor
class confirmed it references Nebula CDateTime, not a plain date text box.
The installed pywinauto `set_edit_text` implementation calls UIA SetValue without
focusing. The upstream [CDateTime source](https://github.com/EclipseNebula/nebula/blob/master/widgets/cdatetime/org.eclipse.nebula.widgets.cdatetime/src/org/eclipse/nebula/widgets/cdatetime/CDateTime.java)
rejects replacement when no segment is active; its focus event activates a segment.
The initial focus-based hypothesis was insufficient: the second live test still
read the old date. Both failed attempts are now modeled in the tests; whole-value
assignment is no longer used for this control.

The date recipe now requires a `commit_path` pointing to the observed customer
reference field. It moves focus there and back to the date, then uses the widget's
documented [segment keyboard behavior](https://eclipse.dev/nebula/widgets/cdatetime/cdatetimeb2c1.html?page=operation):

- Read the English date text and accessible selection offsets to identify the
  current month/day/year segment. Unsupported formats/patterns stop before typing.
- Move between segments using bounded right-arrow navigation, checking selection
  after each move. Verify field focus and foreground window before/after each key.
- Set day 1 first when necessary, then year, month and final day. This avoids invalid
  intermediate dates such as February 31 or February 29 in a non-leap year.
- Type two digits (four for year); the widget commits and advances automatically.
  Verify each intermediate date and finally the retained date after leaving the field.

There is no Enter, Save, clipboard paste, automatic refocus after losing focus, or
whole-value SetValue. A failure stops before subsequent header edits. An intentional
intermediate date may remain after a partial failure; inspect it rather than retrying
blindly. These keyboard interactions still require live verification.

For the already partially filled unsaved PO000002, use CMD:

```bat
..\.venv\Scripts\fakturama-cash.exe test-order-header --expected-number PO000002 --date 2026-07-14 --reference WEB-2026-0714-A17 --date-only
```

The explicit date-only option requires the other four fields to match before
writing. It records new before/after evidence, runs only `fill_order_date`, and
checks all five fields afterward. This is not a generic retry/resume facility.
The usual test still requires an empty reference and initial Gross/With VAT modes.
The second failure's recorded initial state was empty reference/Gross; it stopped
before those fields were written. For that state, use the normal command without
`--date-only`, after verifying the visible header. Do not change fields simply to
force the date-only guard to pass.
