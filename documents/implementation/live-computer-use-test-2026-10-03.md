# Fakturama live Computer Use header test

Date: 2026-10-03 (Africa/Cairo).
Checkout: `D:\TJM Task\Implementation\TJM-Task`.
Branch: **Development**, tracking `origin/Development`; not master.
Inspected HEAD: `02550d089577616f5a6d3edb0f137a4b1646e986`.

## Scope and result

The user requested a live Fakturama test through Computer Use. The installed
computer-use skill's `@oai/sky` helper initialized and targeted the running
Fakturama window. The test used the existing blank New Order editor. No Save,
Order creation, Invoice creation, payment, extraction, commit or push was performed.

| Header field | Before | Verified after |
| --- | --- | --- |
| Application-proposed number | PO000001 | PO000001 |
| Date | Oct 3, 2026 | Jul 14, 2026 |
| Customer reference | Empty | WEB-2026-0714-A17 |
| Price mode | Gross | Net |
| VAT mode | With VAT | With VAT |

The editor remains open with unsaved edits. Final values were read from the
accessibility tree and checked against the visible application. These are explicit
assignment calibration inputs, not values extracted in this test.

## Date interaction observed live

1. Focused the empty customer reference, then the date field.
2. Visually confirmed the selected year segment. Right-arrow navigation selected
   month, then day, without changing the date.
3. Sent numeric key events `0`, `1` to set safe day 1; the widget advanced to year.
4. Preserved 2026 and navigated right to month. Sent `0`, `7`; the widget committed
   July and advanced to day.
5. Sent `1`, `4`, then clicked the reference field. The date remained Jul 14, 2026
   after losing focus.
6. Typed the reference and selected the visibly observed Net option. A subsequent
   accessibility observation confirmed all five header values.

Each input was followed by a fresh observation. Numeric input used `sky.press_key`,
not whole-value replacement or clipboard paste. The unchanged VAT value was read
back; this test did not exercise changing the VAT dropdown.

## Limits and observations for continuation

- This verifies live segmented keyboard interaction through Computer Use. It did
  not execute `test-order-header`, `date_entry.enter_date`, or pywinauto's
  `selection_indices()` and foreground guards. Those remain unverified live.
- Computer Use did not return `selected_text` for this date control. Segment
  selection was inspected in screenshots; that does not establish whether the
  project's selection-offset API works.
- Some immediate accessibility snapshots retained an earlier date, reference or
  dropdown value while the screenshot already showed the edit. Later observations
  agreed, including the date after blur. Read-back timing needs live attention.
- The tab became `*New Order`; the accessibility pane remained `New Order` during
  this test. No production selector or calibration flag was changed.
- A capture before activation showed an occluding application. After activating
  Fakturama, screenshots showed its actual editor. Inspect captured pixels before
  relying on evidence, even when the accessibility tree belongs to Fakturama.
- Totals displayed `$0.00` in the current workspace. EUR configuration was not
  checked or changed; verify it before testing the assignment's monetary workflow.
- No debtor/product selection, line totals, persistence, linkage or paid-state
  behavior was tested. Full end-to-end automation remains incomplete.

Screenshots and accessibility observations were returned in this local chat's
Computer Use tool results. This report summarizes observations; it is not a
project-generated evidence bundle or a CLI success result.

## Continuation: selectors, currency and regression suite

The existing-contact icon beside Addresses opened `Select the address`. Its
search accepted `Northstar`, verified in the accessible Edit value and screenshot.
The grid looked empty both before and after search. Cancel returned to the same
unsaved Order without filling its invoice address.

After maximizing Fakturama, the upper selector icon beside Items opened
`Select a product`. Its search accepted `CHR-ERG-01`, verified in the accessible
Edit value and screenshot. This grid also looked empty. Cancel returned without
inserting an item. All five header values remained as listed above.

Neither selector exposed accessible result rows, a complete count, or an explicit
zero-result indicator. Therefore neither observation may be used by the program
to decide that a master record must be created. See
[selector calibration](selector-calibration.md) for observed columns and remaining
positive/duplicate/scroll tests.

File > Preferences > General showed Currency locale `Afghanistan`, with example
`$-1,234.57`. This establishes the displayed configuration, not an ISO currency
code or proof of USD. Preferences was cancelled without applying changes. EUR
must be configured and verified before a monetary transaction test.

