"""Focused custom-grid tests; no real clipboard, desktop, or application writes."""
from types import SimpleNamespace
import sys

import pytest

from fakturama_cash import clipboard_table, ui
from fakturama_cash.clipboard_table import copy_table, parse_table
from fakturama_cash.errors import ReviewRequired
from fakturama_cash.matching import exact_match


def test_tsv_preserves_empty_cells_multiline_fields_and_duplicate_records():
    text = 'SKU\tDescription\tStock\r\nA\t"first\nsecond"\t\r\nA\t"first\nsecond"\t\r\n'
    rows = parse_table(text, ["sku", "description", "stock"], headers=["SKU", "Description", "Stock"])
    assert rows == [{"sku": "A", "description": "first\nsecond", "stock": ""}] * 2
    with pytest.raises(ReviewRequired, match="Ambiguous"):
        exact_match(rows, {"sku": "A"}, identity="sku")


@pytest.mark.parametrize("text", ["A\tName\textra", "A", "\t", 'A\t"unfinished', "A\tNam…", "A\tNam..."])
def test_bad_or_truncated_cells_stop(text):
    with pytest.raises(ReviewRequired):
        parse_table(text, ["sku", "name"])


def test_header_count_and_empty_checks_are_independent():
    with pytest.raises(ReviewRequired, match="headers"):
        parse_table("wrong\nA", ["sku"], headers=["SKU"])
    with pytest.raises(ReviewRequired, match="row count"):
        parse_table("A", ["sku"], expected_count=2)
    with pytest.raises(ReviewRequired, match="empty"):
        parse_table("", ["sku"])
    assert parse_table("SKU\r\n", ["sku"], headers=["SKU"], empty_confirmed=True, expected_count=0) == []


def test_raw_nattable_copy_preserves_literal_quotes():
    assert parse_table('A\t"Quoted name"', ["sku", "name"], format="raw_tsv") == [
        {"sku": "A", "name": '"Quoted name"'}]


class Clipboard:
    def __init__(self):
        self.number = 3
        self.pid = 10
        self.text = "OLD\tCLIPBOARD"
    def sequence(self):
        return self.number
    def owner_process(self):
        return self.pid
    def read(self):
        return self.text


