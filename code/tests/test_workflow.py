import json

import pytest

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.models import OrderInput
from fakturama_cash.matching import payment_definition
from fakturama_cash.state import Journal, semantic_fingerprint
from fakturama_cash.workflow import Workflow
from fake_ui import FakeUI


def run(order, ui, tmp_path, image="imagehash"):
    with Journal(tmp_path, image, semantic_fingerprint(order)) as journal:
        return Workflow(ui, journal).run(order)


@pytest.mark.parametrize("existing", [True, False])
def test_continuous_flow(order, tmp_path, existing):
    ui = FakeUI(order, existing=existing)
    assert run(order, ui, tmp_path) == {"order": "TEST-ORDER-01", "invoice": "TEST-INVOICE-01"}
    assert len(ui.order["items"]) == 2
    assert ui.invoice["order_no"] == ui.order["no"]
    assert ui.invoice["value"] == order.source_total
    assert ui.actions.count("save_order") == ui.actions.count("save_invoice") == 1
    assert ui.actions.count("create_linked_invoice") == 1
    assert ui.actions.count("select_product") == 2
    if not existing:
        assert ui.actions.index("save_payment") < ui.actions.index("new_debtor")
        assert ui.actions.index("save_vat") < ui.actions.index("new_product")
        assert ui.actions.count("save_vat") == 1
        assert ui.debtor["separate_delivery"] is True
        assert ui.debtor["customer_id"] == "TEST-CUSTOMER-01"


def test_unpaid_same_address(payload, tmp_path):
    payload["payment"].update(status="UNPAID", date=None)
    payload["debtor"]["delivery"] = payload["debtor"]["billing"]
    order = OrderInput.model_validate(payload)
    ui = FakeUI(order)
    run(order, ui, tmp_path)
    assert ui.invoice["paid"] is False
    assert ui.invoice["payment_date"] is None and ui.invoice["value"] is None
    assert ui.debtor["separate_delivery"] is False


@pytest.mark.parametrize("action", ["save_order", "save_invoice", "save_product", "select_product", "create_linked_invoice"])
def test_interrupted_mutation_never_repeats(order, tmp_path, action):
    ui = FakeUI(order, fail=action)
    with pytest.raises(ReviewRequired):
        run(order, ui, tmp_path)
    assert ui.actions.count(action) == 1
    before = (tmp_path / "imagehash/checkpoint.json").read_bytes()
    ui.fail = None
    with pytest.raises(ReviewRequired, match="prior run"):
        run(order, ui, tmp_path)
    assert (tmp_path / "imagehash/checkpoint.json").read_bytes() == before
    assert ui.actions.count(action) == 1


def test_reencoded_input_has_semantic_duplicate_guard(order, tmp_path):
    ui = FakeUI(order, existing=True)
    run(order, ui, tmp_path)
    with pytest.raises(ReviewRequired, match="prior run"):
        run(order, ui, tmp_path, image="different-image-bytes")


def test_persisted_reference_and_customer_stop_before_open(order, tmp_path):
    ui = FakeUI(order)
    ui.documents.append({"reference": order.external_reference, "company": order.debtor.company,
                         "no": "PRIOR", "date": "2025-01-01", "total": "1.00"})
    with pytest.raises(ReviewRequired, match="previous transaction"):
        run(order, ui, tmp_path)
    assert "open_order" not in ui.actions


def test_duplicate_debtor_does_not_create(order, tmp_path):
    ui = FakeUI(order, existing=True)
    ui.debtors *= 2
    with pytest.raises(ReviewRequired, match="Ambiguous"):
        run(order, ui, tmp_path)
    assert "new_debtor" not in ui.actions


def test_invoice_method_absent_stops_before_invoice_save(order, tmp_path):
    ui = FakeUI(order, existing=True)
    ui.methods = []
    with pytest.raises(ReviewRequired, match="payment method"):
        run(order, ui, tmp_path)
    assert "save_invoice" not in ui.actions


def test_order_total_mismatch_stops_before_save(order, tmp_path):
    class WrongTotal(FakeUI):
        def read(self, name, ctx):
            result = super().read(name, ctx)
            if name == "order" and "total" in result:
                result["total"] = "570"
            return result
    ui = WrongTotal(order, existing=True)
    with pytest.raises(ReviewRequired):
        run(order, ui, tmp_path)
    assert "save_order" not in ui.actions


def test_exclusive_run_lock(tmp_path, order):
    with Journal(tmp_path, "a", semantic_fingerprint(order)):
        with pytest.raises(ReviewRequired, match="lock"):
            with Journal(tmp_path, "b", semantic_fingerprint(order)):
                pass


def test_conflicting_payment_terms_stop_before_debtor(order, tmp_path):
    ui = FakeUI(order)
    ui.payments = [{**payment_definition(order.payment.method), "net_days": "30"}]
    with pytest.raises(ReviewRequired, match="conflicting"):
        run(order, ui, tmp_path)
    assert "new_debtor" not in ui.actions
    assert "new_payment" not in ui.actions


def test_equivalent_vat_decimal_is_reused(order, tmp_path):
    ui = FakeUI(order)
    ui.vats = [{"name": "VAT 19%", "value": "19.00", "code": "S"}]
    run(order, ui, tmp_path)
    assert "new_vat" not in ui.actions


def test_wrong_delivery_address_stops(order, tmp_path):
    class WrongAddress(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == "select_debtor":
                self.order["delivery_address"] = self.order["invoice_address"]
    ui = WrongAddress(order, existing=True)
    with pytest.raises(ReviewRequired):
        run(order, ui, tmp_path)
    assert "select_product" not in ui.actions


def test_unlinked_invoice_stops_before_save(order, tmp_path):
    class Unlinked(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == "create_linked_invoice":
                self.invoice["order_no"] = "ANOTHER-ORDER"
    ui = Unlinked(order, existing=True)
    with pytest.raises(ReviewRequired):
        run(order, ui, tmp_path)
    assert "save_invoice" not in ui.actions


def test_workflow_progress_tracks_items_and_verified_stages(order, tmp_path):
    ui = FakeUI(order, existing=True)
    messages = []
    with Journal(tmp_path, "imagehash", semantic_fingerprint(order)) as journal:
        Workflow(ui, journal, progress=messages.append).run(order)
    assert "Processing item 1 of 2" in messages
    assert "Processing item 2 of 2" in messages
    assert "Order saved and verified in Documents" in messages
    assert "Persisted Invoice and payment fields verified" in messages
    assert ui.actions.count("save_order") == 1
    assert ui.actions.count("save_invoice") == 1


def test_progress_does_not_claim_uncertain_save_was_verified(order, tmp_path):
    ui = FakeUI(order, existing=True, fail="save_order")
    messages = []
    with Journal(tmp_path, "imagehash", semantic_fingerprint(order)) as journal:
        with pytest.raises(ReviewRequired):
            Workflow(ui, journal, progress=messages.append).run(order)
    assert any("save order" in line for line in messages)
    assert "Order saved and verified in Documents" not in messages
    assert "Persisted Invoice and payment fields verified" not in messages
    assert ui.actions.count("save_order") == 1
