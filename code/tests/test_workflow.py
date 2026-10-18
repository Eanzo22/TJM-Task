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
        assert ui.actions.index("new_debtor") < ui.actions.index("fill_debtor") < ui.actions.index("save_payment")
        assert ui.actions.index("save_payment") < ui.actions.index("fill_debtor_payment") < ui.actions.index("save_debtor")
        assert ui.actions.index("save_vat") < ui.actions.index("new_product")
        assert ui.actions.count("save_vat") == 1
        assert ui.debtor["separate_delivery"] is True
        assert ui.debtor["customer_id"] == "TEST-CUSTOMER-01"


def test_product_auto_accept_is_disabled_before_any_order_is_opened(order, tmp_path):
    class AutoAcceptingUI(FakeUI):
        def act(self, name, ctx):
            if name == 'search_product' and self.auto_accept_single_product:
                raise AssertionError('Fakturama would close the single-result selector here')
            super().act(name, ctx)

    ui = AutoAcceptingUI(order, existing=True)
    ui.auto_accept_single_product = True
    run(order, ui, tmp_path)
    assert ui.auto_accept_single_product is False
    assert ui.actions.count('disable_product_auto_accept') == 1
    assert ui.actions.index('inspect_product_selection_settings') < ui.actions.index('disable_product_auto_accept')
    assert ui.actions.index('disable_product_auto_accept') < ui.actions.index('close_environment') < ui.actions.index('open_order')
    assert ui.actions.count('select_product') == len(order.items)


def test_already_manual_product_selection_does_not_write_preferences(order, tmp_path):
    ui = FakeUI(order, existing=True)
    run(order, ui, tmp_path)
    assert 'disable_product_auto_accept' not in ui.actions


