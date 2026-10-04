# Live UIA integration — 2026-10-04

Branch: Development. Workspace: `C:\Users\mmsss\Documents\Fakturama`,
English UI, Germany/EUR, observed desktop scale. The user authorized clearly
labelled synthetic data and discarding the old mixed-currency draft.

PO000003 → INV000002 completed a staged development integration. Its reference
is CODEX-UIA-FULL-20261004-003, Order date Jul14 2026, Invoice/service dates Oct4
2026. Four lines preserved source order, repeated SKUs, quantities, net prices,
19% VAT and 10%/0%/5%/0% discounts. Saved net619.00, VAT117.61, totalEUR736.61.
Invoice persisted paid with Bank Transfer, Jul18 date and full value736.61.
Both source recipient snapshots persisted and the exact Invoice was closed and
reopened from Documents before the final full-field comparison.

Saved missing masters include CUST000003, Bank Transfer, VAT19%,
CODEX-LIVE-CHAIR-003 and CODEX-LIVE-MAT-003. Contact/address roles and master
definitions were read independently before Save; selectors confirmed saved IDs.
Existing PO000002 → INV000001 previously passed payment/reopen at EUR42.84.

Implementation corrections from the live integration:

- Products have six raw TSV cells; Debtors nine. Literal fixture tabs had caused
  misleading extra columns and were repaired. Product matching now reads the
  blank-filter complete catalogue and requires one exact SKU.
- Debtor single-selection Copy needs a first-row selection before the bounded
  walk. Unselected or empty Copy can raise Fakturama exceptions.
- A fourth item required scrolling the outer editor. Header checks cover actual
  data columns, excluding the unused tail changed by a scrollbar.
- Native focus is verified before keys. SWT UIA SetFocus sometimes leaves focus
  in Documents; a bounded native focus fallback now handles grid copy, text blur
  and closing a clean selected editor.
- New Delivery tabs receive text binding only on initial Order Save. Save with
  Invoice selected, verify the confirmed saved document, then reapply addresses
  and make one distinct update if binding changed their source snapshots.

Private staged evidence is under
`code/evidence/private/live-smoke/51022fd06feb81056aa216fbe6654d11fda260b9103e57f5f295caeb9a0ecb7f/`.
It records development reconciliation and uncertain stages; it must not be
presented as one uninterrupted production run. A separate clean production Workflow smoke completed without intervention:
**PO000004 → INV000003**, reference CODEX-UIA-FULL-20261004-004, two items,
net570.00/VAT108.30/totalEUR678.30. The workflow used existing masters, preserved
the Jul14 Order date and proposed Oct4 Invoice/service dates, and persisted paid
Bank Transfer with Jul18 date and full value678.30. Both recipient snapshots and
all Invoice fields passed after exact-number reopening. Order remained open.
Its distinct address update was triggered and verified after initial Save.

Private clean-run checkpoint: `code/evidence/private/live-smoke/7e106fdde9a57cf665dbe52e0841e458d6aa516ccb1a84007b9b0f8704ee5f5a/checkpoint.json`;
progress log: `code/evidence/private/clean-smoke.log`. Final status/stage are
`complete`; no action is pending or uncertain. 286 automated tests passed in
12.83s, profile completeness passed, and `git diff --check` passed. The user
requested committing the implementation on Development; no push requested.

Image extraction passed separately with a real local model and manual source
comparison. These UI runs start from validated synthetic JSON, so they do not
claim a fresh image-command end-to-end demonstration. Invoice's GUI has no source
Order number: exact scoped follow-up, Order date and copied values provide the
relationship evidence, as disclosed in the journal.
