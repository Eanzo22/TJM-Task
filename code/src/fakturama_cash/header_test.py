"""A supervised, unsaved header calibration test; not the production workflow."""

from .errors import ReviewRequired
from .state import write_json


def validate_test_profile(profile):
    """Allow only the observed five reads and four edits, never arbitrary actions."""
    pane = {"control_type": "Pane", "title": "New Order"}
    controls = {
        "no": {"control_type": "Edit", "title": "", "to_right_of": "No."},
        "date": {"control_type": "Edit", "title": "", "to_right_of": "Date"},
        "reference": {"control_type": "Edit", "title": "Cust.Ref."},
        "price_mode": {"control_type": "ComboBox", "title": ""},
        "vat_mode": {"control_type": "ComboBox", "title": "VAT"},
    }
    fields = {name: {"path": [pane, control], "read": "value"}
              for name, control in controls.items()}
    fields["date"]["transform"] = "date"
    actions = [
        {"path": fields["date"]["path"], "operation": "set",
         "value": "${input.order_date}", "format": "date_english", "commit_path": fields["reference"]["path"]},
        {"path": fields["reference"]["path"], "operation": "set", "value": "${input.external_reference}"},
        {"path": fields["price_mode"]["path"], "operation": "select", "value": "Net"},
        {"path": fields["vat_mode"]["path"], "operation": "select", "value": "With VAT"},
    ]
    # Exact allowlisting keeps this incomplete-profile exception from becoming
    # a generic executor of save/invoke/number-edit/navigation recipes.
    if (profile.get("window_title_re") != "^Fakturama - .*"
            or profile.get("queries", {}).get("order_header") != {"fields": fields}
            or profile.get("actions", {}).get("fill_order_header") != actions
            or profile.get("actions", {}).get("fill_order_date") != actions[:1]):
        raise ReviewRequired("Header test requires the restricted Order-header mapping",
                             stage="header test configuration")


def fill_and_verify_header(adapter, *, expected_number, order_date, reference, directory, progress, date_only=False):
    """Write once, compare all five fields, and leave any partial changes for review."""
    validate_test_profile(adapter.profile)
    record = {"status": "preparing", "write_attempted": False,
              "save_action_sent": False, "live_profile_calibrated": False, "date_only": date_only}
    evidence = directory / "header-test.json"
    write_json(evidence, record)
    try:
        progress("Activating Fakturama and checking the open New Order before editing")
        adapter.prepare_window()
        before = adapter.read("order_header", {})
        record["before"] = before
        write_json(evidence, record)
        if before["no"] != expected_number:
            raise ReviewRequired("Open Order number does not match the requested test target",
                                 stage="header test", expected=expected_number, observed=before["no"])
        expected = {"no": expected_number, "date": order_date, "reference": reference,
                    "price_mode": "Net", "vat_mode": "With VAT"}
        if date_only:
            # Explicit repair of this unsaved header only, not workflow resume.
            # Do not touch the other fields, and require them to match first.
            if any(before[key] != expected[key] for key in ("reference", "price_mode", "vat_mode")):
                raise ReviewRequired("Date-only test requires the other header fields to match", stage="header test",
                                     expected=expected, observed=before)
        elif before["reference"] != "":
            raise ReviewRequired("Customer reference is not empty; refusing to overwrite it", stage="header test")
        if not date_only and (before["price_mode"] != "Gross" or before["vat_mode"] != "With VAT"):
            raise ReviewRequired("Header is not in the observed initial Gross/With VAT state", stage="header test")
        # Discover every destination before the first edit. A later UI change can
        # still interrupt the write, so record intent before calling the adapter.
        action = "fill_order_date" if date_only else "fill_order_header"
        for step in adapter.profile["actions"][action]:
            if not adapter.find(step["path"], {}).is_enabled():
                raise ReviewRequired("Header field is disabled", stage="header test")
        record.update(status="write_attempted", write_attempted=True, expected=expected)
        write_json(evidence, record)
        progress("Changing only the date; no Save action" if date_only else
                 "Filling date/reference and selecting Net/With VAT; no Save action")
        adapter.act(action, {"input": {"order_date": order_date, "external_reference": reference}})
        progress("Reading all five fields back, including the unchanged proposed number")
        after = adapter.read("order_header", {})
        record["after"] = after
        if after != expected:
            raise ReviewRequired("Order header read-back does not match", stage="header test",
                                 expected=expected, observed=after)
        record["status"] = "verified_unsaved_order_header"
        write_json(evidence, record)
        return {**record, "evidence": str(evidence)}
    except Exception as exc:
        record["status"] = "review_required"
        record["reason"] = str(exc)
        write_json(evidence, record)
        # No rollback or automatic retry: a failed write may already have changed
        # the editor. Preserve the evidence and let the user inspect that state.
        if isinstance(exc, ReviewRequired):
            exc.details["safe_next_action"] = "Inspect the open Order and header-test.json. Partial edits may remain; do not save or retry automatically."
            raise
        raise ReviewRequired(f"Header test failed: {type(exc).__name__}: {exc}", stage="header test",
                             next_action="Inspect the open Order and header-test.json. Partial edits may remain; do not save or retry automatically.") from exc
