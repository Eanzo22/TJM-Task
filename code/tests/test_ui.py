import pytest

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.ui import UIAAdapter, resolve, wait_stable
from fakturama_cash.workflow import ACTIONS, QUERIES


class Clock:
    def __init__(self):
        self.now = 0
    def time(self):
        return self.now
    def sleep(self, value):
        self.now += value


def test_wait_until_results_stable():
    clock = Clock()
    results = iter([[], [{"sku": "A"}], [{"sku": "A"}], [{"sku": "A"}], [{"sku": "A"}]])
    assert wait_stable(lambda: next(results), timeout=1, interval=0.1, stable_for=0.2,
                       clock=clock.time, sleep=clock.sleep) == [{"sku": "A"}]


def test_unstable_results_timeout():
    clock = Clock()
    with pytest.raises(ReviewRequired, match="stable state"):
        wait_stable(lambda: clock.now, timeout=0.5, interval=0.1,
                    clock=clock.time, sleep=clock.sleep)


def test_incomplete_profile_cannot_start():
    adapter = UIAAdapter({"calibrated": False}, desktop=object())
    with pytest.raises(ReviewRequired, match="not fully calibrated"):
        adapter.preflight(ACTIONS, QUERIES)


def test_template_is_lookup_not_eval():
    assert resolve("${input.items.0.sku}", {"input": {"items": [{"sku": "A"}]}}) == "A"
    assert resolve("__import__('os').system('bad')", {}) == "__import__('os').system('bad')"


def test_complete_profile_check_does_not_connect():
    profile = {"calibrated": True, "actions": {"example": [{}]}, "queries": {"value": {"path": []}}}
    UIAAdapter(profile, desktop=object()).preflight({"example"}, {"value"}, connect=False)


def test_discovery_retries_only_missing_observation(monkeypatch):
    from fakturama_cash import ui
    clock = Clock()
    monkeypatch.setattr(ui.time, "monotonic", clock.time)
    monkeypatch.setattr(ui.time, "sleep", clock.sleep)
    adapter = UIAAdapter({"timeout_seconds": 1}, desktop=object())
    attempts = []
    control = object()
    def observe(*_):
        attempts.append(None)
        if len(attempts) < 3:
            raise LookupError("not visible yet")
        return control
    monkeypatch.setattr(adapter, "_find_once", observe)
    assert adapter.find([{"title": "observed name"}], {}) is control
    assert len(attempts) == 3


def test_native_modal_binding_handles_hidden_shell_and_rejects_other_process(monkeypatch):
    from types import SimpleNamespace
    from fakturama_cash import ui
    import win32process
    modal = SimpleNamespace(element_info=SimpleNamespace(control_type='Window',name='Select a product'),
                            is_visible=lambda:False)
    root = SimpleNamespace(descendants=lambda **kw:[],process_id=lambda:42)
    desktop = SimpleNamespace(window=lambda handle:SimpleNamespace(wrapper_object=lambda:modal))
    adapter=UIAAdapter({},desktop=desktop)
    adapter._native_discovery=True
    monkeypatch.setattr(adapter,'root',lambda:root)
    monkeypatch.setattr(ui,'_matching_window_handles',lambda pattern:[13,14])
    monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda h:(1,42 if h==13 else 99))
    assert adapter._find_once([dict(control_type='Window',title='Select a product')],{}) is modal


def test_ambiguous_discovery_is_not_retried(monkeypatch):
    adapter = UIAAdapter({}, desktop=object())
    attempts = []
    def observe(*_):
        attempts.append(None)
        raise ReviewRequired("ambiguous")
    monkeypatch.setattr(adapter, "_find_once", observe)
    with pytest.raises(ReviewRequired, match="ambiguous"):
        adapter.find([{"title": "repeated label"}], {})
    assert len(attempts) == 1


def test_root_binds_once_but_does_not_retarget_after_close(monkeypatch):
    import sys
    from types import SimpleNamespace
    alive = [True]
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace(
        IsWindow=lambda handle: alive[0], IsWindowVisible=lambda handle: True))
    calls = []
    window = SimpleNamespace(handle=123, window_text=lambda: "Fakturama - test")
    def windows(**kwargs):
        calls.append(kwargs)
        return [window]
    adapter = UIAAdapter({"window_title_re": "^Fakturama - .*"}, desktop=SimpleNamespace(windows=windows))
    assert adapter.root() is window
    assert adapter.root() is window
    assert len(calls) == 1 and calls[0]["visible_only"] is False
    alive[0] = False
    with pytest.raises(ReviewRequired, match="closed or changed"):
        adapter.root()
    assert len(calls) == 1


@pytest.mark.parametrize("condition", [{"when": False}, {"unless": True}])
def test_false_address_branch_does_not_discover_or_mutate_a_control(monkeypatch, condition):
    adapter = UIAAdapter({"actions": {"delivery": [
        {"operation": "invoke", "path": [], **condition}]}}, desktop=object())
    monkeypatch.setattr(adapter, "find", lambda *args: pytest.fail("Skipped address branch"))
    adapter.act("delivery", {})


def test_conditions_do_not_treat_text_as_boolean(monkeypatch):
    adapter = UIAAdapter({"actions": {"delivery": [
        {"operation": "invoke", "path": [], "when": "false"}]}}, desktop=object())
    monkeypatch.setattr(adapter, "find", lambda *args: pytest.fail("Invalid condition"))
    with pytest.raises(ReviewRequired, match="must be boolean"):
        adapter.act("delivery", {})


def test_default_payment_flag_compares_two_observed_fields(monkeypatch):
    adapter = UIAAdapter({}, desktop=object())
    values = {"standard": "Cash", "name": "Bank Transfer"}
    monkeypatch.setattr(adapter, "_scalar", lambda spec, ctx: values[spec["path"]])
    query = {"same_text": [{"path": "standard"}, {"path": "name"}]}
    assert adapter._read(query, {}) is False
    values["name"] = " Cash "
    assert adapter._read(query, {}) is True
