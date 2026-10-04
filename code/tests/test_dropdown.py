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
