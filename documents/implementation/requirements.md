# Requirement coverage

Updated 5 October 2026 on Development. The assignment remains the specification. Implementation checks and simulated tests are distinguished from observed live results below.

| Requirement | Current implementation and evidence |
| --- | --- |
| Extract the supplied image | Three vision passes plus Windows OCR; latest real image extraction reconciled two items and EUR 678.30 |
| Validate before business writes | Strict fields/date/Decimal rules, OCR source consistency, line/VAT/total reconciliation; errors stop |
| Open Order first and retain No | New Order after preflight, source date/reference, Net/With VAT; latest PO000011 verified |
| Debtor existence through Order selector | Exact Company/first/last/ZIP/city and explicit OK; ambiguous/conflicting results stop |
| Missing Debtor and payment | Fresh blank Debtor, proposed ID, contact/role fields; conditional terms inspection/creation while Debtor stays open, Save once and reselect. Current revised missing-payment branch still needs an isolated live check |
| Address roles | Shared Company/contact heading with independently verified source postal fields. No requirement that billing and delivery locations match |
| Product existence through Order selector | Exact SKU, verified row and OK; auto-accept disabled before Order. Existing and newly saved Products selected in the latest run |
| VAT before missing Product | Exact VAT name/rate/code S; create only if absent. Latest missing MAT-DESK-02 was created after VAT inspection, saved once and reselected |
| Product master values | Source SKU/description, undiscounted gross price, verified VAT, zero cost/stock; blank fresh form checked |
| Complete every source line | Quantity/net/VAT/discount/description and line net verified in source order; latest two lines passed |
| Complete and Save Order once | Zero overall discount/shipping, source totals, one Save and exact Documents row check. PO000011 passed without a repair Save |
| Linked Invoice | Scoped saved-Order follow-up and copied values; toolbar Invoice is unused |
| Preserve proposed Invoice fields | No/date/service date retained; latest proposed dates 5 October 2026 passed |
| Payment and final documents | INV000005 persisted Bank Transfer, paid 18 July 2026, EUR 678.30. Order remained open; full Invoice reopened and checked read-only after mapping correction |
| Stop after Invoice verification | No Delivery, Correction, or Dunning creation actions |
| UIA grounding | Scoped controls, reviewed relative table geometry, copy completeness and layout guards; other devices require calibration |
| Uncertain action handling | Write-ahead per-attempt journal, run lock, no automatic replay; read-only reconcile, no automatic resume |
| Setup and reporting | CMD setup, explicit new-machine calibration steps, CPU-only option, progress and success/failure sounds documented |

Latest automated check: **414 tests passed** on 5 October 2026. Tests cover simulated matching, creation, payment, mutation failures, search focus, clipboard contention, layout guards, extraction diagnostics, and calibration. They do not establish live success for every conditional branch.

Adapted creation controls preserve the specified sequence: New > New Debtor and the Products list's force-new button replace Navigation View shortcuts that can reopen existing records. Invoice linkage has no directly visible source-Order number; evidence is the scoped follow-up plus copied values. See [verification](verification.md) and [remaining work](remaining-issues-and-test-plan.md) for limits.
