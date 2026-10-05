# Fakturama implementation handoff

Updated 5 October 2026. Work on **Development**, not master. The latest implementation and setup are in [code README](../code/README.md); the assignment is the specification. The README now contains the current flowchart and code boundaries. The sample `documents/Live_Task.png` is tracked. Operator calibration steps are in [the walkthrough](implementation/calibration.md).

## Current state

The actual image workflow saved **PO000011 → INV000005**, Net EUR 570.00, VAT EUR 108.30, Total EUR 678.30, Bank Transfer paid on 18 July 2026. It selected existing Debtor/Product data, created missing MAT-DESK-02 after VAT inspection, and saved each document once. It stopped only at final Invoice reopening because Documents used a different reviewed header allocation.

The mapping was corrected and a separate read-only check reopened the saved Invoice and verified full fields/payment. Result: `verified_saved_workflow`. No new business records, extra Save, or discarded records were required. The original failed checkpoint remains `review_required`; a fresh uninterrupted run after the correction has not been claimed. **Do not rerun this transaction.**

[Verification](implementation/verification.md) records the private evidence paths and distinguishes earlier synthetic smoke tests. The current automated suite has **414 passing tests**; it performs no live UI writes.

## Current implementation decisions

- Extract items, addresses, and other source fields in separate vision passes; reconcile before UI writes. The observed GPU token-repeat HTTP 500 passed with `FAKTURAMA_VISION_CPU_ONLY=1` (`num_gpu=0`). Set variables in the same CMD session; `.env` is not loaded.
- Start a fresh New Order for every explicit `run`. Image hashes group evidence only; no prior-checkpoint/customer/reference duplicate gate and no automatic resume.
- Use exact Order-selector results and explicit OK. Preferences > Documents automatic single-result acceptance is disabled/applied/verified before Order creation when enabled.
- Keep Order open while resolving masters. Force fresh Debtors with New > New Debtor; resolve unavailable payment terms while Debtor remains open. Force fresh Products through the Products list after verifying VAT. Blank-form checks prevent overwriting selected records.
- Verify shared Debtor Company/contact headings and each address role's postal fields independently. Source block labels stay in input evidence; billing/delivery locations need not match each other.
- Save once, journal intent first, and stop on uncertainty. There is no second address repair Save. `reconcile` reads persisted rows, not full editor verification or resume.
- Guard keyboard focus, stable search text, complete copied rows, and row identity before acceptance. Retry only clipboard access on contention, never Save/OK. Accept wider unused item canvas only with identical data-header pixels and reviewed Documents header variants only.
- Local `calibrate` measures seven empty/populated table views and copy counts. The builder's `--calibrated` flag does not measure a new device. Private local profiles/evidence remain ignored.

## Continuing work

Read [remaining work](implementation/remaining-issues-and-test-plan.md) before another live transaction. Priority is a clean new image transaction, current missing-Debtor/payment and UNPAID branches, missing VAT, and second-device calibration. Do not claim these from simulated tests or older mappings.

Use Windows CMD instructions, keep implementation straightforward, and avoid excessive repeated tests. Live runs require an unlocked desktop and no concurrent automation/operator input. Resolve unsaved drafts explicitly; never delete checkpoints to force a rerun. Commit on Development when requested; push only when requested.

Technical details are consolidated in [UI profile](implementation/ui-profile.md) and [requirement coverage](implementation/requirements.md). Superseded debugging diaries have been removed from the working documentation; Git history retains the earlier tracked versions.