class Grid:
    def __init__(self, clipboard=None):
        self.element_info = SimpleNamespace(runtime_id=[1, 2, 3], control_type="Pane")
        self.clipboard = clipboard
        self.keys = []
        self.focused = False
        self.copy_works = True
    def process_id(self):
        return 10
    def set_focus(self):
        self.focused = True
    def type_keys(self, key, **kwargs):
        assert kwargs["set_foreground"] is False
        self.keys.append(key)
        if key == "^c" and self.copy_works and self.clipboard:
            self.clipboard.number += 1
            self.clipboard.text = "A\tTest"


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(clipboard_table.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(clipboard_table.time, "sleep", lambda duration: now.__setitem__(0, now[0] + duration))
    return now


@pytest.fixture
def native_clipboard(monkeypatch):
    # Real pywintypes exception type, mocked native calls: no desktop access.
    error_type = pytest.importorskip('pywintypes').error
    clipboard = clipboard_table.WindowsClipboard()
    clipboard.number, clipboard.pid, clipboard.text = 3, 10, 'OLD\tCLIPBOARD'
    monkeypatch.setattr(clipboard, 'sequence', lambda: clipboard.number)
    monkeypatch.setattr(clipboard, 'owner_process', lambda: clipboard.pid)
    calls, failures = [], []
    def open_clipboard():
        calls.append('open')
        if failures:
            raise failures.pop(0)
    native = SimpleNamespace(OpenClipboard=open_clipboard,
                             CloseClipboard=lambda: calls.append('close'),
                             CF_UNICODETEXT=13,
                             IsClipboardFormatAvailable=lambda format: True,
                             GetClipboardData=lambda format: clipboard.text)
    monkeypatch.setitem(sys.modules, 'win32clipboard', native)
    return clipboard, calls, failures, native, error_type


def test_copy_accepts_only_new_text_from_the_target_process(clock):
    clipboard = Clipboard()
    grid = Grid(clipboard)
    assert copy_table(grid, is_safe=lambda: grid.focused, timeout=1, clipboard=clipboard) == "A\tTest"
    assert grid.keys == ["^a", "^c"]


@pytest.mark.parametrize('select_all', [True, False])
def test_native_access_denial_retries_only_read_and_closes_only_successful_open(clock, native_clipboard, select_all):
    clipboard, calls, failures, _, error_type = native_clipboard
    failures.extend([error_type(5, 'OpenClipboard', 'Access is denied.')] * 2)
    grid = Grid(clipboard)
    assert copy_table(grid, is_safe=lambda: True, timeout=120, clipboard=clipboard,
                      select_all=select_all) == 'A\tTest'
    assert calls == ['open', 'open', 'open', 'close']
    assert grid.keys == (['^a', '^c'] if select_all else ['^c'])


@pytest.mark.parametrize('timeout', [1, 120])
def test_persistent_native_access_denial_is_bounded_and_does_not_repeat_copy(clock, native_clipboard, timeout):
    clipboard, calls, failures, _, error_type = native_clipboard
    failures.extend([error_type(5, 'OpenClipboard', 'Access is denied.')] * 100)
    grid = Grid(clipboard)
    with pytest.raises(ReviewRequired, match='Clipboard remained busy') as error:
        copy_table(grid, is_safe=lambda: True, timeout=timeout, clipboard=clipboard)
    assert error.value.details['stage'] == 'table_read'
    assert clock[0] <= min(timeout, 3)
    assert 'close' not in calls
    assert grid.keys == ['^a', '^c']


@pytest.mark.parametrize('change', ['focus', 'owner'])
def test_clipboard_retry_stops_when_focus_or_ownership_changes(clock, native_clipboard, change):
    clipboard, calls, failures, _, error_type = native_clipboard
    failures.append(error_type(5, 'OpenClipboard', 'Access is denied.'))
    monkey_owner = clipboard.owner_process
    clipboard.owner_process = lambda: 999 if change == 'owner' and clock[0] > 0 else monkey_owner()
    grid = Grid(clipboard)
    with pytest.raises(ReviewRequired, match='focus changed|another application'):
        copy_table(grid, is_safe=lambda: not (change == 'focus' and clock[0] > 0),
                   timeout=120, clipboard=clipboard)
    assert calls == ['open']
    assert grid.keys == ['^a', '^c']


@pytest.mark.parametrize('operation', ['OpenClipboard', 'GetClipboardData'])
def test_other_native_errors_are_not_treated_as_clipboard_contention(clock, native_clipboard, operation):
    clipboard, calls, failures, native, error_type = native_clipboard
    failure = error_type(6 if operation == 'OpenClipboard' else 5, operation, 'Native failure')
    if operation == 'OpenClipboard':
        failures.append(failure)
    else:
        def fail_read(format):
            raise failure
        native.GetClipboardData = fail_read
    grid = Grid(clipboard)
    with pytest.raises(error_type):
        copy_table(grid, is_safe=lambda: True, timeout=120, clipboard=clipboard)
    assert calls == (['open'] if operation == 'OpenClipboard' else ['open', 'close'])
    assert clock[0] == 0
    assert grid.keys == ['^a', '^c']


def test_failed_copy_never_reuses_old_clipboard_or_retries_keys(clock):
    clipboard = Clipboard()
    grid = Grid(clipboard)
    grid.copy_works = False
    with pytest.raises(ReviewRequired, match="did not update"):
        copy_table(grid, is_safe=lambda: True, timeout=1, clipboard=clipboard)
    assert grid.keys == ["^a", "^c"]


def test_clipboard_changed_by_other_application_stops(clock):
    clipboard = Clipboard()
    clipboard.pid = 999
    with pytest.raises(ReviewRequired, match="another application"):
        copy_table(Grid(clipboard), is_safe=lambda: True, timeout=1, clipboard=clipboard)


def test_focus_loss_stops_before_copy(clock):
    grid = Grid(Clipboard())
    with pytest.raises(ReviewRequired, match="before copy"):
        copy_table(grid, is_safe=lambda: len(grid.keys) == 0, timeout=1, clipboard=grid.clipboard)
    assert grid.keys == ["^a"]


@pytest.fixture
def adapter(monkeypatch):
    profile = {"queries": {"products": {
        "path": [{"title": "Products"}, {"control_type": "Pane", "leaf": True}],
        "clipboard_rows": {"columns": ["sku", "name"], "copy_scope": "all_rows",
                           "keyboard_selection": "ctrl_home_down_enter"}}},
        "actions": {"select_product": [{"operation": "select_copied_row", "query": "products",
                                        "value": "${selected_product}"}]}}
    adapter = ui.UIAAdapter(profile, desktop=object())
    grid = Grid()
    copied = ["A\tFirst\r\nB\tSecond\r\n"]
    monkeypatch.setattr(adapter, "find", lambda *args: grid)
    monkeypatch.setattr(adapter, "_keyboard_safe", lambda c: True)
    monkeypatch.setattr(clipboard_table, "copy_table", lambda *args, **kwargs: copied[0])
    monkeypatch.setattr(ui, "wait_stable", lambda observe, **kwargs: observe())
    return adapter, grid, copied


def test_selection_rechecks_snapshot_and_consumes_token_once(adapter):
    subject, grid, _ = adapter
    row = exact_match(subject.read("products", {}), {"sku": "B"}, identity="sku")
    subject.act("select_product", {"selected_product": row})
    assert grid.keys == ["^{HOME}", "{DOWN}", "{ENTER}"]
    with pytest.raises(ReviewRequired, match="current table observation"):
        subject.act("select_product", {"selected_product": row})
    assert len(grid.keys) == 3


@pytest.mark.parametrize("failure", [None, "wrong_row", "changed_header"])
def test_double_click_rechecks_selected_row_and_calibrated_header(adapter, monkeypatch, failure):
    from PIL import Image
    subject, grid, _ = adapter
    picture = Image.new("RGB", (12, 30), "white")
    geometry = {"width": 12, "header_height": 5, "row_height": 10, "column_x": 4,
                "header_sha256": clipboard_table.snapshot_fingerprint(picture.crop((0, 0, 12, 5)))["sha256"]}
    subject.profile["queries"]["products"]["clipboard_rows"].update(
        keyboard_selection="ctrl_home_down_double_click", row_geometry=geometry)
    grid.capture_as_image = lambda: picture
    grid.descendants = lambda **kwargs: []
    row = subject.read("products", {})[1]
    calls = []
    def copy(*args, **kwargs):
        if kwargs.get("select_all") is False:
            return "A\tFirst" if failure == "wrong_row" else "B\tSecond"
        return "A\tFirst\nB\tSecond"
    monkeypatch.setattr(clipboard_table, "copy_table", copy)
    monkeypatch.setattr(ui, "_click_control", lambda *args, **kwargs: calls.append(kwargs))
    if failure == "changed_header":
        picture.putpixel((0, 0), (0, 0, 0))
    if failure:
        with pytest.raises(ReviewRequired):
            subject.act("select_product", {"selected_product": row})
        assert calls == []
    else:
        subject.act("select_product", {"selected_product": row})
        assert calls == [{"relative": (4, 20), "double": True}]
    assert "{ENTER}" not in grid.keys


@pytest.mark.parametrize('failure', [None, 'wrong_row', 'disabled', 'replaced'])
def test_selector_confirms_only_verified_row_with_scoped_ok(adapter, monkeypatch, failure):
    subject, grid, _ = adapter
    subject.profile['queries']['products']['clipboard_rows']['keyboard_selection'] = 'ctrl_home_down_confirm'
    step = subject.profile['actions']['select_product'][0]
    step['confirm_path'] = 'dialog_ok'
    calls = []
    button = SimpleNamespace(is_enabled=lambda: failure != 'disabled', invoke=lambda: calls.append('OK'))
    def find(path, context):
        if path == 'dialog_ok':
            if failure == 'replaced':
                grid.element_info.runtime_id = [9, 9, 9]
            return button
        return grid
    monkeypatch.setattr(subject, 'find', find)
    def copy(*args, **kwargs):
        if kwargs.get('select_all') is False:
            return 'A\tFirst' if failure == 'wrong_row' else 'B\tSecond'
        return 'A\tFirst\nB\tSecond'
    monkeypatch.setattr(clipboard_table, 'copy_table', copy)
    monkeypatch.setattr(ui, '_click_control', lambda *args, **kwargs: pytest.fail('Selector must confirm with OK'))
    row = subject.read('products', {})[1]
    if failure:
        with pytest.raises(ReviewRequired):
            subject.act('select_product', {'selected_product': row})
        assert calls == []
    else:
        subject.act('select_product', {'selected_product': row})
        assert calls == ['OK']
    assert grid.keys == ['^{HOME}', '{DOWN}']
    assert subject._table_reads == {}


@pytest.mark.parametrize("change", ["reorder", "content", "replace", "forged", "negative"])
def test_stale_or_forged_row_never_activates(adapter, change):
    subject, grid, copied = adapter
    selected = subject.read("products", {})[1]
    if change == "reorder":
        copied[0] = "B\tSecond\nA\tFirst"
    elif change == "content":
        copied[0] = "A\tFirst\nB\tOther"
    elif change == "replace":
        grid.element_info.runtime_id = [4, 5, 6]
    elif change == "forged":
        selected["sku"] = "IMPOSTOR"
    else:
        selected["_ui_row"]["index"] = -1
    with pytest.raises(ReviewRequired, match="changed since"):
        subject.act("select_product", {"selected_product": selected})
    assert grid.keys == []


def test_explicit_empty_indicator_returns_empty_without_copy(adapter, monkeypatch):
    subject, grid, _ = adapter
    spec = subject.profile["queries"]["products"]
    spec.update(empty_indicator={"path": "status"}, empty_text="No results")
    monkeypatch.setattr(subject, "_scalar", lambda *args: "No results")
    monkeypatch.setattr(clipboard_table, "copy_table", lambda *args, **kwargs: pytest.fail("empty grid copy"))
    assert subject.read("products", {}) == []
    assert grid.keys == []


def test_calibrated_empty_pixels_skip_the_crashing_copy_command(adapter, monkeypatch):
    from PIL import Image
    subject, grid, _ = adapter
    image = Image.new("RGB", (12, 8), "white")
    grid.capture_as_image = lambda: image
    subject.profile["queries"]["products"]["clipboard_rows"]["empty_snapshot"] = clipboard_table.snapshot_fingerprint(image)
    monkeypatch.setattr(clipboard_table, "copy_table", lambda *args, **kwargs: pytest.fail("empty grid copy"))
    assert subject.read("products", {}) == []
    assert grid.keys == ["^{HOME}"]


def test_changed_table_size_cannot_reuse_empty_calibration(adapter, monkeypatch):
    from PIL import Image
    subject, grid, _ = adapter
    subject.profile["queries"]["products"]["clipboard_rows"]["empty_snapshot"] = clipboard_table.snapshot_fingerprint(Image.new("RGB", (12, 8)))
    grid.capture_as_image = lambda: Image.new("RGB", (13, 8))
    monkeypatch.setattr(clipboard_table, "copy_table", lambda *args, **kwargs: pytest.fail("layout changed"))
    with pytest.raises(ReviewRequired, match="layout changed"):
        subject.read("products", {})


@pytest.mark.parametrize('populated', [False, True])
def test_empty_crop_checks_calibrated_area_when_canvas_grows(adapter, monkeypatch, populated):
    from PIL import Image
    subject, grid, _ = adapter
    calibrated = Image.new('RGB', (12, 8), 'white')
    wider = Image.new('RGB', (33, 20), 'gray')
    wider.paste(calibrated, (0, 0))
    if populated:
        wider.putpixel((3, 5), (0, 0, 0))
    grid.capture_as_image = lambda: wider
    config = subject.profile['queries']['products']['clipboard_rows']
    config.update(empty_crop=True, empty_snapshot=clipboard_table.snapshot_fingerprint(calibrated))
    if populated:
        assert [row['sku'] for row in subject.read('products', {})] == ['A', 'B']
    else:
        monkeypatch.setattr(clipboard_table, 'copy_table', lambda *args, **kw: pytest.fail('empty copy'))
        assert subject.read('products', {}) == []


def test_empty_crop_rejects_a_canvas_smaller_than_calibrated_area(adapter):
    from PIL import Image
    subject, grid, _ = adapter
    config = subject.profile['queries']['products']['clipboard_rows']
    config.update(empty_crop=True,
                  empty_snapshot=clipboard_table.snapshot_fingerprint(Image.new('RGB', (12, 8))))
    grid.capture_as_image = lambda: Image.new('RGB', (11, 8))
    with pytest.raises(ReviewRequired, match='crop no longer fits'):
        subject.read('products', {})


def test_nonempty_grid_pixels_continue_to_normal_copy(adapter):
    from PIL import Image
    subject, grid, _ = adapter
    subject.profile["queries"]["products"]["clipboard_rows"]["empty_snapshot"] = clipboard_table.snapshot_fingerprint(Image.new("RGB", (12, 8), "white"))
    grid.capture_as_image = lambda: Image.new("RGB", (12, 8), "black")
    assert [r["sku"] for r in subject.read("products", {})] == ["A", "B"]


def test_visible_only_copy_is_not_accepted(adapter):
    subject, _, _ = adapter
    subject.profile["queries"]["products"]["clipboard_rows"]["copy_scope"] = "visible_rows"
    with pytest.raises(ReviewRequired, match="all result rows"):
        subject.read("products", {})


def test_inspection_of_unverified_copy_cannot_issue_selection_tokens(adapter):
    subject, grid, _ = adapter
    subject.profile["queries"]["products"]["clipboard_rows"]["copy_scope"] = "unverified"
    rows = subject.inspect_table("products")
    assert rows[0]["sku"] == "A" and "_ui_row" not in rows[0]
    assert subject._table_reads == {}
    with pytest.raises(ReviewRequired, match="all result rows"):
        subject.read("products", {})
    subject.profile["calibrated"] = True
    with pytest.raises(ReviewRequired, match="all result rows"):
        subject.preflight(set(), {"products"}, connect=False)
    assert grid.keys == []
