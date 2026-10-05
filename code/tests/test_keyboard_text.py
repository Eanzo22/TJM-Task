from types import SimpleNamespace

import pytest

from fakturama_cash import ui
from fakturama_cash.errors import ReviewRequired


@pytest.fixture
def scene(monkeypatch):
    keys = []
    focused = [None]
    field = SimpleNamespace(element_info=SimpleNamespace(control_type="Edit"),
                            is_enabled=lambda: True, get_value=lambda: "Saved text")
    commit = SimpleNamespace(is_enabled=lambda: True, has_keyboard_focus=lambda: focused[0] == "commit",
                             set_focus=lambda: focused.__setitem__(0, "commit"))
    field.set_focus = lambda: focused.__setitem__(0, "field")
    field.type_keys = lambda text, **kwargs: keys.append(text)
    adapter = ui.UIAAdapter({}, desktop=object())
    monkeypatch.setattr(adapter, "find", lambda path, context: {"field": field, "commit": commit}[path])
    monkeypatch.setattr(adapter, "_keyboard_safe", lambda c: focused[0] == ("field" if c is field else "commit"))
    monkeypatch.setattr(ui, "wait_stable", lambda observe, **kwargs: observe())
    step = {"operation": "type_text", "path": "field", "commit_path": "commit"}
    return adapter, step, field, keys, focused


def test_text_commits_by_blurring_and_reads_retained_value(scene):
    adapter, step, _, keys, focused = scene
    adapter._type_text(step, {}, "Saved text")
    assert keys == ["^a", "Saved text"]
    assert focused[0] == "commit"


def test_value_reverted_on_blur_is_not_a_success(scene):
    adapter, step, _, _, _ = scene
    with pytest.raises(ReviewRequired, match="not retained"):
        adapter._type_text(step, {}, "Ignored text")


@pytest.mark.parametrize('dirty', [False, True])
def test_close_requires_clean_selected_tab_and_verifies_disappearance(scene, monkeypatch, dirty):
    adapter, _, field, keys, _ = scene
    tab=SimpleNamespace(window_text=lambda:'*INV1' if dirty else 'INV1',is_selected=lambda:True)
    adapter.profile['actions']={'close':[dict(operation='close_clean_editor',path='field',tab_path='tab',wait_absent='editor')]}
    monkeypatch.setattr(adapter,'find',lambda path,ctx:field if path=='field' else tab)
    absent=[]
    monkeypatch.setattr(adapter,'_wait_absent',lambda path,ctx:absent.append(path))
    if dirty:
        with pytest.raises(ReviewRequired,match='clean and selected'):
            adapter.act('close',{})
        assert keys==[] and absent==[]
    else:
        adapter.act('close',{})
        assert keys==['^w'] and absent==['editor']


def test_set_search_uses_value_pattern_without_dialog_keyboard_shortcuts(scene, monkeypatch):
    adapter, step, field, keys, _ = scene
    values = ['']
    field.set_edit_text = lambda value: values.__setitem__(0, value)
    monkeypatch.setattr(adapter, '_scalar', lambda *args: values[0])
    adapter.profile['actions'] = {'search': [dict(operation='set_search',path='field',value='SKU-003')]}
    adapter.act('search',{})
    assert values[0]=='SKU-003' and keys==[]


def test_failed_search_value_assignment_stops_before_matching_records(scene, monkeypatch):
    adapter, _, field, keys, _ = scene
    field.set_edit_text = lambda value: None
    monkeypatch.setattr(adapter, '_scalar', lambda *args: 'OLD SEARCH')
    adapter.profile['actions']={'search':[dict(operation='set_search',path='field',value='SKU-003')]}
    with pytest.raises(ReviewRequired,match='not retained'):
        adapter.act('search',{})
    assert keys==[]