Some modal accessibility-index clicks did not reach their intended control. Fresh
screenshots and visibly grounded coordinate clicks completed search/cancellation.
These coordinates were used only for supervised Computer Use and were not added
to the production mappings.

Added 12 synthetic regressions covering inaccessible results, an unconfirmed
empty state, incomplete row counts, missing/ambiguous cells, preservation of
duplicates, and workflow stops before missing-master creation or document save.
The full suite passed **203 tests in 10.42 seconds** using the project's Python
3.12 interpreter. No test operated the live desktop or vision model.

The local `.venv` launcher failed inside the assistant's sandbox but succeeded
when run outside it. A subsequent test attempt hit permissions on a temporary
directory previously created by the sandbox. A fresh temporary root and disabled
pytest cache resolved that execution issue; no ACLs were changed or old evidence
deleted. Reproducible Windows CMD commands (choose a fresh run directory):

```bat
cd /d "D:\TJM Task\Implementation\TJM-Task\code"
mkdir .pytest_runs\local-verification-01
set "PYTEST_DEBUG_TEMPROOT=%CD%\.pytest_runs\local-verification-01"
..\.venv\Scripts\python.exe -m pytest -q -x --tb=short -p no:cacheprovider
```

The project's live date-only test remains pending. The installed Computer Use
skill's guidance requires: "Use only the Computer Use JS APIs for Windows app
automation." This session used that API for desktop actions and did not launch
the pywinauto CLI to operate Fakturama. The observed current header supports this
next supervised user-run CMD check after a fresh `inspect-order`:

```bat
cd /d "D:\TJM Task\Implementation\TJM-Task\code"
..\.venv\Scripts\python.exe -m fakturama_cash.cli inspect-order
..\.venv\Scripts\python.exe -m fakturama_cash.cli test-order-header --expected-number PO000001 --date 2026-07-14 --reference WEB-2026-0714-A17 --date-only
```

Run the second command only if inspection still matches the intended unsaved
Order number/reference and Net/With VAT modes. The date writer intentionally
passes through day 1, even when the final target date already matches. Failure
can therefore leave an intermediate unsaved date; inspect evidence before any
further action. Expected success is `verified_unsaved_order_header`.

## Authorized EUR and saved-master continuation

The user explicitly confirmed that `C:\Users\mmsss\Documents\Fakturama` is a
test workspace and approved EUR configuration and labelled test debtor/product
records. File > Preferences > General > Currency locale was changed to Germany,
showing `-1.234,57 €`, then Apply and Close was clicked once. A read-only check of
`C:\Users\mmsss\.fakturama2\.metadata\.plugins\org.eclipse.core.runtime\.settings\com.sebulli.fakturama.rcp.prefs`
later confirmed `PREFERENCE_CURRENCY_LOCALE=de/DE`. New product and Order editors
displayed euro amounts; the older Order retained its previous formatting.

### Saved records and persistence findings

| Record | Observed saved state |
| --- | --- |
| Product | `CODEX-UI-TEST-001`, name `CODEX TEST - Selector Calibration`, EUR 10.00, Free of Tax |
| Debtor | Proposed ID `CUST000001`, Test Buyer, Test Street 1, 00000 Test City; default country United States retained |

Each record was saved once through the current-editor Save control. Its dirty
marker disappeared, and its row subsequently appeared in the selector. These
are synthetic fixtures, not assignment masters.

Direct value assignment of `10,00` to product price reverted to `0`. With the
price focused, Ctrl+A, literal `10`, then Tab retained `10,00 €`. Its selector
row later confirmed that price. This test does not verify the project's monetary
writer or prove that UIA value assignment commits a currency control's model.

Company was assigned `CODEX TEST - Selector Calibration` and visible in the
debtor form before save, but the saved selector's Company cell was blank and
the inserted address omitted it. Product Description similarly appeared in the
editor but blank in the selector. These fields need keyboard repair and an
independent read-back; do not count visual form assignment as persistence.

### Positive selectors and failed insertion

A separate unsaved Order was opened and labelled `CODEX-UI-CALIBRATION-ONLY`.
It proposed `PO000001`, the same number as the original unsaved reference test.
Its date is 2026-10-03, Gross, With VAT. The original draft remains separate with
reference `WEB-2026-0714-A17`, date 2026-07-14, Net, With VAT. Scope by reference
and editor, not proposed number alone.

