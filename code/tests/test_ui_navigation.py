"""Minimal tab/panel navigation tests; no real desktop operations."""
from types import SimpleNamespace

import pytest

from fakturama_cash import ui
from fakturama_cash.errors import ReviewRequired


class Box:
    left, top, right, bottom = 0, 0, 100, 100
    def width(self):
        return self.right - self.left
    def height(self):
        return self.bottom - self.top


@pytest.fixture
def setup(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(ui.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(ui.time, "sleep", lambda duration: now.__setitem__(0, now[0] + duration))
    return ui.UIAAdapter({"timeout_seconds": 1}, desktop=object())


class Tab:
    element_info = SimpleNamespace(control_type="TabItem")
    def __init__(self, working=True):
        self.selected = False
        self.selections = 0
        self.working = working
    def is_enabled(self):
        return True
    def is_selected(self):
        return self.selected
    def select(self):
        self.selections += 1
        self.selected = self.working


def test_nested_tab_steps_reacquire_and_verify(setup, monkeypatch):
    tabs = {"outer": Tab(), "inner": Tab()}
    observations = []
    def find(path, context):
        observations.append(path)
        if path == "inner":
            assert tabs["outer"].selected
        return tabs[path]
    monkeypatch.setattr(setup, "find", find)
    setup.profile["actions"] = {"open_section": [
        {"operation": "select_tab", "path": "outer"},
        {"operation": "select_tab", "path": "inner"}]}
    setup.act("open_section", {})
    setup.act("open_section", {})  # Already selected tabs must not be clicked again.
    assert [tab.selections for tab in tabs.values()] == [1, 1]
    assert observations.count("inner") >= 2


def test_document_category_selection_does_not_preserve_previous_filter(setup, monkeypatch):
    item = Tab()
    item.element_info = SimpleNamespace(control_type='TreeItem')
    monkeypatch.setattr(setup, 'find', lambda *args: item)
    step = dict(operation='select_tree', path='Orders category')
    setup._navigate_control(step, {})
    setup._navigate_control(step, {})
    assert item.is_selected() and item.selections == 1


def test_combined_document_categories_reject_a_repeated_document(setup, monkeypatch):
    row = dict(type='Order', no='PO000001')
    setup.profile['queries'] = {'orders': {'path':'orders'}, 'invoices': {'path':'invoices'}}
    monkeypatch.setattr(setup, '_scalar', lambda *args: [row])
    with pytest.raises(ReviewRequired, match='multiple categories'):
        setup._read({'concat_queries':['orders','invoices']}, {})


def test_tab_selection_failure_stops_without_repeated_clicks(setup, monkeypatch):
    tab = Tab(working=False)
    monkeypatch.setattr(setup, "find", lambda *args: tab)
    with pytest.raises(ReviewRequired, match="did not become selected"):
        setup._navigate_control({"operation": "select_tab", "path": "tab"}, {})
    assert tab.selections == 1


def test_broken_selection_pattern_falls_back_to_observed_tab_bounds(setup, monkeypatch):
    tab = Tab()
    clicks = []
    def unavailable():
        raise RuntimeError("Member not found")
    def click_input(**kwargs):
        clicks.append(kwargs)
        tab.selected = True
    tab.select = unavailable
    tab.rectangle = lambda: Box()
    tab.click_input = click_input
    monkeypatch.setattr(setup, "find", lambda *args: tab)
    monkeypatch.setattr(ui, "_click_control", lambda c: c.click_input(coords=(50, 50)))
    setup._navigate_control({"operation": "select_tab", "path": "tab"}, {})
    assert clicks == [{"coords": (50, 50)}]


class Panel:
    def __init__(self, moving=True):
        self.iface_scroll = SimpleNamespace(CurrentVerticalScrollPercent=0, CurrentHorizontalScrollPercent=0)
        self.steps = 0
        self.moving = moving
    def rectangle(self):
        return Box()
    def scroll(self, direction, amount, count):
        assert amount == "page" and count == 1
        self.steps += 1
        if self.moving:
            self.iface_scroll.CurrentVerticalScrollPercent += 10


def panel_setup(adapter, monkeypatch, *, after=2, moving=True, ambiguous=False):
    panel = Panel(moving)
    target = SimpleNamespace(rectangle=lambda: Box())
    calls = []
    def find(path, context):
        assert path == "panel"
        calls.append(path)
        return panel
    def target_find(path, context, parent=None):
        assert parent is panel and path == "relative-target"
        if ambiguous:
            raise ReviewRequired("Control is ambiguous")
        if panel.steps < after:
            raise LookupError("off-screen")
        return target
    monkeypatch.setattr(adapter, "find", find)
    monkeypatch.setattr(adapter, "_find_once", target_find)
    return panel, calls


def scroll_step(**extra):
    return {"operation": "scroll_to", "path": "panel", "target_path": "relative-target", **extra}


def test_scroll_is_scoped_bounded_and_reobserved(setup, monkeypatch):
    panel, calls = panel_setup(setup, monkeypatch)
    setup._navigate_control(scroll_step(), {})
    assert panel.steps == 2 and len(calls) >= 3


def test_visible_target_needs_no_scrolling(setup, monkeypatch):
    panel, _ = panel_setup(setup, monkeypatch, after=0)
    setup._navigate_control(scroll_step(), {})
    assert panel.steps == 0


def test_scroll_limit_is_enforced(setup, monkeypatch):
    panel, _ = panel_setup(setup, monkeypatch, after=20)
    with pytest.raises(ReviewRequired, match="configured limit"):
        setup._navigate_control(scroll_step(max_steps=3), {})
    assert panel.steps == 3


def test_scroll_stall_stops_without_repeating(setup, monkeypatch):
    panel, _ = panel_setup(setup, monkeypatch, moving=False)
    with pytest.raises(ReviewRequired, match="configured limit"):
        setup._navigate_control(scroll_step(), {})
    assert panel.steps == 1


def test_ambiguity_does_not_trigger_scroll(setup, monkeypatch):
    panel, _ = panel_setup(setup, monkeypatch, ambiguous=True)
    with pytest.raises(ReviewRequired, match="ambiguous"):
        setup._navigate_control(scroll_step(), {})
    assert panel.steps == 0


def test_unsupported_scroll_pattern_stops(setup, monkeypatch):
    panel, _ = panel_setup(setup, monkeypatch)
    del panel.iface_scroll
    with pytest.raises(ReviewRequired, match="pattern unavailable"):
        setup._navigate_control(scroll_step(), {})
    assert panel.steps == 0


@pytest.mark.parametrize("limit", [0, 31, True, "8"])
def test_invalid_scroll_limit_stops(setup, limit):
    with pytest.raises(ReviewRequired, match="Invalid bounded"):
        setup._navigate_control(scroll_step(max_steps=limit), {})


def test_queries_cannot_hide_business_writes_in_preparation(setup):
    with pytest.raises(ReviewRequired, match="only select_tab/scroll_to"):
        setup._read({"prepare": [{"operation": "set", "path": "field", "value": "bad"}]}, {})


def test_nested_field_groups_prepare_their_own_tabs(setup, monkeypatch):
    current = [None]
    monkeypatch.setattr(setup, "_navigate_control", lambda step, ctx: current.__setitem__(0, step["path"]))
    monkeypatch.setattr(setup, "_scalar", lambda spec, ctx: current[0])
    result = setup._read({"fields": {
        "billing": {"prepare": [{"operation": "select_tab", "path": "billing"}], "path": "name"},
        "delivery": {"prepare": [{"operation": "select_tab", "path": "delivery"}], "path": "name"},
    }}, {})
    assert result == {"billing": "billing", "delivery": "delivery"}


def test_live_preflight_prepares_window_but_static_check_does_not(setup, monkeypatch):
    setup.profile["calibrated"] = True
    calls = []
    def prepare():
        calls.append("prepared")
        return SimpleNamespace(descendants=lambda **kwargs: [])
    monkeypatch.setattr(setup, "prepare_window", prepare)
    setup.preflight(set(), set(), connect=False)
    assert calls == []
    setup.preflight(set(), set())
    assert calls == ["prepared"]


def test_live_preflight_preserves_unrelated_dirty_editors(setup, monkeypatch):
    setup.profile["calibrated"] = True
    root = SimpleNamespace(descendants=lambda **kwargs: [
        SimpleNamespace(element_info=SimpleNamespace(name="*New Order"))])
    monkeypatch.setattr(setup, "prepare_window", lambda: root)
    with pytest.raises(ReviewRequired, match="Unsaved editors"):
        setup.preflight(set(), set())
