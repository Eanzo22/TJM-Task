from types import SimpleNamespace
from unittest.mock import Mock
from decimal import Decimal, InvalidOperation

import pytest

from fakturama_cash import clipboard_table, item_table, ui
from fakturama_cash.errors import ReviewRequired
from fakturama_cash.verification import require


@pytest.fixture
def cell_scene(monkeypatch):
    row = dict(sku='T01-TRAY', name='Document Tray', quantity='2.00',
               unit_price='12.5', vat_raw='VAT taxValue: [0.19] VAT 19%',
               discount_raw='0.0', line_price='25.01')
    table = object()
    click = Mock()
    monkeypatch.setattr(clipboard_table, 'copy_table', lambda *a, **kw: [dict(row)])
    monkeypatch.setattr(clipboard_table, 'parse_table', lambda rows, *a, **kw: rows)
    monkeypatch.setattr(item_table, 'visible_cell', lambda *a: (table, (100, 50)))
    monkeypatch.setattr(ui, '_click_control', click)
    adapter = SimpleNamespace(
        profile={'queries': {'items_raw': {'path': [], 'clipboard_rows': {'columns': []}}}},
        timeout=1, find=lambda *a: table, _keyboard_safe=lambda *a: True,
        _type_text=Mock(),
    )
    step = dict(query='items_raw', index=0, sku='T01-TRAY',
                layout={'columns': dict.fromkeys(['quantity', 'name', 'vat', 'unit_price', 'discount'], 100)},
                commit_path=[])
    return adapter, step, row, click


@pytest.mark.parametrize(('column', 'value'), [
    ('unit_price', '12.50'), ('quantity', '2'), ('name', 'Document Tray'),
    ('vat', '19'), ('discount', '0'),
])
def test_matching_unit_price_is_committed_but_other_matching_cells_are_preserved(cell_scene, column, value):
    adapter, step, row, click = cell_scene
    step.update(column=column, value=value)

    def commit(write, context, source_value, **kwargs):
        # Simulate the manually observed recalculation after explicitly entering 12.50.
        assert write['transform'] == 'decimal'
        assert write['decimal_separator'] == ','
        assert kwargs == {'verify_after_blur': False}
        row.update(unit_price=source_value, line_price='25.00')

    adapter._type_text.side_effect = commit
    item_table.edit_cell(adapter, step, {})
    if column == 'unit_price':
        adapter._type_text.assert_called_once()
        assert adapter._type_text.call_args.args[2] == '12.50'
        click.assert_called_once()
        require(item_table.item_values(row), {'unit_net': '12.50', 'source_net': '25.00'}, 'line_2')
    else:
        adapter._type_text.assert_not_called()
        click.assert_not_called()


def test_committed_unit_price_must_still_be_retained(cell_scene):
    adapter, step, row, _ = cell_scene
    step.update(column='unit_price', value='12.50')
    adapter._type_text.side_effect = lambda *a, **kw: row.update(unit_price='12.51')
    with pytest.raises(ReviewRequired, match='Item cell was not retained'):
        item_table.edit_cell(adapter, step, {})


def test_unchanged_line_total_mismatch_is_not_tolerated(cell_scene):
    adapter, step, row, _ = cell_scene
    step.update(column='unit_price', value='12.50')
    # A successful write call alone is not proof that the application's total changed.
    item_table.edit_cell(adapter, step, {})
    adapter._type_text.assert_called_once()
    with pytest.raises(ReviewRequired, match='Displayed or persisted values do not match'):
        require(item_table.item_values(row), {'unit_net': '12.50', 'source_net': '25.00'}, 'line_2')


@pytest.mark.parametrize('fraction, percent', [('-0.125', '12.5'), ('-0.075', '7.5'), ('-0.0125', '1.25')])
def test_fractional_discount_is_read_without_rounding(cell_scene, fraction, percent):
    _, _, row, _ = cell_scene
    row['discount_raw'] = fraction
    assert Decimal(item_table.item_values(row)['discount_percent']) == Decimal(percent)


@pytest.mark.parametrize('fraction', ['NaN', 'Infinity', '-Infinity', '-0,125', 'invalid'])
def test_invalid_copied_discount_is_rejected(cell_scene, fraction):
    _, _, row, _ = cell_scene
    row['discount_raw'] = fraction
    with pytest.raises((ValueError, InvalidOperation)):
        item_table.item_values(row)


@pytest.mark.parametrize('retained', [True, False])
def test_discount_edit_verifies_fractional_readback(cell_scene, retained):
    adapter, step, row, _ = cell_scene
    step.update(column='discount', value='12.5')
    row.update(quantity='3', unit_price='19.99')
    adapter._type_text.side_effect = lambda *a, **kw: row.update(
        discount_raw='-0.125' if retained else '-0.075', line_price='52.47')
    if retained:
        item_table.edit_cell(adapter, step, {})
        require(item_table.item_values(row), {'discount_percent': '12.5', 'source_net': '52.47'}, 'line_1')
    else:
        with pytest.raises(ReviewRequired, match='Item cell was not retained'):
            item_table.edit_cell(adapter, step, {})
    adapter._type_text.assert_called_once()
