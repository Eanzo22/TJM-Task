# Calibrate Fakturama on a new machine

Use this after installing dependencies from [the CMD setup guide](../../code/README.md). Calibration measures table geometry and checks that Copy returns all rows. It produces `code/config/live-local.json` for this device. It does not train the model or automatically configure Fakturama.

## 1 Prepare Fakturama

1. Open an authorized, backed-up test workspace using the supported English UI.
2. In **File > Preferences > General**, configure the currency locale for Germany/EUR and check that the displayed currency example is EUR. Changing a contact's Country alone does not configure the application's currency.
3. In **Preferences > Documents**, uncheck **immediately take over a clearly found item number**, click **Apply**, then close Preferences. Otherwise a single Product result can be accepted before you finish calibration.
4. Maximize the main Fakturama window. Keep Windows display resolution/scaling and column widths unchanged for the session; leave selector dialogs at their normal size.
5. Stop any other automation. Calibration expects you to operate Fakturama between prompts, then stop interacting while it captures/copies.

## 2 Check that there are rows to measure

You need at least one saved **Debtor, Product, VAT definition, payment term, Order, and Invoice**. Existing suitable records are fine; no particular name, number, or sample business value is required.

For a completely empty test workspace, prepare them manually before calibration:

1. Check **Data > VATs** and **Data > terms of payment**; create one usable test definition in each only if there are no entries.
2. Create and save one test Debtor and one Product, using the available payment/VAT definitions.
3. Create a test Order, select that Debtor/Product, and Save it. Create and Save its follow-up Invoice. Close the saved editors.

These are manual test records used to expose a real first row and test Copy. Calibration itself never creates or saves them. It needs a populated row to measure row height/column positions; confirming an empty grid as populated would produce an invalid profile.

## 3 Start calibration in CMD

```bat
cd /d "D:\TJM Task\Implementation\TJM-Task\code"
..\.venv\Scripts\python.exe scripts\build_live_profile.py
..\.venv\Scripts\fakturama-cash.exe calibrate --profile config\live-profile.json --output config\live-local.json
```

Adjust the checkout path. The first command builds the English control mappings and marks that source profile uncalibrated. The second guides you through measurements and creates a separate local output. Do not add `--calibrated` to skip the measurements.

## 4 Repeat the capture cycle for each table

For the table named in CMD:

1. **Open it in Fakturama** using the navigation table below.
2. **Make it empty.** Enter a Search value that matches nothing, such as `__NO_MATCH__`, and wait until there are zero rows. For Order items, start with an empty temporary Order instead.
3. **Return to CMD and press Enter.** The command brings the target to the foreground and captures its table.
4. **Review the captured image.** In the review window, check **I checked this is an empty table**, then click **Accept reviewed capture**. Confirm only if there are no data rows.
5. **Make it populated.** Return to Fakturama and clear Search. Show at least one row and determine the full result count, including rows below the visible area. For Order items, manually select one existing Product into the unsaved Order.
6. **Return to CMD and press Enter again.** The populated screenshot opens in the review window.
7. **Mark the screenshot**, following the exact click sequence below. Enter the total row count, check **I checked the column order and the total row count against Fakturama**, then click **Accept reviewed capture**.
8. The command returns to the live table, copies its results, and compares the row count. Keep that table unchanged until CMD prompts for the next one.

The review window displays a **captured image**. Click marks there, not on Fakturama. If a mark is wrong, use **Reset marks** and repeat. Scrollbars in the review window scroll the image only.

### Where to open the seven tables

| CMD table | Your action in Fakturama |
| --- | --- |
| Documents: Orders | Open **Data > Documents** and select **Orders** |
| Documents: Invoices | In Documents, select **Invoices** |
| VATs | Open **Data > VATs** |
| Terms of payment | Open **Data > terms of payment** |
| Product selector | Open a temporary **New Order**, choose **Net / With VAT**, and click the upper Product-selection icon beside Items; keep the draft unsaved |
| Debtor selector | Cancel the Product dialog; on that same Order, click the upper existing-contact icon beside Addresses |
| Order items | Cancel the Debtor dialog and show that same unsaved Order's Items table. Keep it empty for the first capture; add one existing Product for the second |

Use the upper existing-record selectors rather than green plus controls. Clear the Search filter after each list's populated measurement. Keep empty/populated captures at the same table size.

### What to click in a populated screenshot

For the first six tables, click in this order:

1. The first pixel immediately **below the column-header divider**.
2. The first pixel immediately **below the first data-row divider**.
3. Inside a data cell in that first row, away from borders; the record name/number cell is a useful choice.

```text
Column headings
--------------------  Click just below this divider first
First record
--------------------  Click just below this divider second
Second record
```

For **Order items**, the first two clicks are the same. Then click the **right edge of the Total heading**, before unused header space, followed by the centres of these first-row cells: **Quantity, Name, VAT, Unit Price, Discount**, in that order. Enter **1** as the row count if you added one Product. The on-screen prompt identifies the next required mark.

## 5 Finish and use the local profile

After all seven tables pass, CMD reports **calibrated_local_profile** and the output file is written. Cancel any open selector, close the temporary Order **without saving**, clear remaining Search filters, and leave no dirty editor tabs.

```bat
..\.venv\Scripts\fakturama-cash.exe check-profile config\live-local.json
..\.venv\Scripts\fakturama-cash.exe validate "..\documents\Live_Task.png"
..\.venv\Scripts\fakturama-cash.exe run "..\documents\Live_Task.png" --profile config\live-local.json
```

The vision environment settings from setup must still be set in this CMD, including CPU-only mode if required. Run only after validation passes and you have reviewed its values. The image command creates a new transaction; do not rerun an already saved transaction in the same workspace to repeat a demonstration.

Calibration does not certify a complete business run. It retains the English control mappings; changed language/column order can need code/profile review. Changing resolution, scaling, or table layout later may require recalibration.

## If calibration stops

- **No populated row:** prepare the missing record manually, then start calibration again.
- **Different table bounds/header:** restore the same size/layout for both captures and start again. Do not resize between empty and populated screenshots.
- **Copied count differs:** check the true count and whether Copy includes off-screen rows. Do not enter a convenient count to bypass the check.
- **Control not found:** verify the English UI, correct table/dialog, and temporary Order title. For a different pane title, use `--order-editor "Exact pane title"`.
- **Cancelled review or failed measurement:** any existing `live-local.json` is preserved. The current command restarts the seven-table sequence rather than resuming halfway.

Private captures and measurement files are under `code/evidence/private/calibration/<attempt>/`. The output profile is ignored by Git. Only the generated **live-local.json** should be used as this device's calibrated profile; an unfinished draft is not ready to run.
