"""Temporary document expansion must never leak into calibrated table reads."""
from types import SimpleNamespace

import pytest

from fakturama_cash import ui
from fakturama_cash.errors import ReviewRequired


def field(label, kind='order'):
    return [{'control_type': 'Pane', 'title': '${' + kind + '_editor}'},
            {'control_type': 'Edit', 'title': label}]


@pytest.fixture
def layout(monkeypatch):
    adapter = ui.UIAAdapter({'timeout_seconds': .5}, desktop=object())
    state = dict(expanded=False, exposed=False, reveal=True, restore=True, ambiguous=False)
    clicks = []
    now = [0.0]
    monkeypatch.setattr(ui.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(ui.time, 'sleep', lambda t: now.__setitem__(0, now[0] + t))

    def rectangle():
        return SimpleNamespace(left=0, top=0, right=900, bottom=900 if state['expanded'] else 500)

    stack = SimpleNamespace(element_info=SimpleNamespace(control_type='Tab'), rectangle=rectangle)
    pane = SimpleNamespace(parent=lambda: stack)

    def find(path, context, parent=None):
        if parent is not None:
            assert parent is stack
            assert path[0] == {'control_type': 'ToolBar', 'direct': True}
            title = path[-1]['title']
            if title != ('Restore' if state['expanded'] else 'Maximize'):
                raise LookupError(title)
            return SimpleNamespace(title=title, is_enabled=lambda: True)
        if len(path) == 1:
            return pane
        if state['ambiguous']:
            raise ReviewRequired('Control is ambiguous')
        if state['exposed'] or (state['expanded'] and state['reveal']):
            return object()
        raise LookupError('Hidden totals')

    def click(button):
        clicks.append(button.title)
        if button.title == 'Maximize':
            state['expanded'] = True
        elif state['restore']:
            state['expanded'] = False

    monkeypatch.setattr(adapter, '_find_once', find)
    monkeypatch.setattr(ui, '_click_control', click)
    return adapter, state, clicks


def test_existing_totals_do_not_change_layout(layout):
    adapter, state, clicks = layout
    state['exposed'] = True
    with adapter._editor_space([field('Discount')], {}):
        assert not state['expanded']
    assert clicks == []


@pytest.mark.parametrize('kind', ['order', 'invoice'])
def test_missing_totals_expand_once_then_restore(layout, kind):
    adapter, state, clicks = layout
    with adapter._editor_space([field('Discount', kind), field('Total', kind)], {}):
        assert state['expanded']
    assert clicks == ['Maximize', 'Restore']
    assert not state['expanded']


def test_business_failure_restores_without_replaying_write(layout):
    adapter, state, clicks = layout
    with pytest.raises(ReviewRequired, match='write outcome unknown'):
        with adapter._editor_space([field('Discount')], {}):
            raise ReviewRequired('write outcome unknown')
    assert clicks == ['Maximize', 'Restore'] and not state['expanded']


def test_missing_after_expansion_stops_before_body_and_restores(layout):
    adapter, state, clicks = layout
    state['reveal'] = False
    with pytest.raises(ReviewRequired, match='remain unavailable'):
        with adapter._editor_space([field('Discount')], {}):
            pytest.fail('Must not write when the field is still missing')
    assert clicks == ['Maximize', 'Restore'] and not state['expanded']


def test_ambiguous_field_is_not_a_resize_signal(layout):
    adapter, state, clicks = layout
    state['ambiguous'] = True
    with pytest.raises(ReviewRequired, match='ambiguous'):
        with adapter._editor_space([field('Discount')], {}):
            pytest.fail('Ambiguity must stop')
    assert clicks == []


def test_already_maximized_missing_field_does_not_toggle(layout):
    adapter, state, clicks = layout
    state.update(expanded=True, reveal=False)
    with pytest.raises(ReviewRequired, match='cannot be exposed'):
        with adapter._editor_space([field('Discount')], {}):
            pytest.fail('Must not guess a second navigation action')
    assert clicks == []


def test_restore_failure_stops_before_any_table_read(layout, monkeypatch):
    adapter, state, clicks = layout
    state['restore'] = False
    def scalar(spec, context):
        assert spec['path'] != 'table', 'An un-restored layout must not reach the table'
        return '0'
    monkeypatch.setattr(adapter, '_scalar', scalar)
    spec = {'fields': {'discount': {'path': field('Discount')}, 'items': {'path': 'table'}}}
    with pytest.raises(ReviewRequired, match='original layout'):
        adapter._read(spec, {})
    assert clicks == ['Maximize', 'Restore']


@pytest.mark.parametrize('kind', ['order', 'invoice'])
def test_table_is_read_only_after_totals_layout_is_restored(layout, monkeypatch, kind):
    adapter, state, clicks = layout
    def scalar(spec, context):
        if spec['path'] == 'table':
            assert not state['expanded'] and clicks == ['Maximize', 'Restore']
            return ['row']
        assert state['expanded']
        return '0'
    monkeypatch.setattr(adapter, '_scalar', scalar)
    spec = {'fields': {'discount': {'path': field('Discount', kind)},
                       'total': {'path': field('Total', kind)}, 'items': {'path': 'table'}}}
    assert adapter._read(spec, {}) == {'discount': '0', 'total': '0', 'items': ['row']}


def test_totals_action_is_wrapped_and_other_actions_are_not(layout, monkeypatch):
    adapter, state, clicks = layout
    recipe = [{'operation': 'type_text', 'path': field('Discount')}]
    adapter.profile['actions'] = {'fill_order_totals': recipe, 'save_order': recipe}
    calls = []
    def act(name, steps, context):
        calls.append(name)
        assert steps == recipe
        assert state['expanded'] == (name == 'fill_order_totals')
    monkeypatch.setattr(adapter, '_act_recipe', act)
    adapter.act('fill_order_totals', {})
    adapter.act('save_order', {})
    assert calls == ['fill_order_totals', 'save_order']
    assert clicks == ['Maximize', 'Restore']


def test_unrelated_master_fields_never_expand(layout, monkeypatch):
    adapter, _, clicks = layout
    monkeypatch.setattr(adapter, '_scalar', lambda *args: '19')
    assert adapter._read({'fields': {'vat': {'path': [{'control_type': 'Pane', 'title': 'Product'}]}}}, {}) == {'vat': '19'}
    assert clicks == []


def test_mixed_editors_rejected_before_navigation(layout):
    adapter, _, clicks = layout
    with pytest.raises(ReviewRequired, match='one mapped document editor'):
        with adapter._editor_space([field('Discount'), field('Discount', 'invoice')], {}):
            pytest.fail('Mixed editors must not resize')
    assert clicks == []
