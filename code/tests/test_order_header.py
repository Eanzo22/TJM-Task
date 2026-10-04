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
    focused = None

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
    def set_focus(self):
        Control.focused = self
    def has_keyboard_focus(self):
        return Control.focused is self
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


class DateControl(EditControl):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active = "month"
        self.buffer = ""
        self.keys = []

    def set_focus(self):
        super().set_focus()
        self.active, self.buffer = "month", ""

    def set_edit_text(self, value):
        # Both live attempts ignored UIA SetValue, even after focus was verified.
        pass

    def window_text(self):
        return self.value

    def selection_indices(self):
        space, comma = self.value.index(" "), self.value.index(",")
        return {"month": (0, space), "day": (space + 1, comma),
                "year": (comma + 2, len(self.value))}.get(self.active, (0, len(self.value)))

    def type_keys(self, key, **options):
        from fakturama_cash.normalize import day
        assert self.has_keyboard_focus()
        assert options["set_foreground"] is False and options["vk_packet"] is False
        assert options["turn_off_numlock"] is False
        self.keys.append(key)
        fields = ("month", "day", "year")
        if key == "{RIGHT}":
            self.active = fields[(fields.index(self.active) + 1) % 3] if self.active in fields else "month"
            return
        assert len(key) == 1 and key.isdigit()  # No Enter, paste, Save or Ctrl+A.
        self.buffer += key
        if len(self.buffer) == (4 if self.active == "year" else 2):
            value = day(self.value).replace(**{self.active: int(self.buffer)})
            months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            self.value = f"{months[value.month - 1]} {value.day}, {value.year}"
            self.writes.append(self.value)
            self.buffer = ""
            self.active = fields[(fields.index(self.active) + 1) % 3]


DATE_WRITES = ["Oct 1, 2026", "Jul 1, 2026", "Jul 14, 2026"]


@pytest.fixture
def scene(monkeypatch):
    Control.focused = None
    number = EditControl("Edit", "", (40, 10, 120, 30), "TEST-ORDER-001")
    date = DateControl("Edit", "", (220, 10, 290, 30), "Oct 2, 2026")
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
    monkeypatch.setattr("fakturama_cash.ui._capture_state", lambda root: (True, None))
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


@pytest.mark.parametrize("focused", [False, True])
def test_text_replacement_reproduces_both_live_failures(scene, focused):
    date = scene[3]
    if focused:
        date.set_focus()
    date.set_edit_text("Jul 14, 2026")
    assert date.value == "Oct 2, 2026"
    assert date.writes == []


def test_date_write_focuses_then_blurs_and_verifies(scene):
    adapter, _, number, date, ref, mode, vat = scene
    adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert date.value == "Jul 14, 2026"
    assert ref.has_keyboard_focus()
    assert all(c.writes == [] for c in (number, ref, mode, vat))


def test_date_reverting_on_blur_stops_before_other_edits(scene, monkeypatch):
    adapter, _, _, date, ref, mode, vat = scene
    focus = ref.set_focus
    def focus_and_revert():
        focus()
        date.value = "Oct 2, 2026"
    monkeypatch.setattr(ref, "set_focus", focus_and_revert)
    with pytest.raises(ReviewRequired, match="Date was not retained"):
        adapter.act("fill_order_header", {"input": {"order_date": "2026-07-14", "external_reference": "TEST"}})
    assert date.writes == DATE_WRITES
    assert all(c.writes == [] for c in (ref, mode, vat))


def test_date_focus_failure_stops_before_write(scene, monkeypatch):
    adapter, _, _, date, *_ = scene
    monkeypatch.setattr(date, "set_focus", lambda: None)
    def immediate_wait(observe, reason):
        if not observe():
            raise ReviewRequired(reason, stage="UI navigation")
    monkeypatch.setattr(adapter, "_wait_for", immediate_wait)
    with pytest.raises(ReviewRequired, match="Date field did not receive focus"):
        adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert all(c.writes == [] for c in scene[2:])


def test_date_does_not_type_without_selection_pattern(scene, monkeypatch):
    adapter, _, _, date, *_ = scene
    def unavailable():
        raise RuntimeError("Text pattern unavailable")
    monkeypatch.setattr(date, "selection_indices", unavailable)
    with pytest.raises(ReviewRequired, match="Cannot read date value or selected segment"):
        adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert date.keys == []


def test_already_correct_date_does_not_disturb_segments(scene, monkeypatch):
    adapter, _, _, date, ref, *_ = scene
    date.value = "Jul 14, 2026"
    monkeypatch.setattr(date, "selection_indices", lambda: pytest.fail("No navigation needed"))
    adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert date.keys == []
    assert ref.has_keyboard_focus()


