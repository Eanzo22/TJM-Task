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


@pytest.mark.parametrize('state, expected', [(0, ['expand']), (1, []), (3, ['invoke']),
                                            ('missing', ['invoke'])])
def test_menu_selection_uses_menu_patterns(monkeypatch, state, expected):
    from types import SimpleNamespace
    from pywinauto.uia_defines import NoPatternInterfaceError
    calls = []

    def expand_state():
        if state == 'missing':
            raise NoPatternInterfaceError()
        return state

    control = SimpleNamespace(
        element_info=SimpleNamespace(control_type='MenuItem'), is_enabled=lambda: True,
        get_expand_state=expand_state, expand=lambda: calls.append('expand'),
        invoke=lambda: calls.append('invoke'),
        select=lambda: pytest.fail('Menus must not use the SelectionItem pattern'))
    adapter = UIAAdapter({'actions': {'inspect_environment': [
        {'operation': 'select', 'path': [{'control_type': 'MenuItem', 'title': 'File'}]}]}}, desktop=object())
    monkeypatch.setattr(adapter, 'find', lambda *args: control)
    adapter.act('inspect_environment', {})
    assert calls == expected


@pytest.mark.parametrize('state', [0, 3])
def test_menu_com_failure_names_step_and_never_replays(monkeypatch, state):
    from types import SimpleNamespace
    from comtypes import COMError
    calls = []

    def fail(operation):
        calls.append(operation)
        raise COMError(-2146233079, None, (None, None, None, 0, None))

    menu = SimpleNamespace(
        element_info=SimpleNamespace(control_type='MenuItem'), is_enabled=lambda: True,
        get_expand_state=lambda: state, expand=lambda: fail('expand'), invoke=lambda: fail('invoke'))
    path = [{'control_type': 'MenuItem', 'title': 'Preferences'}]
    adapter = UIAAdapter({'actions': {'inspect_environment': [
        {'operation': 'select', 'path': [], 'when': False},
        {'operation': 'select', 'path': path}]}}, desktop=object())
    monkeypatch.setattr(adapter, 'find', lambda *args: menu)
    with pytest.raises(ReviewRequired, match='Selection step 2 failed: COMError') as error:
        adapter.act('inspect_environment', {})
    assert error.value.details['stage'] == 'inspect_environment'
    assert error.value.details['expected'] == path
    assert isinstance(error.value.__cause__, COMError)
    assert calls == (['expand'] if state == 0 else ['invoke'])


@pytest.mark.parametrize('control_type, value, expected', [('TreeItem', None, ()), ('ComboBox', 'EUR', ('EUR',))])
def test_non_menu_selection_is_unchanged(monkeypatch, control_type, value, expected):
    from types import SimpleNamespace
    calls = []
    control = SimpleNamespace(element_info=SimpleNamespace(control_type=control_type),
                              is_enabled=lambda: True, select=lambda *args: calls.append(args))
    adapter = UIAAdapter({'actions': {'select_test': [
        {'operation': 'select', 'path': [], 'value': value}]}}, desktop=object())
    monkeypatch.setattr(adapter, 'find', lambda *args: control)
    adapter.act('select_test', {})
    assert calls == [expected]


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


def test_transient_missing_foreground_is_an_unsafe_observation(monkeypatch):
    """Closing the calibration review must not call GetAncestor with HWND 0."""
    import sys
    from types import SimpleNamespace
    from fakturama_cash import ui

    monkeypatch.setattr(ui, '_foreground_handle', lambda: 0)
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(
        IsWindow=lambda handle: handle == 43,
        GetAncestor=lambda handle, flag: pytest.fail('GetAncestor must not receive HWND 0'),
        IsChild=lambda *args: False))
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(
        GetWindowThreadProcessId=lambda handle: pytest.fail('A missing foreground has no process')))
    control = SimpleNamespace(handle=43, has_keyboard_focus=lambda: True,
                              is_enabled=lambda: True, process_id=lambda: 7)

    assert UIAAdapter({}, desktop=object())._keyboard_safe(control) is False


def test_native_root_handles_disappearance_between_validation_and_lookup(monkeypatch):
    """A handle can close after IsWindow succeeds but before GetAncestor."""
    import sys
    from types import SimpleNamespace
    from fakturama_cash import ui

    class InvalidHandle(Exception):
        winerror = 1400

    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(
        IsWindow=lambda handle: True,
        GetAncestor=lambda handle, flag: (_ for _ in ()).throw(InvalidHandle())))

    assert ui._native_root_handle(43) is None


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
