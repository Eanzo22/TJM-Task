"""Synthetic regression checks for the inaccessible grids observed in Fakturama.

No live desktop or master-data writes. A blank UIA tree is deliberately modeled
separately from an explicit, calibrated zero-result indication.
"""
from types import SimpleNamespace

import pytest

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.matching import exact_match
from fakturama_cash.state import Journal, semantic_fingerprint
from fakturama_cash.ui import UIAAdapter
from fakturama_cash.workflow import Workflow
from fake_ui import FakeUI


class Cell:
    def __init__(self, name, value):
        self.element_info = SimpleNamespace(name=name, control_type="Edit")
        self.value = value

    def get_value(self):
        return self.value


class Row:
    def __init__(self, *cells):
        self.cells = cells

    def children(self):
        return self.cells


class Table:
    rows = ()

    def descendants(self, control_type):
        assert control_type == "DataItem"
        return self.rows


@pytest.fixture
def grid(monkeypatch):
    table = Table()
    count = Cell("Result count", "0")
    status = Cell("Result status", "Loading")
    controls = {"table": table, "count": count, "status": status}
    adapter = UIAAdapter({}, desktop=object())
    monkeypatch.setattr(adapter, "find", lambda path, context: controls[path[0]["title"]])
    spec = {"path": [{"title": "table"}], "rows": {"columns": {"sku": "Item No."}}}
    return adapter, spec, table, count, status


def test_inaccessible_table_is_not_an_empty_result(grid):
    adapter, spec, *_ = grid
    with pytest.raises(ReviewRequired, match="no accessible rows"):
        adapter._read(spec, {})


@pytest.mark.parametrize("observed", ["Loading", "", "1 result"])
def test_unconfirmed_empty_table_stops(grid, observed):
    adapter, spec, _, _, status = grid
    status.value = observed
    spec.update(empty_indicator={"path": [{"title": "status"}]}, empty_text="0 results")
    with pytest.raises(ReviewRequired, match="Cannot distinguish empty"):
        adapter._read(spec, {})


def test_only_explicit_calibrated_zero_results_allows_empty(grid):
    adapter, spec, _, _, status = grid
    # This indicator is synthetic; neither live selector currently exposes it.
    status.value = "0 results"
    spec.update(empty_indicator={"path": [{"title": "status"}]}, empty_text="0 results")
    assert adapter._read(spec, {}) == []


@pytest.mark.parametrize("reported_count", [None, "2"])
def test_visible_subset_cannot_be_used_as_complete_results(grid, reported_count):
    adapter, spec, table, count, _ = grid
    table.rows = [Row(Cell("Item No.", "SYNTHETIC-SKU"))]
    if reported_count is not None:
        count.value = reported_count
        spec["total_count"] = {"path": [{"title": "count"}]}
    with pytest.raises(ReviewRequired, match="Cannot prove all result rows"):
        adapter._read(spec, {})


@pytest.mark.parametrize("cell_count", [0, 2])
def test_missing_or_ambiguous_column_stops(grid, cell_count):
    adapter, spec, table, count, _ = grid
    table.rows = [Row(*(Cell("Item No.", "SYNTHETIC-SKU") for _ in range(cell_count)))]
    count.value = "1"
    spec["total_count"] = {"path": [{"title": "count"}]}
    with pytest.raises(ReviewRequired, match="Grid cells require calibration"):
        adapter._read(spec, {})


def test_complete_duplicate_rows_reach_matching_without_deduplication(grid):
    adapter, spec, table, count, _ = grid
    table.rows = [Row(Cell("Item No.", "SYNTHETIC-SKU")) for _ in range(2)]
    count.value = "2"
    spec["total_count"] = {"path": [{"title": "count"}]}
    rows = adapter._read(spec, {})
    assert rows == [{"sku": "SYNTHETIC-SKU"}, {"sku": "SYNTHETIC-SKU"}]
    with pytest.raises(ReviewRequired, match="Ambiguous or conflicting"):
        exact_match(rows, {"sku": "SYNTHETIC-SKU"}, identity="sku")


@pytest.mark.parametrize("query", ["debtor_results", "product_results"])
def test_unreadable_selector_stops_before_master_creation_or_document_save(grid, order, tmp_path, query):
    adapter, spec, *_ = grid

    class UnreadableSelector(FakeUI):
        def read(self, name, context):
            if name == query:
                return adapter._read(spec, context)
            return super().read(name, context)

    ui = UnreadableSelector(order, existing=True)
    with Journal(tmp_path, "synthetic-inaccessible-grid", semantic_fingerprint(order)) as journal:
        with pytest.raises(ReviewRequired, match="no accessible rows"):
            Workflow(ui, journal).run(order)
    assert not set(ui.actions) & {
        "new_debtor", "new_payment", "new_product", "new_vat", "select_product",
        "save_order", "create_linked_invoice", "save_invoice",
    }
