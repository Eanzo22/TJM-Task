# UI mapping and calibration contract

Current implementation on Development, 5 October 2026. For operator steps, use the [new-machine calibration walkthrough](calibration.md). This page explains the adapter boundaries and mappings.

## Profiles

- `code/config/*.partial.json` contains reviewed component mappings.
- `scripts/build_live_profile.py` combines them into `config/live-profile.json`, uncalibrated by default. Its `--calibrated` flag asserts prior review; it does not measure a device.
- The tracked composed profile was measured on the original English/EUR 1920×1080 setup. `calibrate` produces ignored `live-local.json` with local table measurements after all seven views pass.
- Profiles supply the window selector, action/query mappings, calibration state, and bounded timeout. The current profile uses 120 seconds for UI observations. `check-profile` checks completeness offline, not live correctness.

## Discovery and writes

Scoped UIA paths must resolve to one control. Labels and current bounds locate unnamed controls without fixed desktop coordinates. Controls are reacquired after navigation; ambiguity stops immediately. Preflight activates/maximizes one Fakturama window and rejects dirty editor tabs without saving or closing them.

The workflow owns business decisions and verification. The adapter executes profile recipes and returns actual observed values. Source expectations must not be substituted into observations. The journal stores mutation intent before actions; uncertain Create/Save/selection/payment writes are not replayed.

`type_text` commits through a separate control and verifies retained text. Dates use numeric segments and post-blur read-back. Product `type_search` keeps focus in Search, sends no Enter, and never reopens or accepts the selector.

## Custom tables

The observed SWT grids lack usable accessible data rows. Clipboard reads check foreground focus, freshness/ownership, column widths, and complete copied results. Blank/stale Copy or missing accessible children do not establish an empty list. Reviewed empty fingerprints avoid Copy on genuinely empty grids.

Products expose six raw columns; Debtor results expose nine and can require a bounded row walk. Before accepting a match, the adapter rechecks table identity/content/order and verifies the positioned row by Copy. Order selectors confirm through their scoped OK; Documents activation uses reviewed relative row geometry. Malformed data, changed headers, or off-screen activation stops.

Clipboard access-denied retries are bounded to three seconds and repeat the read only. Ctrl+C, OK, and Save are not repeated. Item editing checks source SKU/index, viewport, header pixels, and measured columns. Wider unused right-hand space is accepted only with identical calibrated data headers; narrower canvases and uncalibrated internal scrolling stop. Documents permit only explicitly reviewed header variants.

## Master records and addresses

Automatic single-result Product acceptance must be off. Preflight checks **Preferences > Documents > immediately take over a clearly found item number**, disables it with one Apply when enabled, and verifies it before opening Order. For manual calibration, disable it before starting the command.

The installed navigation shortcuts can reopen existing masters. Fresh Debtors use **New > New Debtor**; fresh Products use **Data > Products > Create a new product** after VAT verification. Blank-field checks protect existing records. Payment terms are resolved while the fresh Debtor stays open; a stale dropdown stops before Debtor Save.

Company/contact are shared fields; each address role has independent postal/optional fields. A matching contact line and Germany's `DE-` ZIP prefix are accepted as presentation. Other unexpected lines or value differences stop. Source block labels remain in extraction evidence. The workflow saves Order once and reports saved-address rebinding rather than making another repair Save.

Invoice linkage uses the exact saved Order's scoped follow-up, Order Date, and copied values because this GUI has no visible source Order No. Final verification closes only the clean Invoice, searches its exact number in Documents, reopens it, and reads persisted fields/payment.

See [requirements](requirements.md) for coverage and [verification](verification.md) for observed results.
