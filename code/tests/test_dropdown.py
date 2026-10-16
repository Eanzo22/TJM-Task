from types import SimpleNamespace

import pytest

from fakturama_cash import ui
from fakturama_cash.errors import ReviewRequired


@pytest.fixture
def dropdown(monkeypatch):
    options = ["Free of Tax", "VAT 19%", "VAT 7%"]
    index, keys = [0], []
    def type_keys(key, **kwargs):
        keys.append(key)
        index[0] = 0 if key == "{HOME}" else index[0] + 1
    control = SimpleNamespace(selected_text=lambda: options[index[0]],
                              set_focus=lambda: None, type_keys=type_keys)
    adapter = ui.UIAAdapter({}, desktop=object())
    monkeypatch.setattr(adapter, "find", lambda *_: control)
    monkeypatch.setattr(adapter, "_combo_options", lambda _: options)
    monkeypatch.setattr(adapter, '_combo_selected_index', lambda _: index[0])
    monkeypatch.setattr(adapter, "_keyboard_safe", lambda _: True)
    monkeypatch.setattr(ui, "wait_stable", lambda observe, **kwargs: observe())
    return adapter, options, control, keys


def test_dropdown_uses_exact_observed_option_and_keyboard_events(dropdown):
    adapter, _, control, keys = dropdown
    adapter._select_option({"path": []}, {}, "VAT 19%")
    assert keys == ["{HOME}", "{DOWN}"]
    assert control.selected_text() == "VAT 19%"


@pytest.mark.parametrize("options", [["VAT 19%", "VAT 19%"], ["VAT 19% reduced"]])
def test_missing_or_duplicate_option_stops_before_input(dropdown, options):
    adapter, observed, _, keys = dropdown
    observed[:] = options
    with pytest.raises(ReviewRequired, match="missing or ambiguous"):
        adapter._select_option({"path": []}, {}, "VAT 19%")
    assert keys == []


def test_dropdown_does_not_retype_an_existing_selection(dropdown):
    adapter, _, _, keys = dropdown
    adapter._select_option({"path": []}, {}, "Free of Tax")
    assert keys == []


def test_dropdown_stops_when_focus_changes(dropdown, monkeypatch):
    adapter, _, _, keys = dropdown
    monkeypatch.setattr(adapter, "_keyboard_safe", lambda _: False)
    with pytest.raises(ReviewRequired, match="focus changed"):
        adapter._select_option({"path": []}, {}, "VAT 19%")
    assert keys == []


def test_vat_code_matches_the_code_not_a_localized_caption(dropdown):
    adapter, options, control, _ = dropdown
    options[:] = ["Z (Zero rated goods)", "S (Standard rate)"]
    adapter._select_option({"path": [], "option_match": "vat_code"}, {}, "S")
    assert control.selected_text() == "S (Standard rate)"


def test_blank_option_is_selected_and_index_verified(dropdown):
    adapter, options, control, keys = dropdown
    options[:] = ['Free of Tax', '']
    adapter._select_option({'path': []}, {}, '')
    assert keys == ['{HOME}', '{DOWN}']
    assert control.selected_text() == ''
    assert adapter._combo_selected_index(control) == 1


def test_blank_text_without_selection_is_not_treated_as_selected(dropdown, monkeypatch):
    adapter, options, control, keys = dropdown
    options[:] = ['Free of Tax', '']
    monkeypatch.setattr(control, 'selected_text', lambda: '')
    indices = iter([-1, 1])
    monkeypatch.setattr(adapter, '_combo_selected_index', lambda _: next(indices))
    adapter._select_option({'path': []}, {}, '')
    assert keys == ['{HOME}', '{DOWN}']


def test_blank_selection_that_does_not_stick_stops(dropdown, monkeypatch):
    adapter, options, control, keys = dropdown
    options[:] = ['Free of Tax', '']
    monkeypatch.setattr(control, 'selected_text', lambda: '')
    monkeypatch.setattr(adapter, '_combo_selected_index', lambda _: -1)
    with pytest.raises(ReviewRequired, match='Blank dropdown option was not selected'):
        adapter._select_option({'path': []}, {}, '')
    assert keys == ['{HOME}', '{DOWN}']


def test_duplicate_blank_options_stop_before_input(dropdown):
    adapter, options, _, keys = dropdown
    options[:] = ['', '']
    with pytest.raises(ReviewRequired, match='missing or ambiguous'):
        adapter._select_option({'path': []}, {}, '')
    assert keys == []
