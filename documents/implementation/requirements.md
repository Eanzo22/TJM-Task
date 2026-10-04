# Requirement checklist

Updated 2026-10-04, Development. UIA implementation is present. Live component
verification and a clean integrated run are recorded separately; simulated tests
do not establish live correctness. See the latest handoff for run status.

| Requirement | Implementation and observed verification |
| --- | --- |
| Read the supplied order image | Three real local vision passes plus Windows OCR; combined extraction passed and was manually compared with the source |
| Required fields, dates and arithmetic | Strict models, Decimal reconciliation; invalid or uncertain values stop |
| Open Order first and preserve number | Live header and segmented date entry verified |
| Exact Debtor/SKU matching | Full copied catalogue, bounded debtor row walk, ambiguity stops, guarded activation |
| Missing Debtor and separate delivery | Live CUST000003 created; contact, address roles, Net, zero discount and payment checked before Save |
| Missing payment method | Live Bank Transfer created and inspected; resolve before fresh Debtor so its dropdown refreshes |
| Missing VAT/Product | Live VAT 19%, Chair and Mat created; proposed values and VAT definition checked |
| Item sequence, quantity/net/VAT/discount | Four ordered live lines saved in PO000003, net 619.00, VAT 117.61, total EUR736.61 |
| Both document recipient snapshots | Source text entered and independently read; confirmed first-Save rebinding handled by a distinct address update |
| Save Order and verify Documents | PO000002 and PO000003 verified with preserved date/reference/no and total |
| Linked Invoice from saved Order | Scoped follow-up, copied fields and Order date checked; PO000002 → INV000001 saved/reopened |
| Preserve Invoice number/date/service date | Captured from proposed Invoice and required unchanged |
| Paid/source payment date/full value | INV000003 persisted paid with Jul18 date and EUR678.30 after exact-number reopen |
| Original Order open, no further types | Final Order/Invoice rows checked; action set creates no delivery note or other document type |
| Unknown mutation outcome | Write-ahead journal, exclusive lock, no automatic repeat; accepted-write timeout tests |
| Duplicate protection | Image/semantic fingerprints and persisted customer or recipient/reference candidates |
| Evidence and read-only reconciliation | Private source/model/capture/checkpoint evidence; reconcile inspects identifiers, does not resume |
| Clean production Workflow | PO000004 → INV000003, reference CODEX-UIA-FULL-20261004-004, completed without intervention; both addresses and all copied/payment fields persisted |
| Automated verification | 286 tests passed; live GUI evidence has separate scope |
| Setup and recovery | Code README, UI profile, latest handoff and live integration record |

Remaining limits: nonzero document discount/shipping tax allocation, arbitrary
source layouts, mixed-rate rounding edge cases and uncalibrated internal grid
scrolling stop or need further work. Current mappings target the observed
English/EUR workspace and display scale. The GUI exposes no source Order number
on Invoice; relationship evidence is the exact scoped follow-up, Order date and
all copied values. The journal records that limitation explicitly.

The first Order Save and a conditional address update are intentional distinct
mutations. This deviates from the single-Save plan because Fakturama initializes
a new Delivery tab's text binding during the first Save.
