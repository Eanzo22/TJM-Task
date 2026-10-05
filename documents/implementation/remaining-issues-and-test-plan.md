# Remaining work and focused verification

Updated 5 October 2026, Development. The current image flow saved PO000011 and INV000005, and full persisted verification passed read-only after correcting final reopen calibration. The transaction needs no rerun. See [verification](verification.md).

## Next verification priorities

1. Use a new authorized test transaction for one clean image command with the current mappings. Do not recreate the already verified transaction just to obtain a clean log.
2. Exercise the revised missing-Debtor/missing-payment branch with the Debtor kept open. Confirm dropdown refresh, one Debtor Save, and exact reselection. A stale dropdown must stop before Save.
3. Exercise current missing-VAT creation, UNPAID persistence, and interruption after an uncertain write. Reconcile the saved state read-only before deciding on another transaction.
4. Run guided calibration on another device, confirm copied counts and reviewed geometry, and verify a transaction there. Follow the [new-machine walkthrough](calibration.md); existing flags do not establish portability.

These require controlled live data and should follow implementation work as needed; repeating the whole regression suite without a new change adds no evidence about the desktop.

## Scope limits

| Area | Current boundary |
| --- | --- |
| Image extraction | Assignment table/address layout and EUR; arbitrary layouts need new detection/schema work |
| Arithmetic | Nonzero overall discount/shipping stop; mixed-rate/fractional rounding needs additional live evaluation |
| Tables | Reviewed English labels/columns and local geometry; uncalibrated internal scrolling or off-screen activation stops |
| Empty workspace calibration | Requires at least one authorized populated row in each measured view; no automatic fixture creation |
| Address binding | Saved mismatches stop before follow-up; no second Order repair Save |
| Invoice relationship | GUI lacks source Order No; scoped follow-up, Order Date and copied fields provide narrower evidence |
| Recovery | Checkpoint review and read-only reconcile; no automatic resume or transaction deduplication |
| Concurrency | One run-root lock; no cross-directory/multi-machine coordination |

## Three additional hours

- **First hour:** validate device calibration and a clean current transaction on a second device, recording observed mapping differences.
- **Second hour:** improve read-only reconciliation to distinguish saved, unsaved, and uncertain stages and give concrete operator next steps without replaying uncertain writes.
- **Final hour:** improve vision failure/cancellation feedback, focused regressions for observed failures, and a short successful setup/run demonstration.

CPU-only inference already exists for the observed local GPU failure; use the [CMD setup instructions](../../code/README.md#cpu-only-fallback) rather than changing validation or guessing extracted values.
