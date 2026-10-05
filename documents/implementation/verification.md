# Verification and evidence

Updated 5 October 2026, Development. This records observed results; configuration checks and simulated tests are not described as live workflow completion.

## Latest image-driven transaction

The actual source image was processed through three vision sections, then the UI workflow created **Order PO000011 → Invoice INV000005**. Existing Debtor and first Product were selected. Missing MAT-DESK-02 was created after VAT inspection, saved once, and reselected. Both source lines, addresses, and totals passed. The Order and Invoice each received one Save and passed their Documents row checks.

| Verified field | Persisted value |
| --- | --- |
| Order date | 14 July 2026 |
| Invoice and service dates | Proposed 5 October 2026, preserved |
| Net / VAT / Total | EUR 570.00 / 108.30 / 678.30 |
| Payment | Bank Transfer, paid |
| Paid date / value | 18 July 2026 / EUR 678.30 |
| Source Order | Open, same reference and total |

The command stopped only at final Invoice reopening: a Documents header variant caused the calibrated row-activation guard to reject the visible selected row. After adding that exact reviewed variant, a separate read-only verification reopened INV000005 and compared all source/copy/payment fields. No New/Save action or business repair was performed. Its result is `verified_saved_workflow`; the original checkpoint remains `review_required`, unchanged. A fresh uninterrupted image run with the corrected mapping has not been claimed.

Private paths relative to `code/`:

```text
runs/dccd74e337dfe5a5677366c004c98742d18cdb2444c5fdc90aba38ecc239ba67/
  extractions/7778d8aff06c48d68ba25faa2b31f5d9/
  workflows/ec864802c11943df969dee5065294eed/
    checkpoint.json
    post-failure-verification.json
    post-failure-verified.png
    post-failure-verified-uia.json
```

The local one-off verification script is `evidence/private/verify-existing-invoice.py`; it is not a public resume command. Evidence and source images are ignored/private and absent in a clean clone. Review customer details before sharing captures.

## Earlier development evidence

- PO000004 → INV000003 completed a synthetic JSON UI smoke at EUR 678.30 using older mappings. It included a second address update that the current single-Save implementation has removed. It is not proof of the current image command.
- PO000003 → INV000002 was a staged four-line development integration at EUR 736.61, covering repeated SKUs, discounts, and outer-editor scrolling. It was not one uninterrupted production run.
- Fresh Debtor creation and payment/VAT creation were exercised historically. The current payment-while-Debtor-open branch, missing VAT branch, UNPAID path, and second-device calibration still need targeted current live verification.
- Live Preferences inspection confirmed the automatic single-result Product setting could be disabled and remained off after reopening Preferences.

## Automated and offline checks

On 5 October 2026, **414 tests passed**. These use synthetic data, mocked transports, and fake UI controls; they make no live business writes. Coverage includes schema/arithmetic, CPU request options and HTTP diagnostics, exact matching, current workflow sequence, journals, guarded search/row selection, clipboard retries, header/viewport checks, sounds, and guided calibration.

The pytest run reported a cache permission warning from the inherited local `.pytest_cache`; the tests passed. The documented CMD test command uses its own local cache/temp paths. Profile completeness checks are offline and do not certify geometry, copy scope, or transaction correctness.

The current live profile passed the offline completeness check, `pip check` reported no broken requirements, and all local links in the seven retained Markdown guides resolved. Git whitespace checks passed. No live business run was started for this documentation and commit pass.

For current verification priorities, see [remaining work](remaining-issues-and-test-plan.md). Setup, commands, and recovery are in [code README](../../code/README.md).
