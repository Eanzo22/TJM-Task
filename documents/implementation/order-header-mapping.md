# First mapping group: Order header

Status: header read-back confirmed by the user's live inspection on 2026-10-02;
controlled write command implemented, live write verification still pending.
Based on the user's `code/evidence/private/mapping-order/` screenshot and UI tree.
The user's inspection returned PO000002, 2026-10-02, an empty reference, Gross,
and With VAT. The computer-use helper could not initialize in the assistant's
session, so the assistant has not performed the live write test.

## Mapped fields

All paths are scoped to one visible `Pane` named `New Order`.

| Field | How it is located | Handling |
| --- | --- | --- |
| Proposed number | Unnamed Edit immediately to the right of `No.` | Read only; no write recipe |
| Date | Unnamed Edit immediately to the right of `Date` | Read as ISO; draft write uses the observed English named-month format |
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