@pytest.mark.parametrize('profile_source', ['component', 'live', 'generated'])
def test_product_search_recipe_does_not_accept_or_reopen_dialog(scene, monkeypatch, profile_source):
    import json
    import runpy
    from pathlib import Path

    adapter, _, field, keys, focused = scene
    code = Path(__file__).resolve().parents[1]
    if profile_source == 'generated':
        monkeypatch.chdir(code)
        profile = runpy.run_path(str(code / 'scripts/build_live_profile.py'))['build']()
    else:
        filename = 'selectors.partial.json' if profile_source == 'component' else 'live-profile.json'
        profile = json.loads((code / 'config' / filename).read_text(encoding='utf-8'))
    adapter.profile = profile
    path = profile['actions']['search_product'][0]['path']
    values = ['OLD SEARCH']

    def find(actual_path, context):
        # Opening/accepting the dialog or focusing its Cancel button is forbidden
        # during search. Only the same scoped Search Edit may be accessed.
        assert actual_path == path
        return field

    def type_keys(value, **kwargs):
        assert kwargs['set_foreground'] is False
        keys.append(value)
        if value != '^a':
            values[0] = value

    monkeypatch.setattr(adapter, 'find', find)
    monkeypatch.setattr(adapter, '_find_once', find)
    monkeypatch.setattr(adapter, '_scalar', lambda *args: values[0])
    field.type_keys = type_keys
    for _ in range(2):
        adapter.act('search_product', {'line': {'sku': 'CHR-ERG-01'}})
    assert values[0] == 'CHR-ERG-01' and keys == ['^a', 'CHR-ERG-01']
    assert focused[0] == 'field'


@pytest.fixture
def search_scene(scene, monkeypatch):
    adapter, _, field, keys, focused = scene
    value = ['']
    adapter.profile['actions'] = {'search_product': [dict(operation='type_search',
        path='field', value='SKU-003', read='native_text')]}
    monkeypatch.setattr(adapter, '_find_once', lambda path, ctx: field)
    monkeypatch.setattr(adapter, '_scalar', lambda *args: value[0])

    def type_keys(text, **kwargs):
        keys.append(text)
        if text == 'SKU-003':
            value[0] = text

    field.type_keys = type_keys
    return adapter, field, keys, focused, value


def test_reopened_search_uses_keyboard_when_value_pattern_does_not_persist(search_scene):
    adapter, field, keys, focused, value = search_scene
    field.set_edit_text = lambda text: None  # Reproduces the ignored SetValue.
    adapter.act('search_product', {})
    assert value[0] == 'SKU-003' and keys == ['^a', 'SKU-003']
    assert focused[0] == 'field'


def test_search_focus_loss_after_select_all_stops_before_sku(search_scene):
    adapter, field, keys, focused, _ = search_scene

    def lose_focus(text, **kwargs):
        keys.append(text)
        focused[0] = None

    field.type_keys = lose_focus
    with pytest.raises(ReviewRequired, match='focus changed'):
        adapter.act('search_product', {})
    assert keys == ['^a']


def test_search_dialog_disappearance_stops_without_reopening(search_scene, monkeypatch):
    adapter, field, keys, _, _ = search_scene

    def field_present(path, context):
        if keys:
            raise LookupError('dialog closed')
        return field

    monkeypatch.setattr(adapter, '_find_once', field_present)
    with pytest.raises(ReviewRequired, match='disappeared'):
        adapter.act('search_product', {})
    assert keys == ['^a']


def test_search_reacquires_replaced_provider_before_typing_sku(search_scene, monkeypatch):
    adapter, original, keys, _, value = search_scene
    replacement = SimpleNamespace(element_info=SimpleNamespace(control_type='Edit'), is_enabled=lambda: True)

    def replacement_keys(text, **kwargs):
        assert text == 'SKU-003' and kwargs['set_foreground'] is False
        keys.append(text)
        value[0] = text

    replacement.type_keys = replacement_keys
    monkeypatch.setattr(adapter, '_find_once', lambda *args: replacement if keys else original)
    monkeypatch.setattr(adapter, '_keyboard_safe', lambda control: True)
    adapter.act('search_product', {})
    assert keys == ['^a', 'SKU-003'] and value[0] == 'SKU-003'


def test_ignored_search_keys_stop_without_repeated_entry(search_scene):
    adapter, field, keys, _, _ = search_scene
    field.type_keys = lambda text, **kwargs: keys.append(text)
    with pytest.raises(ReviewRequired, match='not retained') as error:
        adapter.act('search_product', {})
    assert error.value.details['observed'] == ''
    assert keys == ['^a', 'SKU-003']


