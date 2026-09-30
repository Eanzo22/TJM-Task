# Requirement checklist

Status labels deliberately distinguish simulated tests from live behavior. No business step has been live-verified end to end.

| Requirement / assignment step | Implementation | Verification status |
|---|---|---|
| Read order image through a real extraction path | `extraction.py` vision HTTP request + schema | Implemented but unverified with a real model; request/response tested with mocks |
| Local OCR text and word bounds | `windows_ocr.py`, CLI `ocr` | Live verified on supplied image; output contains errors, not accepted as structured input |
| Required customer/addresses/items/payment/totals | `models.py` | Tested with mocks/synthetic fixtures |
| Decimal, discounts, VAT, source reconciliation | `normalize.py`, `OrderInput.reconcile` | Tested with synthetic fixtures; live rounding edge cases unverified |
| Nonzero overall discount/shipping | Validation review stop | Unfinished tax allocation; zero/absent supported |
| Desktop accessibility and screenshot diagnostics | `UIAAdapter.capture`, CLI `diagnose` | Live verified; private evidence captured |
| Scoped unique controls, stable reads, bounded waits | `ui.py` | Implemented but live action mappings unverified; wait logic tested |
| Custom SWT grid OCR/visual interaction | Not implemented | Unfinished; observed grid exposes no DataItems |
| Open Order first, preserve number, fill header | `Workflow.run` | Tested with mocks; live profile unfinished |
| Exact Debtor search, ambiguity stop | `resolve_debtor`, `exact_match` | Tested with mocks |
| New Debtor; preserve ID; addresses/alias/Net/zero discount | `resolve_debtor` | Tested with mocks; actual address-role editing unfinished |
| 2.10.4 / missing payment terms | `payment_definition`, `resolve_debtor` | Tested with mocks, including conflicting terms; live selection unfinished |
| Payment dropdown refresh behavior | Resolve payment before fresh Debtor | Based on user observation; workaround tested with mocks; explicit sequence deviation |
| Exact SKU, VAT definition, Product gross master price | `resolve_line`, `Line.gross_master` | Tested with mocks; live fields/mapping unfinished |
| Every item in original order; line discounts | `resolve_line` and verification | Tested with mocks on multiple rows |
| Both populated addresses checked | `resolve_debtor`, `expected_order` | Tested with mocks including wrong-delivery failure |
| Save Order once and verify Documents row | `Workflow.run`, `document_row` | Tested with mocks, including accepted-write timeout |
| Create linked Invoice through Order follow-up | `Workflow.run` | Tested with mocks, including wrong-link failure; live menu unfinished |
| Preserve Invoice number/date/service date | `Workflow.run` | Tested with mocks |
| PAID date/full amount vs unpaid | `Payment`, `Workflow.run` | Tested with mocks; real persisted verification unfinished |
| Original Order remains open; no extra document types | Final document checks; bounded action set | Tested with mocks |
| Mutation uncertainty, checkpoints, no blind retry | `Journal`, workflow | Tested with mocks at save/product/select/follow-up interruption points |
| Same image and normalized-input rerun protection | `guard_prior_run`, persisted candidate check | Tested with mocks; persisted search needs live grid reader |
| Read-only reconciliation command | CLI `reconcile` | Implemented but unverified live; inspection only, no automatic resume |
| Raw/normalized evidence, logs and transition captures | `extraction.py`, `state.py`, workflow | Tested with mocks; real diagnostic captures available |
| Real end-to-end demonstration | None | Unfinished; existing user records left unchanged |
| Setup, CLI, limitations, recovery, +3 hours answer | `README.md`, this checklist, `ui-profile.md` | Provided |

The source image exists. The blockers are not missing source data: they are unconfigured structured extraction, incomplete UI mappings, inaccessible custom tables, and an existing live workspace containing related records that must not be overwritten or duplicated.
