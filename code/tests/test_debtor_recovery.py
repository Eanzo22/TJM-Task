"""Recovery checks with simulated controls, never a live contact or Save."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fakturama_cash import debtor_recovery, ui
from fakturama_cash.errors import ReviewRequired


@pytest.fixture
def scene(monkeypatch):
    checked = [True]
    keys = []
    field = SimpleNamespace(is_enabled=lambda: True, type_keys=lambda key, **kw: keys.append(key))
    def press(key, **kwargs):
        keys.append(key)
        if key == '{SPACE}':
            checked[0] = not checked[0]
    table = SimpleNamespace(type_keys=press)
    native = Mock()
    native.item_count.return_value = 1
    native.get_item.return_value.text.return_value = 'New Debtor'
    native.get_item.return_value.is_checked.side_effect = lambda: checked[0]
    tab = SimpleNamespace(window_text=lambda: '*New Debtor', is_selected=lambda: True)
    ok = Mock()
    step = dict(operation='discard_debtor_draft', path='field', tab_path='tab',
                save_dialog=[{'control_type': 'Window', 'title': 'Save Parts'}], wait_absent='editor')
    adapter = ui.UIAAdapter({'actions': {'discard_debtor_draft': [step]}}, desktop=object())
    def find(path, context):
        if path == 'field':
            return field
        if path == 'tab':
            return tab
        return table if path[-1]['control_type'] == 'List' else ok
    monkeypatch.setattr(adapter, 'find', find)
    monkeypatch.setattr(adapter, '_keyboard_safe', lambda c: True)
    def wait(predicate, message):
        if not predicate():
            raise ReviewRequired(message)
    monkeypatch.setattr(adapter, '_wait_for', wait)
    absent = Mock()
    monkeypatch.setattr(adapter, '_wait_absent', absent)
    monkeypatch.setattr(debtor_recovery, 'focus_table', lambda *a: None)
    monkeypatch.setattr(debtor_recovery, '_native_save_list', lambda c: native)
    return adapter, native, tab, ok, checked, keys, absent


@pytest.mark.parametrize('checked_initially', [True, False])
def test_discard_unchecks_only_draft_and_verifies_dialog_and_editor_closed(scene, checked_initially):
    adapter, _, _, ok, checked, keys, absent = scene
    checked[0] = checked_initially
    adapter.act('discard_debtor_draft', {'debtor_editor': 'New Debtor'})
    assert keys == (['^w', '{HOME}', '{SPACE}'] if checked_initially else ['^w'])
    assert checked[0] is False
    ok.invoke.assert_called_once()
    assert absent.call_count == 2
    assert absent.call_args.args[0] == 'editor'


@pytest.mark.parametrize('problem', ['extra_parts', 'wrong_part', 'checked', 'saved_tab', 'inactive_tab', 'wrong_editor'])
def test_unsafe_close_does_not_accept_save_dialog(scene, problem):
    adapter, native, tab, ok, _, keys, _ = scene
    context = {'debtor_editor': 'New Debtor'}
    if problem == 'extra_parts':
        native.item_count.return_value = 2
    elif problem == 'wrong_part':
        native.get_item.return_value.text.return_value = 'New Order'
    elif problem == 'checked':
        native.get_item.return_value.is_checked.side_effect = lambda: True
    elif problem == 'saved_tab':
        tab.window_text = lambda: 'Saved Contact'
    elif problem == 'inactive_tab':
        tab.is_selected = lambda: False
    else:
        context['debtor_editor'] = 'Saved Contact'
    with pytest.raises(ReviewRequired):
        adapter.act('discard_debtor_draft', context)
    ok.invoke.assert_not_called()
    if problem in ('saved_tab', 'inactive_tab', 'wrong_editor'):
        assert keys == []


def test_focus_loss_does_not_close_another_editor(scene, monkeypatch):
    adapter, _, _, ok, _, keys, _ = scene
    monkeypatch.setattr(adapter, '_keyboard_safe', lambda c: False)
    with pytest.raises(ReviewRequired, match='focus changed'):
        adapter.act('discard_debtor_draft', {'debtor_editor': 'New Debtor'})
    assert keys == []
    ok.invoke.assert_not_called()


@pytest.mark.parametrize('source', ['component', 'live', 'generated'])
def test_recovery_mapping_is_available_without_table_recalibration(source, monkeypatch):
    import json
    import runpy
    from pathlib import Path
    code = Path(__file__).resolve().parents[1]
    if source == 'generated':
        monkeypatch.chdir(code)
        profile = runpy.run_path(str(code / 'scripts/build_live_profile.py'))['build']()
    else:
        filename = 'master-forms.partial.json' if source == 'component' else 'live-profile.json'
        profile = json.loads((code / 'config' / filename).read_text(encoding='utf-8'))
    step, = profile['actions']['discard_debtor_draft']
    assert step['operation'] == 'discard_debtor_draft'
    assert step['save_dialog'] == [{'control_type': 'Window', 'title': 'Save Parts'}]
    assert step['wait_absent'] == [{'control_type': 'Pane', 'title': '${debtor_editor}'}]