@pytest.mark.parametrize('bad', ['newline', 'commit_button', 'value_read', 'not_text'])
def test_invalid_search_recipe_sends_no_keys(search_scene, bad):
    adapter, _, keys, focused, _ = search_scene
    step = adapter.profile['actions']['search_product'][0]
    if bad == 'newline':
        step['value'] = 'SKU\n003'
    elif bad == 'commit_button':
        step['commit_path'] = 'commit'
    elif bad == 'value_read':
        step['read'] = 'value'
    else:
        step['value'] = None
    with pytest.raises(ReviewRequired, match='Search needs plain text'):
        adapter.act('search_product', {})
    assert keys == [] and focused[0] is None


def test_search_shortcut_characters_are_literal(search_scene):
    adapter, field, keys, _, value = search_scene
    step = adapter.profile['actions']['search_product'][0]
    step['value'] = 'SKU+^%~(){}'

    def type_keys(text, **kwargs):
        keys.append(text)
        if text != '^a':
            value[0] = 'SKU+^%~(){}'

    field.type_keys = type_keys
    adapter.act('search_product', {})
    assert keys == ['^a', 'SKU{+}{^}{%}{~}{(}{)}{{}{}}']


def test_shortcut_metacharacters_are_literal(scene):
    adapter, step, field, keys, _ = scene
    field.get_value = lambda: "A+^%~(){}"
    adapter._type_text(step, {}, "A+^%~(){}")
    assert keys[1] == "A{+}{^}{%}{~}{(}{)}{{}{}}"


@pytest.mark.parametrize("input_value", ["10", "10,00"])
def test_currency_read_back_normalizes_formatted_euros(scene, input_value):
    adapter, step, field, _, _ = scene
    step["transform"] = "decimal"
    field.get_value = lambda: "10,00 €"
    adapter._type_text(step, {}, input_value)


def test_decimal_keyboard_format_matches_the_observed_editor_locale(scene):
    adapter, step, field, keys, _ = scene
    step.update(transform="decimal", decimal_separator=",")
    field.get_value = lambda: "12,50 €"
    adapter._type_text(step, {}, "12.50")
    assert keys == ["^a", "12,50"]


@pytest.mark.parametrize("bad", ["newline", "transform", "read", "same_commit"])
def test_bad_text_recipe_rejected_before_keys(scene, bad):
    adapter, step, _, keys, _ = scene
    value = "Saved text"
    if bad == "newline":
        value = "not\na shortcut"
    elif bad == "transform":
        step["transform"] = "unknown"
    elif bad == "read":
        step["read"] = "unknown"
    else:
        step["commit_path"] = "field"
    with pytest.raises(ReviewRequired):
        adapter._type_text(step, {}, value)
    assert keys == []


def test_swt_search_retains_native_text_when_uia_value_is_blank_on_blur(scene, monkeypatch):
    import sys
    adapter, step, field, _, focused = scene
    field.handle = 123
    field.class_name = lambda: "Edit"
    field.get_value = lambda: "Saved text" if focused[0] == "field" else ""
    def native(handle):
        assert handle == field.handle
        return SimpleNamespace(window_text=lambda: "Saved text")
    monkeypatch.setitem(sys.modules, "pywinauto.controls.hwndwrapper", SimpleNamespace(HwndWrapper=native))
    step["read"] = "native_text"
    adapter._type_text(step, {}, "Saved text")
    assert field.get_value() == ""
    assert focused[0] == "commit"


@pytest.mark.parametrize("safe", [True, False])
def test_popup_escape_requires_current_focus_and_verified_disappearance(scene, monkeypatch, safe):
    adapter, _, _, keys, _ = scene
    adapter.profile['actions'] = {'close': [{'operation': 'dismiss_popup',
        'path': 'field', 'wait_absent': 'popup'}]}
    monkeypatch.setattr(adapter, '_keyboard_safe', lambda c: safe)
    def absent(path, context):
        assert keys == ['{ESC}']
        raise LookupError()
    monkeypatch.setattr(adapter, '_find_once', absent)
    if safe:
        adapter.act('close', {})
        assert keys == ['{ESC}']
    else:
        with pytest.raises(ReviewRequired, match='focus changed'):
            adapter.act('close', {})
        assert keys == []
