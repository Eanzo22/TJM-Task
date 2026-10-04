from types import SimpleNamespace

import pytest

from fakturama_cash import clipboard_table as tables
from fakturama_cash.errors import ReviewRequired


def scene(monkeypatch, rows, *, stuck=False, limit=10):
    position = [0]
    def keys(value, **kwargs):
        if value == '^{HOME}':
            position[0] = 0
        elif value == '^{END}':
            position[0] = len(rows) - 1
        elif not stuck:
            position[0] = min(position[0] + 1, len(rows) - 1)
    control = SimpleNamespace(set_focus=lambda: None, type_keys=keys)
    monkeypatch.setattr(tables, 'copy_table', lambda *a, **kw: rows[position[0]])
    config = {'columns': ['id', 'name'], 'format': 'raw_tsv',
              'row_walk': {'identity': 'id', 'max_rows': limit}}
    return lambda: tables.walk_table(control, config, is_safe=lambda: True, timeout=1)


def test_single_selection_walk_includes_hidden_rows(monkeypatch):
    walk = scene(monkeypatch, ['1\tFirst', '2\tSecond', '3\tLast'])
    assert [r['id'] for r in walk()] == ['1', '2', '3']


def test_ignored_down_does_not_look_like_end_of_results(monkeypatch):
    with pytest.raises(ReviewRequired, match='before the last'):
        scene(monkeypatch, ['1\tFirst', '2\tLast'], stuck=True)()


def test_reused_identity_is_not_deduplicated(monkeypatch):
    with pytest.raises(ReviewRequired, match='identity'):
        scene(monkeypatch, ['1\tFirst', '1\tConflict'])()


def test_bounded_walk_stops_instead_of_returning_partial_data(monkeypatch):
    with pytest.raises(ReviewRequired, match='row limit'):
        scene(monkeypatch, ['1\tFirst', '2\tLast'], limit=1)()
