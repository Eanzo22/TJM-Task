"""Order header lookup tests based on observed layout, with synthetic values."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.ui import UIAAdapter, load_profile


PROFILE = Path(__file__).parents[1] / "config/order-header.partial.json"


class Box:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom
    def width(self):
        return self.right - self.left
    def height(self):
        return self.bottom - self.top


class Control:
    def __init__(self, kind, name, bounds, value="", children=None):
        self.element_info = SimpleNamespace(control_type=kind, name=name, automation_id="unused-changing-id")
        self.box, self.value, self.children_list = Box(*bounds), value, children or []
        self.writes = []
    def rectangle(self):
        return self.box
    def is_visible(self):
        return True
    def is_enabled(self):
        return True
    def descendants(self, control_type=None):
        return [c for c in self.children_list if control_type is None or c.element_info.control_type == control_type]
    def set_edit_text(self, value):
        self.value = value
        self.writes.append(value)
    def select(self, value):
        self.value = value
        self.writes.append(value)


class EditControl(Control):
    def get_value(self):
        return self.value


class ComboControl(Control):
    # Match pywinauto: ComboBoxWrapper deliberately has no get_value().
    def selected_text(self):
        return self.value


@pytest.fixture
def scene(monkeypatch):
    number = EditControl("Edit", "", (40, 10, 120, 30), "TEST-ORDER-001")
    date = EditControl("Edit", "", (220, 10, 290, 30), "Oct 2, 2026")
    ref = EditControl("Edit", "Cust.Ref.", (40, 60, 200, 80))
    mode = ComboControl("ComboBox", "", (310, 10, 390, 30), "Gross")
    vat = ComboControl("ComboBox", "VAT", (310, 60, 390, 80), "With VAT")
    controls = [Control("Text", "No.", (10, 10, 30, 30)), number,
                Control("Text", "Date", (180, 10, 210, 30)), date, ref, mode, vat]
    pane = Control("Pane", "New Order", (0, 0, 400, 300), children=controls)
    unrelated = Control("Edit", "Cust.Ref.", (40, 400, 200, 420), "OTHER EDITOR")
    root = Control("Window", "Fakturama", (0, 0, 800, 600), children=[pane, unrelated])
    adapter = UIAAdapter(load_profile(PROFILE), desktop=object())
    monkeypatch.setattr(adapter, "root", lambda: root)
    return adapter, pane, number, date, ref, mode, vat


@pytest.mark.parametrize("scale,offset", [(1, 0), (2, 500)])
def test_header_lookup_is_scoped_and_moves_with_labels(scene, scale, offset):
    adapter, pane, *_ = scene
    for control in pane.children_list:
        b = control.box
        control.box = Box(b.left * scale + offset, b.top * scale + offset,
                          b.right * scale + offset, b.bottom * scale + offset)
    result = adapter._read(adapter.profile["queries"]["order_header"], {})
    assert result == {"no": "TEST-ORDER-001", "date": "2026-10-02", "reference": "",
                      "price_mode": "Gross", "vat_mode": "With VAT"}
    assert all(control.writes == [] for control in pane.children_list)


def test_dropdown_without_selected_value_stops(scene):
    adapter, _, _, _, _, _, vat = scene
    assert not hasattr(vat, "get_value")
    vat.value = None
    spec = adapter.profile["queries"]["order_header"]["fields"]["vat_mode"]
    with pytest.raises(ReviewRequired, match="no selected value"):
        adapter._scalar(spec, {})


def test_dropdown_without_read_pattern_stops(scene, monkeypatch):
    adapter, _, _, _, _, _, vat = scene
    def unavailable():
        raise RuntimeError("Selection/Value pattern unavailable")
    monkeypatch.setattr(vat, "selected_text", unavailable)
    spec = adapter.profile["queries"]["order_header"]["fields"]["vat_mode"]
    with pytest.raises(ReviewRequired, match="Cannot read dropdown selection"):
        adapter._scalar(spec, {})
    assert vat.writes == []


def test_header_fill_preserves_number_and_uses_source_values(scene):
    adapter, pane, number, date, ref, mode, vat = scene
    adapter.act("fill_order_header", {"input": {"order_date": "2026-07-14", "external_reference": "SYNTHETIC-REF"}})
    assert number.writes == []
    assert date.value == "Jul 14, 2026"
    assert ref.value == "SYNTHETIC-REF"
    assert mode.value == "Net" and vat.value == "With VAT"


def test_missing_number_cannot_select_date_field(scene):
    adapter, pane, number, *_ = scene
    pane.children_list.remove(number)
    spec = adapter.profile["queries"]["order_header"]["fields"]["no"]
    with pytest.raises(ReviewRequired, match="Another label"):
        adapter._scalar(spec, {})


def test_duplicate_label_stops(scene):
    adapter, pane, *_ = scene
    pane.children_list.append(Control("Text", "Date", (180, 10, 210, 30)))
    spec = adapter.profile["queries"]["order_header"]["fields"]["date"]
    with pytest.raises(ReviewRequired, match="label is missing or ambiguous"):
        adapter._scalar(spec, {})


def test_tied_field_candidates_stop(scene):
    adapter, pane, *_ = scene
    pane.children_list.append(Control("Edit", "", (220, 10, 300, 30)))
    spec = adapter.profile["queries"]["order_header"]["fields"]["date"]
    with pytest.raises(ReviewRequired, match="Control is ambiguous"):
        adapter._scalar(spec, {})


def test_draft_is_not_a_complete_order_query_or_live_profile():
    profile = load_profile(PROFILE)
    assert profile["calibrated"] is False
    assert "order" not in profile["queries"]
    assert "save_order" not in profile["actions"]
    assert "to_right_of" in json.dumps(profile)


def test_inspect_order_only_reads_and_preserves_each_attempt(scene, monkeypatch, tmp_path, capsys):
    from fakturama_cash import cli
    adapter, *_ = scene
    monkeypatch.setattr(cli, "UIAAdapter", lambda profile: adapter)
    monkeypatch.setattr(adapter, "act", lambda *args: pytest.fail("Unexpected write"))
    monkeypatch.setattr(adapter, "prepare_window", lambda: pytest.fail("Unexpected navigation"))
    monkeypatch.setattr(adapter, "read", lambda name, ctx: adapter._read(adapter.profile["queries"][name], ctx))
    for _ in range(2):
        assert cli.main(["inspect-order", "--profile", str(PROFILE), "--out", str(tmp_path), "--quiet"]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "observed_order_header"
        assert output["header"]["no"] == "TEST-ORDER-001"
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_inspect_order_rejects_query_navigation(monkeypatch, tmp_path, capsys):
    from fakturama_cash import cli
    profile = load_profile(PROFILE)
    profile["queries"]["order_header"]["prepare"] = [{"operation": "select_tab", "path": []}]
    monkeypatch.setattr(cli, "load_profile", lambda path: profile)
    monkeypatch.setattr(cli, "UIAAdapter", lambda *args: pytest.fail("Must reject before connecting"))
    assert cli.main(["inspect-order", "--quiet", "--out", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().err)["stage"] == "UI inspection"


@pytest.fixture
def header_test_cli(scene, monkeypatch, tmp_path):
    from fakturama_cash import cli
    adapter, *_ = scene
    monkeypatch.setattr(cli, "UIAAdapter", lambda profile: adapter)
    monkeypatch.setattr(adapter, "prepare_window", lambda: None)
    monkeypatch.setattr(adapter, "read", lambda name, ctx: adapter._read(adapter.profile["queries"][name], ctx))
    args = ["test-order-header", "--expected-number", "TEST-ORDER-001", "--date", "2026-07-14",
            "--reference", "TEST-REFERENCE", "--out", str(tmp_path), "--quiet"]
    return cli, args


def test_controlled_header_fill_verifies_without_saving(scene, header_test_cli, tmp_path, capsys):
    adapter, _, number, date, ref, mode, vat = scene
    cli, args = header_test_cli
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "verified_unsaved_order_header"
    assert result["after"] == {"no": "TEST-ORDER-001", "date": "2026-07-14", "reference": "TEST-REFERENCE",
                               "price_mode": "Net", "vat_mode": "With VAT"}
    assert result["save_action_sent"] is False
    assert result["live_profile_calibrated"] is False
    assert number.writes == []
    assert [date.writes, ref.writes, mode.writes, vat.writes] == [["Jul 14, 2026"], ["TEST-REFERENCE"], ["Net"], ["With VAT"]]
    saved = json.loads(Path(result["evidence"]).read_text())
    assert saved["before"]["reference"] == ""
    assert saved["after"] == result["after"]


@pytest.mark.parametrize("field,value", [(2, "OTHER-ORDER"), (4, "EXISTING-REFERENCE"), (5, "Net"), (6, "No VAT")])
def test_controlled_header_fill_refuses_unexpected_initial_state(scene, header_test_cli, capsys, field, value):
    scene[field].value = value
    cli, args = header_test_cli
    assert cli.main(args) == 2
    assert json.loads(capsys.readouterr().err)["stage"] == "header test"
    assert all(c.writes == [] for c in scene[2:])


def test_controlled_header_fill_stops_on_readback_mismatch(scene, header_test_cli, monkeypatch, tmp_path, capsys):
    cli, args = header_test_cli
    ref = scene[4]
    monkeypatch.setattr(ref, "set_edit_text", lambda value: None)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().err)
    assert result["reason"] == "Order header read-back does not match"
    evidence = json.loads(next(tmp_path.glob("*/header-test.json")).read_text())
    assert evidence["write_attempted"] is True
    assert evidence["after"]["reference"] == ""
    assert evidence["save_action_sent"] is False


def test_controlled_header_fill_keeps_partial_failure_evidence(scene, header_test_cli, monkeypatch, tmp_path, capsys):
    cli, args = header_test_cli
    def fail(value):
        raise RuntimeError("UI changed")
    monkeypatch.setattr(scene[4], "set_edit_text", fail)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().err)
    assert "Partial edits may remain" in result["safe_next_action"]
    assert scene[3].writes == ["Jul 14, 2026"]  # One attempt; no rollback/retry.
    assert scene[5].writes == []
    evidence = json.loads(next(tmp_path.glob("*/header-test.json")).read_text())
    assert evidence["status"] == "review_required"
    assert evidence["before"]["date"] == "2026-10-02"
    assert evidence["write_attempted"] is True


@pytest.mark.parametrize("mutation", ["save", "number", "navigation", "wrong_window"])
def test_controlled_header_fill_rejects_extra_operations_before_connecting(monkeypatch, capsys, mutation):
    from fakturama_cash import cli
    profile = load_profile(PROFILE)
    if mutation == "save":
        profile["actions"]["fill_order_header"].append({"operation": "invoke", "path": []})
    elif mutation == "number":
        profile["actions"]["fill_order_header"][0]["path"] = profile["queries"]["order_header"]["fields"]["no"]["path"]
    elif mutation == "navigation":
        profile["queries"]["order_header"]["prepare"] = [{"operation": "select_tab", "path": []}]
    else:
        profile["window_title_re"] = ".*"
    monkeypatch.setattr(cli, "load_profile", lambda path: profile)
    monkeypatch.setattr(cli, "UIAAdapter", lambda *args: pytest.fail("Must reject before connecting"))
    assert cli.main(["test-order-header", "--expected-number", "TEST-ORDER-001", "--date", "2026-07-14",
                     "--reference", "TEST-REFERENCE", "--quiet"]) == 2
    assert json.loads(capsys.readouterr().err)["stage"] == "header test configuration"