def test_native_selection_fallback_for_swt_date_without_uia_text_pattern(scene, monkeypatch):
    import sys
    adapter, _, _, field, *_ = scene
    selected = field.selection_indices
    field.handle = 456
    field.class_name = lambda: "Edit"
    field.window_text = lambda: ""  # UIA Name is blank; Value holds the date.
    field.selection_indices = lambda: (_ for _ in ()).throw(RuntimeError("No TextPattern"))
    def native(handle):
        assert handle == field.handle
        return SimpleNamespace(window_text=lambda: field.value, selection_indices=selected)
    monkeypatch.setitem(sys.modules, "pywinauto.controls.win32_controls", SimpleNamespace(EditWrapper=native))
    adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert field.value == "Jul 14, 2026"
    assert field.writes == DATE_WRITES


def test_date_does_not_type_into_other_foreground_window(scene, monkeypatch):
    adapter, _, _, date, *_ = scene
    monkeypatch.setattr("fakturama_cash.ui._capture_state", lambda root: (False, None))
    with pytest.raises(ReviewRequired, match="foreground window changed"):
        adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert date.keys == []


def test_date_stops_between_digits_if_focus_is_lost(scene, monkeypatch):
    adapter, _, _, date, ref, *_ = scene
    original = date.type_keys
    def lose_focus(key, **options):
        original(key, **options)
        if key.isdigit():
            ref.set_focus()
    monkeypatch.setattr(date, "type_keys", lose_focus)
    with pytest.raises(ReviewRequired, match="focus changed during entry"):
        adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert [k for k in date.keys if k.isdigit()] == ["0"]


def test_date_stalled_segment_navigation_does_not_type_digits(scene, monkeypatch):
    adapter, _, _, date, *_ = scene
    adapter.timeout = 0.01
    monkeypatch.setattr(date, "type_keys", lambda key, **kwargs: date.keys.append(key))
    with pytest.raises(ReviewRequired, match="navigation did not advance"):
        adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert date.keys == ["{RIGHT}"]


@pytest.mark.parametrize("initial,target,expected", [
    ("Jan 31, 2026", "2026-02-28", "Feb 28, 2026"),
    ("Feb 29, 2024", "2025-02-28", "Feb 28, 2025"),
    ("Dec 31, 2025", "2028-02-29", "Feb 29, 2028"),
])
def test_date_segments_handle_month_end_and_leap_years(scene, initial, target, expected):
    adapter, _, _, date, *_ = scene
    date.value = initial
    adapter.act("fill_order_date", {"input": {"order_date": target}})
    assert date.value == expected


def test_date_rejects_unmapped_display_format_before_keys(scene):
    adapter, _, _, date, *_ = scene
    date.value = "02.10.2026"
    with pytest.raises(ReviewRequired, match="Unsupported date display format"):
        adapter.act("fill_order_date", {"input": {"order_date": "2026-07-14"}})
    assert date.keys == []


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


def test_below_label_uses_live_geometry_not_desktop_coordinates(scene):
    adapter, pane, *_ = scene
    label = Control("Text", "Items", (500, 400, 550, 420))
    existing = Control("Image", "", (510, 430, 530, 450))
    new = Control("Image", "", (510, 460, 530, 480))
    elsewhere = Control("Image", "", (700, 425, 720, 445))
    pane.children_list.extend([label, existing, new, elsewhere])
    path = [{"control_type": "Pane", "title": "New Order"},
            {"control_type": "Image", "below_label": "Items"}]
    assert adapter.find(path, {}) is existing
    pane.children_list.append(Control("Image", "", (530, 430, 550, 450)))
    with pytest.raises(ReviewRequired, match="ambiguous"):
        adapter.find(path, {})


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
    assert [date.writes, ref.writes, mode.writes, vat.writes] == [DATE_WRITES, ["TEST-REFERENCE"], ["Net"], ["With VAT"]]
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
    assert scene[3].writes == DATE_WRITES  # One segment-entry attempt; no rollback/retry.
    assert scene[5].writes == []
    evidence = json.loads(next(tmp_path.glob("*/header-test.json")).read_text())
    assert evidence["status"] == "review_required"
    assert evidence["before"]["date"] == "2026-10-02"
    assert evidence["write_attempted"] is True


def test_date_only_repairs_partial_header_without_rewriting_other_fields(scene, header_test_cli, capsys):
    cli, args = header_test_cli
    scene[4].value = "TEST-REFERENCE"
    scene[5].value = "Net"
    assert cli.main(args + ["--date-only"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["date_only"] is True
    assert result["after"]["date"] == "2026-07-14"
    assert scene[3].writes == DATE_WRITES
    assert all(scene[index].writes == [] for index in (2, 4, 5, 6))


@pytest.mark.parametrize("field,value", [(2, "OTHER-ORDER"), (4, "OTHER-REFERENCE"), (5, "Gross"), (6, "No VAT")])
def test_date_only_refuses_unexpected_other_fields(scene, header_test_cli, capsys, field, value):
    cli, args = header_test_cli
    scene[4].value = "TEST-REFERENCE"
    scene[5].value = "Net"
    scene[field].value = value
    assert cli.main(args + ["--date-only"]) == 2
    assert json.loads(capsys.readouterr().err)["stage"] == "header test"
    assert all(c.writes == [] for c in scene[2:])


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