def test_product_preference_that_does_not_change_stops_before_order(order, tmp_path):
    class IgnoredSetting(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'disable_product_auto_accept':
                self.auto_accept_single_product = True

    ui = IgnoredSetting(order, existing=True)
    ui.auto_accept_single_product = True
    with pytest.raises(ReviewRequired, match='do not match') as error:
        run(order, ui, tmp_path)
    assert error.value.details['stage'] == 'product_selection_settings'
    assert ui.actions.count('disable_product_auto_accept') == 1
    assert 'open_order' not in ui.actions


def test_uncertain_preference_apply_is_not_repeated_and_stops_before_order(order, tmp_path):
    ui = FakeUI(order, existing=True, fail='disable_product_auto_accept')
    ui.auto_accept_single_product = True
    with pytest.raises(ReviewRequired):
        run(order, ui, tmp_path)
    assert ui.actions.count('disable_product_auto_accept') == 1
    assert 'open_order' not in ui.actions
    checkpoint = json.loads(next(tmp_path.glob('imagehash/workflows/*/checkpoint.json')).read_text())
    assert checkpoint['actions']['disable_product_auto_accept'] == 'uncertain'


@pytest.mark.parametrize('invalid', [None, 1, 'false'])
def test_unreadable_product_preference_is_not_assumed_safe(order, tmp_path, invalid):
    ui = FakeUI(order, existing=True)
    ui.auto_accept_single_product = invalid
    with pytest.raises(ReviewRequired, match='preference is unreadable'):
        run(order, ui, tmp_path)
    assert not set(ui.actions) & {'disable_product_auto_accept', 'open_order'}


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
    checkpoint = next(tmp_path.glob("imagehash/workflows/*/checkpoint.json"))
    actions = json.loads(checkpoint.read_text())["actions"]
    assert actions[next(name for name in actions if name.split(":")[0] == action)] == "uncertain"
    assert ui.actions.count(action) == 1


@pytest.mark.parametrize("second_image", ["imagehash", "different-image-bytes"])
def test_each_explicit_run_starts_new_order_and_preserves_prior_evidence(order, tmp_path, second_image):
    first_ui = FakeUI(order, existing=True, fail="save_order")
    with pytest.raises(ReviewRequired):
        run(order, first_ui, tmp_path)
    original = next(tmp_path.glob("imagehash/workflows/*/checkpoint.json"))
    before = original.read_bytes()
    second_ui = FakeUI(order, existing=True)
    run(order, second_ui, tmp_path, image=second_image)
    assert original.read_bytes() == before
    assert second_ui.actions.count("open_order") == 1
    assert len(list(tmp_path.glob("*/workflows/*/checkpoint.json"))) == 2


def test_legacy_checkpoint_does_not_block_order_first_flow_or_get_overwritten(order, tmp_path):
    legacy = tmp_path / "imagehash" / "checkpoint.json"
    legacy.parent.mkdir()
    previous = {"image_fingerprint": "imagehash", "order_fingerprint": semantic_fingerprint(order),
                "status": "review_required", "actions": {"save_order": "uncertain"}}
    legacy.write_text(json.dumps(previous))
    before = legacy.read_bytes()
    ui = FakeUI(order, existing=True)
    run(order, ui, tmp_path)
    assert ui.actions.count("open_order") == 1
    assert legacy.read_bytes() == before


def test_same_attempt_does_not_repeat_uncertain_mutation(order, tmp_path):
    calls = []
    def uncertain_save():
        calls.append("save")
        raise TimeoutError("Outcome unavailable")
    with Journal(tmp_path, "imagehash", semantic_fingerprint(order)) as journal:
        with pytest.raises(TimeoutError):
            journal.mutate("save_order", uncertain_save)
        with pytest.raises(ReviewRequired, match="repeat a mutation"):
            journal.mutate("save_order", uncertain_save)
    assert calls == ["save"]


def test_persisted_reference_and_customer_do_not_add_a_transaction_identity_rule(order, tmp_path):
    ui = FakeUI(order)
    ui.documents.append({"reference": order.external_reference, "company": order.debtor.company,
                         "no": "PRIOR", "date": "2025-01-01", "total": "1.00"})
    run(order, ui, tmp_path)
    assert ui.actions.count("open_order") == 1
    assert ui.actions.index("open_order") < ui.actions.index("open_documents")


def test_existing_recipient_reference_does_not_block_new_order(order, tmp_path):
    ui = FakeUI(order)
    ui.documents.append(dict(reference=order.external_reference, customer=order.debtor.delivery.name))
    run(order, ui, tmp_path)
    assert ui.actions.count('open_order') == 1


def test_saved_address_mismatch_stops_without_rewriting_or_second_order_save(order, tmp_path):
    class RebindingUI(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'save_order':
                self.order['delivery_address']['name'] = 'Different saved recipient'
    ui = RebindingUI(order, existing=True)
    with pytest.raises(ReviewRequired) as error:
        run(order, ui, tmp_path)
    assert error.value.details['stage'] == 'follow_up_source_order'
    assert not set(ui.actions) & {'create_linked_invoice', 'fill_order_addresses'}
    assert ui.actions.count('save_order') == 1
    checkpoint = json.loads(next(tmp_path.glob('imagehash/workflows/*/checkpoint.json')).read_text())
    assert 'save_order' in checkpoint['actions'] and 'save_order:addresses' not in checkpoint['actions']


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


def test_conflicting_payment_terms_stop_before_saving_debtor(order, tmp_path):
    ui = FakeUI(order)
    ui.payments = [{**payment_definition(order.payment.method), "net_days": "30"}]
    with pytest.raises(ReviewRequired, match="do not match"):
        run(order, ui, tmp_path)
    assert "new_debtor" in ui.actions
    assert "save_debtor" not in ui.actions
    assert "new_payment" not in ui.actions


def test_equivalent_vat_decimal_is_reused(order, tmp_path):
    ui = FakeUI(order)
    ui.vats = [{"name": "VAT 19%", "value": "19.00", "code": "S", "description": "Standard tax"}]
    run(order, ui, tmp_path)
    assert "new_vat" not in ui.actions
    assert ui.product["vat_description"] == "Standard tax"


@pytest.mark.parametrize('description, options, label', [
    ('', ['Free of Tax', ''], ''),
    ('', ['Free of Tax', 'VAT 19%'], 'VAT 19%'),
    ('   ', ['Free of Tax', '   '], '   '),
])
def test_blank_existing_vat_description_does_not_block_flow(order, tmp_path, description, options, label):
    ui = FakeUI(order)
    vat = {'name': 'VAT 19%', 'value': '19', 'code': 'S', 'description': description}
    ui.vats = [dict(vat)]
    ui.vat_options = options
    result = run(order, ui, tmp_path)
    assert result['invoice'] == 'TEST-INVOICE-01'
    assert ui.product['vat_description'] == label
    assert ui.vats == [vat]
    assert not {'new_vat', 'fill_vat', 'save_vat'}.intersection(ui.actions)


@pytest.mark.parametrize('options', [['', ''], ['', 'VAT 19%'], ['VAT 7%'], ['VAT 19%', 'VAT 19%']])
def test_blank_vat_still_requires_one_unambiguous_dropdown_option(order, tmp_path, options):
    ui = FakeUI(order)
    ui.vats = [{'name': 'VAT 19%', 'value': '19', 'code': 'S', 'description': ''}]
    ui.vat_options = options
    with pytest.raises(ReviewRequired, match='VAT option missing or ambiguous'):
        run(order, ui, tmp_path)
    assert 'fill_product' not in ui.actions
    assert 'save_product' not in ui.actions


def test_unreadable_vat_description_is_not_assumed_to_be_blank(order, tmp_path):
    ui = FakeUI(order)
    ui.vats = [{"name": "VAT 19%", "value": "19", "code": "S"}]
    with pytest.raises(ReviewRequired, match="description is unreadable"):
        run(order, ui, tmp_path)
    assert "new_product" not in ui.actions


@pytest.mark.parametrize('field, value', [('value', '7'), ('code', 'Z')])
def test_blank_description_never_bypasses_vat_identity_checks(order, tmp_path, field, value):
    ui = FakeUI(order)
    ui.vats = [{'name': 'VAT 19%', 'value': '19', 'code': 'S', 'description': '', field: value}]
    with pytest.raises(ReviewRequired, match='do not match'):
        run(order, ui, tmp_path)
    assert 'new_product' not in ui.actions


def test_vat_code_is_verified_in_editor_even_when_list_omits_it(order, tmp_path):
    class ThinVatList(FakeUI):
        def read(self, name, ctx):
            if name == "vat_results":
                return [{"name": row["name"], "value": row["value"]} for row in self.vats]
            if name == "vat":
                return self.vats[0]
            return super().read(name, ctx)
    ui = ThinVatList(order)
    ui.vats = [{"name": "VAT 19%", "value": "19", "code": "Z", "description": "Wrong tax category"}]
    with pytest.raises(ReviewRequired, match="do not match"):
        run(order, ui, tmp_path)
    assert "inspect_vat" in ui.actions
    assert "new_product" not in ui.actions


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
    assert "fill_order_addresses" not in ui.actions


@pytest.mark.parametrize('field', ['name', 'street', 'zip', 'city', 'country', 'additional_name', 'specification', 'district'])
def test_shared_heading_does_not_hide_wrong_delivery_fields(order, tmp_path, field):
    class WrongDelivery(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'select_debtor':
                self.order['delivery_address'][field] = 'Incorrect value'
    ui = WrongDelivery(order, existing=True)
    with pytest.raises(ReviewRequired) as error:
        run(order, ui, tmp_path)
    assert error.value.details['stage'] == 'selected_addresses'
    assert not set(ui.actions) & {'select_product', 'save_order', 'fill_order_addresses'}


@pytest.mark.parametrize('existing', [False, True])
def test_shared_company_heading_reaches_persisted_invoice_with_distinct_delivery(order, tmp_path, existing):
    before = order.model_dump_json()
    ui = FakeUI(order, existing=existing)
    run(order, ui, tmp_path)
    assert ui.invoice['invoice_address']['name'] == ui.invoice['delivery_address']['name'] == order.debtor.company
    assert ui.invoice['invoice_address']['street'] == order.debtor.billing.street
    assert ui.invoice['delivery_address']['street'] == order.debtor.delivery.street
    assert ui.invoice['delivery_address']['zip'] == order.debtor.delivery.zip
    assert ui.actions.count('save_order') == ui.actions.count('save_invoice') == 1
    assert order.model_dump_json() == before


def test_different_source_block_label_alone_does_not_create_second_postal_address(payload, tmp_path):
    payload['debtor']['delivery'] = {**payload['debtor']['billing'], 'name': 'Source warehouse block label'}
    order = OrderInput.model_validate(payload)
    ui = FakeUI(order)
    run(order, ui, tmp_path)
    assert ui.debtor['separate_delivery'] is False


def test_existing_debtor_skips_master_creation_and_preserves_selected_addresses(order, tmp_path):
    ui = FakeUI(order, existing=True)
    run(order, ui, tmp_path)
    assert not set(ui.actions) & {'new_debtor', 'open_payments', 'new_payment', 'fill_order_addresses'}


def test_existing_payment_dropdown_skips_payment_creation(order, tmp_path):
    ui = FakeUI(order)
    ui.debtor_methods = [order.payment.method]
    run(order, ui, tmp_path)
    assert not set(ui.actions) & {'open_payments', 'new_payment', 'save_payment'}
    assert ui.actions.index('fill_debtor') < ui.actions.index('fill_debtor_payment') < ui.actions.index('save_debtor')


def test_duplicate_payment_dropdown_stops_before_debtor_save(order, tmp_path):
    ui = FakeUI(order)
    ui.debtor_methods = [order.payment.method, order.payment.method]
    with pytest.raises(ReviewRequired, match='ambiguous'):
        run(order, ui, tmp_path)
    assert not set(ui.actions) & {'new_payment', 'save_debtor'}


def test_stale_payment_dropdown_keeps_debtor_unsaved(order, tmp_path):
    class StaleDropdown(FakeUI):
        def read(self, name, ctx):
            return [] if name == 'debtor_methods' else super().read(name, ctx)
    ui = StaleDropdown(order)
    with pytest.raises(ReviewRequired, match='did not refresh'):
        run(order, ui, tmp_path)
    assert ui.actions.count('save_payment') == 1
    assert ui.actions.count('discard_debtor_draft') == 1
    assert ui.actions.count('new_debtor') == 2
    assert 'activate_debtor' in ui.actions
    assert not set(ui.actions) & {'save_debtor', 'select_product', 'save_order'}


@pytest.mark.parametrize('invalid_roles_after_refill', [False, True])
def test_refresh_reads_blank_contact_before_validating_address_roles(order, tmp_path, invalid_roles_after_refill):
    from types import SimpleNamespace
    from fakturama_cash.master_forms import debtor_values

    class StaleDropdown(FakeUI):
        def read(self, name, ctx):
            if name == 'debtor_methods' and self.actions.count('new_debtor') < 2:
                return []
            if name == 'debtor' and self.actions.count('new_debtor') == 2:
                # Execute the real reader with the old definition still in
                # context, not FakeUI's permissive dictionary-only response.
                if self.actions.count('fill_debtor') < 2 or invalid_roles_after_refill:
                    def missing_extra_address(*args):
                        raise LookupError('No additional address in this draft')
                    adapter = SimpleNamespace(
                        profile={'queries': {q: q for q in ('debtor_contact', 'debtor_misc', 'debtor_billing_fields')}},
                        _read=lambda q, c: dict(self.debtor) if q == 'debtor_contact' else {},
                        _scalar=lambda *a: '', _find_once=missing_extra_address)
                    return debtor_values(adapter, ctx)
            return super().read(name, ctx)

    ui = StaleDropdown(order)
    if invalid_roles_after_refill:
        with pytest.raises(ReviewRequired, match='address roles'):
            run(order, ui, tmp_path)
        assert 'save_debtor' not in ui.actions
    else:
        run(order, ui, tmp_path)
        assert ui.actions.count('save_debtor') == 1
    assert ui.actions.count('fill_debtor') == 2


def test_new_payment_stale_list_reopens_and_refills_debtor_once(order, tmp_path):
    class RefreshOnReopen(FakeUI):
        def read(self, name, ctx):
            if name == 'debtor_methods' and self.actions.count('new_debtor') < 2:
                return []
            return super().read(name, ctx)

        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'new_debtor' and self.actions.count(name) == 2:
                self.debtor['customer_id'] = 'TEST-CUSTOMER-02'

    ui = RefreshOnReopen(order)
    run(order, ui, tmp_path)
    assert ui.actions.count('discard_debtor_draft') == 1
    assert ui.actions.count('new_debtor') == ui.actions.count('fill_debtor') == 2
    assert ui.actions.count('save_debtor') == ui.actions.count('save_payment') == 1
    assert ui.actions.count('open_order') == 1
    assert ui.actions.index('discard_debtor_draft') < ui.actions.index('fill_debtor_payment')
    assert ui.debtor['customer_id'] == 'TEST-CUSTOMER-02'
    assert ui.debtor['payment_method'] == order.payment.method
    assert ui.debtor['billing']['street'] == order.debtor.billing.street
    assert ui.debtor['delivery']['street'] == order.debtor.delivery.street
    checkpoint = json.loads(next(tmp_path.glob('imagehash/workflows/*/checkpoint.json')).read_text())
    assert checkpoint['actions']['new_debtor:payment_refresh'] == 'returned_unverified'


@pytest.mark.parametrize('scenario', ['already_available', 'refreshed', 'existing_payment', 'duplicate'])
def test_debtor_recovery_only_for_missing_newly_created_payment(order, tmp_path, scenario):
    class PaymentList(FakeUI):
        def read(self, name, ctx):
            if name == 'debtor_methods' and scenario == 'duplicate' and self.payments:
                return [order.payment.method, order.payment.method]
            return super().read(name, ctx)

    ui = PaymentList(order)
    if scenario == 'already_available':
        ui.debtor_methods = [order.payment.method]
    if scenario == 'existing_payment':
        ui.payments = [payment_definition(order.payment.method)]
    if scenario in ('existing_payment', 'duplicate'):
        with pytest.raises(ReviewRequired):
            run(order, ui, tmp_path)
    else:
        run(order, ui, tmp_path)
    assert 'discard_debtor_draft' not in ui.actions
    assert ui.actions.count('new_debtor') == 1


def test_uncertain_debtor_close_is_not_retried_or_followed_by_new_draft(order, tmp_path):
    class StaleDropdown(FakeUI):
        def read(self, name, ctx):
            return [] if name == 'debtor_methods' else super().read(name, ctx)
    ui = StaleDropdown(order, fail='discard_debtor_draft')
    with pytest.raises(ReviewRequired):
        run(order, ui, tmp_path)
    assert ui.actions.count('discard_debtor_draft') == ui.actions.count('new_debtor') == 1
    assert 'save_debtor' not in ui.actions


def test_modified_debtor_draft_is_not_discarded(order, tmp_path):
    class ChangedDraft(FakeUI):
        def read(self, name, ctx):
            if name == 'debtor_methods':
                return []
            result = super().read(name, ctx)
            if name == 'debtor' and 'save_payment' in self.actions:
                result['company'] = 'Unexpected manual edit'
            return result
    ui = ChangedDraft(order)
    with pytest.raises(ReviewRequired, match='do not match'):
        run(order, ui, tmp_path)
    assert 'discard_debtor_draft' not in ui.actions


def test_wrong_contact_editor_is_never_filled(order, tmp_path):
    class ExistingEditor(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'new_debtor':
                self.debtor.update(company='Previously opened contact', first_name='Alex', last_name='Example')
    ui = ExistingEditor(order)
    with pytest.raises(ReviewRequired, match='do not match') as error:
        run(order, ui, tmp_path)
    assert error.value.details['stage'] == 'new_debtor_blank'
    assert not set(ui.actions) & {'fill_debtor', 'new_payment', 'save_debtor'}


def test_product_selectors_run_in_source_order_after_verified_debtor(order, tmp_path):
    class TracedSelectors(FakeUI):
        def __init__(self, order):
            super().__init__(order, existing=True)
            self.searches = []
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'search_product':
                self.searches.append(ctx['line']['sku'])
    ui = TracedSelectors(order)
    run(order, ui, tmp_path)
    assert ui.searches == [line.sku for line in order.items]
    assert ui.actions.index('select_debtor') < ui.actions.index('open_product_selector')


@pytest.mark.parametrize('field', ['name', 'description'])
def test_existing_product_editor_is_rejected_before_entering_source_fields(order, tmp_path, field):
    class ExistingProductEditor(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'new_product':
                self.product.update(sku='LIVE-CHAIR-003', **{field: 'TEST - Synthetic Chair'})

    ui = ExistingProductEditor(order, existing=True)
    ui.products = []
    with pytest.raises(ReviewRequired, match='do not match') as error:
        run(order, ui, tmp_path)
    assert error.value.details['stage'] == 'new_product_blank'
    assert ui.actions.count('new_product') == 1
    assert not set(ui.actions) & {'fill_product', 'save_product', 'select_product', 'save_order'}
    assert ui.actions.index('inspect_vat') < ui.actions.index('new_product')


def test_new_product_proposed_item_number_is_replaced_with_extracted_sku(order, tmp_path):
    class ProposedProductNumber(FakeUI):
        def act(self, name, ctx):
            super().act(name, ctx)
            if name == 'new_product':
                self.product['sku'] = 'P000123'

    ui = ProposedProductNumber(order, existing=True)
    ui.products = []
    run(order, ui, tmp_path)
    assert [p['sku'] for p in ui.products] == [line.sku for line in order.items]


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