Searching `CUST000001` visibly returned Test Buyer / 00000 / Test City. A
double-click populated `Test Buyer Test Street 1 00000 Test City` in the new
draft's invoice-address Edit. Searching `CODEX-UI-TEST-001` visibly returned the
saved product at `10,00 €`, Tax-free (0.0%). Both populated selectors still
exposed no accessible row cells or complete count. No duplicate or vertical
traversal test was performed.

Double-clicking the product row raised an Internal Error:

```text
org.eclipse.e4.core.di.InjectionException:
javax.money.MonetaryException: Currency mismatch: EUR/USD
```

Read-only inspection of `C:\Users\mmsss\.fakturama2\.metadata\.log` confirmed
the entry at `2026-10-03 19:56:18.696` (log timestamp; timezone unspecified), with:

```text
MoneyUtils.checkAmountParameter(MoneyUtils.java:156)
Money.subtract(Money.java:538)
DocumentSummaryCalculator.calculate(DocumentSummaryCalculator.java:345)
DocumentSummaryManager.calculate(DocumentSummaryManager.java:53)
DocumentEditor.calculate(DocumentEditor.java:1490)
DocumentEditor.addItemsToItemList(DocumentEditor.java:3337)
DocumentEditor.handleDialogSelection(DocumentEditor.java:3241)
```

The draft displayed EUR 10.00 total gross/total and EUR 0.00 VAT after the error.
That is incomplete state, not a passed totals or insertion test. No retry,
Order save, Invoice creation, payment change, deletion or database edit followed.
The error dialog was not reliably dismissible through Computer Use; Return and
Escape produced captures without it, but it appeared again when attempting to
switch tabs. The helper did not enumerate a separately targetable error window.
The user was asked to dismiss it manually and leave both unsaved drafts open.

Next: restore normal UI interaction, repair/read back fixture fields, and resolve
the mixed-currency calculator state before a fresh insertion attempt. Cached
currency values surviving the locale change are a possible cause; an app restart
is a candidate recovery, **not a confirmed fix**. First agree on preserving or
discarding both unsaved drafts. Keep all profiles uncalibrated and the financial
workflow blocked until reliable selection, totals and persistence are verified.

The existing 203-test result remains the latest automated run. These new live
findings changed documentation only; no production runtime code or UI profile
was modified and no new claim about end-to-end success is made.

## User recovery and independent persistence verification

The user reported clearing the error by leaving the tab and returning. The next
observation showed the calibration tab named `PO000001`, Save disabled, and the
follow-up actions enabled. The assistant did not perform this Order save.

The clean calibration tab was closed and its record reopened by double-clicking
the Documents row. Read-back verified `PO000001`, `CODEX-UI-CALIBRATION-ONLY`,
2026-10-03, Gross/With VAT, Test Buyer address, one unit at EUR 10.00, zero VAT,
shipping and discount, and total EUR 10.00. No error dialog appeared during these
steps. This establishes manual persistence/read-back for this synthetic Order;
it does not retroactively make the earlier insertion error a passing test.

The older unsaved `WEB-2026-0714-A17` draft now visibly contains the calibration
product row at EUR 10.00 while its totals remain USD zero. Its proposed number
is also `PO000001`. The assistant neither saved nor removed this draft. The
exact cause of its changed items is unproven; investigate event/editor scoping
and do not infer that switching tabs fixed the underlying currency issue.

The saved debtor's Company and product's Description were confirmed blank,
repaired with focused literal keyboard text followed by Tab, and saved separately.
Each master was closed and reopened from its list. The full Company and Description
values survived, along with the product's EUR 10.00 price. This confirms a working
manual repair sequence, not the production adapter's write strategy.

Next: resolve the unsaved older draft, then test follow-up Invoice creation from
the saved calibration Order and verify source linkage, identifiers, address,
lines, EUR totals and persistence. The saved Order still contains its original
address and blank line description; later master edits were not applied to it.
Do not save the older mixed-currency draft or discard it without user approval.
No Invoice or payment was created in this continuation. No automated tests were
rerun because only live fixture data and documentation changed.
