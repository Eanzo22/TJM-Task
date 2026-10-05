"""Small sequential workflow. The UI adapter observes; this module owns business decisions."""
from .errors import ReviewRequired
from .document_fields import document_addresses
from .matching import exact_match, payment_definition
from .normalize import key
from .verification import document_row, require

ACTIONS = {
    "open_order", "fill_order_header", "open_debtor_selector", "search_debtor", "cancel_debtor_selector",
    "select_debtor", "open_payments", "search_payment", "new_payment", "fill_payment", "save_payment",
    "new_debtor", "fill_debtor", "fill_debtor_payment", "activate_debtor", "save_debtor", "activate_order", "open_product_selector",
    "search_product", "cancel_product_selector", "select_product", "open_vats", "search_vat",
    "new_vat", "fill_vat", "save_vat", "new_product", "fill_product", "save_product",
    "fill_line", "fill_order_totals", "save_order", "open_documents", "create_linked_invoice",
    "fill_invoice_payment", "save_invoice", "reopen_invoice",
    "inspect_payment", "inspect_vat",
    'inspect_environment', 'close_environment',
    'inspect_product_selection_settings', 'disable_product_auto_accept',
}
QUERIES = {"documents", "order", "debtor_results", "payment_results", "debtor", "product_results",
           "vat_results", "product", "line", "invoice", "invoice_methods", "environment",
           "payment", "payment_draft", "vat", "vat_draft", "debtor_methods"}
QUERIES.update({'order_header', 'order_addresses', 'product_selection_settings'})


class Workflow:
    def __init__(self, ui, journal, progress=None):
        self.ui, self.journal = ui, journal
        self.ctx = {}
        self.progress = progress if progress is not None else lambda message: None

    def navigate(self, name):
        # Navigation/search actions must be calibrated as read-only recipes.
        self.progress(f"UI navigation/search: {name.replace('_', ' ')}")
        self.ui.act(name, self.ctx)

    def write(self, name, suffix=""):
        self.progress(f"UI action (no automatic retry): {name.replace('_', ' ')}{suffix}")
        return self.journal.mutate(name + suffix, lambda: self.ui.act(name, self.ctx))

    def read(self, name):
        self.progress(f"Reading stable UI state: {name.replace('_', ' ')}")
        return self.ui.read(name, self.ctx)

    def evidence(self, stage):
        self.progress(f"Capturing UI evidence: {stage}")
        evidence = self.ui.capture(self.journal.directory, stage)
        self.journal.record_evidence(evidence)

    def run(self, order):
        order.reconcile()
        self.ctx["input"] = order.model_dump(mode="json")
        addresses = document_addresses(order.debtor)
        self.ctx['separate_delivery'] = addresses['invoice_address'] != addresses['delivery_address']
        try:
            self.progress("Checking UI profile readiness")
            self.ui.preflight(ACTIONS, QUERIES)
            self.navigate('inspect_environment')
            require(self.read("environment"), {"currency": order.currency}, "environment")
            # 3.3/3.12 require matching the results and explicitly confirming OK.
            # Fakturama otherwise closes the selector as soon as one row remains.
            self.navigate('inspect_product_selection_settings')
            settings = self.read('product_selection_settings')
            enabled = settings.get('auto_accept_single_product')
            if type(enabled) is not bool:
                raise ReviewRequired('Product auto-accept preference is unreadable', stage='UI preflight')
            if enabled:
                self.progress('Disabling automatic Product acceptance for explicit exact-match and OK selection')
                self.write('disable_product_auto_accept')
                require(self.read('product_selection_settings'),
                        dict(auto_accept_single_product=False), 'product_selection_settings')
            self.navigate('close_environment')
            # Assignment 1.3: start a New Order after extraction/setup. Existing
            # master records are checked through that Order's selectors (2/3).
            self.ctx.update(order_editor='New Order', order_tab='New Order',
                            invoice_editor='New Invoice', debtor_editor='New Debtor')
            self.write("open_order")
            initial = self.read("order")
            self.ctx["order_no"] = initial["no"]
            if not self.ctx["order_no"]:
                raise ReviewRequired("Proposed Order number missing", stage="open_order")
            self.journal.data["identifiers"]["order"] = initial["no"]
            self.write("fill_order_header")
            self.ctx['order_tab'] = '*New Order'
            require(self.read("order_header"), {"no": initial["no"], "date": order.order_date,
                    "reference": order.external_reference, "price_mode": "Net", "vat_mode": "With VAT"}, "order_header")
            self.resolve_debtor(order)
            for index, line in enumerate(order.items):
                self.progress(f"Processing item {index + 1} of {len(order.items)}")
                self.resolve_line(index, line)

            self.navigate("activate_order")
            self.write("fill_order_totals")
            expected = self.expected_order(order)
            require(self.read("order"), expected, "order_before_save")
            self.evidence("order-before-save")
            self.write("save_order")
            self.ctx.update(order_editor=initial['no'], order_tab=initial['no'])
            self.navigate("open_documents")
            order_row = {"type": "Order", "no": initial["no"], "date": order.order_date,
                         "reference": order.external_reference, "state": "open", "total": order.source_total}
            document_row(self.read("documents"), order_row, "saved_order")
            self.journal.verified("saved_order")
            self.progress("Order saved and verified in Documents")
            self.evidence("order-saved")

            self.navigate("activate_order")
            require(self.read('order'), expected, 'follow_up_source_order')
            self.write("create_linked_invoice")
            invoice = self.read("invoice")
            self.ctx["invoice_no"] = invoice["no"]
            preserved = {field: invoice[field] for field in ("no", "invoice_date", "service_date")}
            if not all(preserved.values()):
                raise ReviewRequired("Proposed Invoice identifiers/dates missing", stage="new_invoice")
            self.journal.data["identifiers"]["invoice"] = invoice["no"]
            copied = {k: v for k, v in expected.items() if k not in ("no", "date")}
            copied.update(order_date=order.order_date)
            # Some adapters expose the relationship identifier. This Fakturama
            # UI exposes the order date and copied fields, but no source number.
            # Its recipe invokes Invoice inside the exact saved Order pane.
            if 'order_no' in invoice:
                copied['order_no'] = initial['no']
            self.journal.event('invoice_origin', source_order=initial['no'],
                               verification='relationship_field' if 'order_no' in invoice else 'scoped_follow_up_and_copied_fields')
            require(invoice, copied, "invoice_copied_values")
            if sum(key(m) == key(order.payment.method) for m in self.read("invoice_methods")) != 1:
                raise ReviewRequired("Invoice payment method unavailable or ambiguous", stage="invoice_payment")
            payment = dict(payment_method=order.payment.method, paid=order.payment.status == "PAID",
                           payment_date=order.payment.date, value=order.source_total if order.payment.status == "PAID" else None)
            self.ctx["invoice_payment"] = payment
            self.write("fill_invoice_payment")
            require(self.read("invoice"), {**copied, **preserved, **payment}, "invoice_before_save")
            self.evidence("invoice-before-save")
            self.write("save_invoice")
            self.ctx['invoice_editor'] = invoice['no']
            self.navigate("open_documents")
            rows = self.read("documents")
            document_row(rows, order_row, "final_order")
            document_row(rows, {"type": "Invoice", "no": invoice["no"], "reference": order.external_reference,
                               "state": "paid" if payment["paid"] else "unpaid", "total": order.source_total}, "final_invoice")
            self.navigate("reopen_invoice")
            require(self.read("invoice"), {**copied, **preserved, **payment}, "persisted_invoice")
            self.progress("Persisted Invoice and payment fields verified")
            self.journal.verified("complete")
            self.journal.data["status"] = "complete"
            self.journal.flush()
            self.evidence("complete")
            return self.journal.data["identifiers"]
        except Exception as exc:
            try:
                self.evidence("failure")
            except Exception as capture_error:
                self.journal.event("evidence_capture_failed", error=str(capture_error))
            if self.journal.data["actions"]:
                self.journal.data["status"] = "review_required"
                self.journal.flush()
            if isinstance(exc, ReviewRequired):
                raise
            raise ReviewRequired(f"Workflow failed: {type(exc).__name__}: {exc}",
                                 stage=self.journal.data["stage"],
                                 next_action="Inspect checkpoint and evidence. Reconcile uncertain writes; do not rerun blindly.") from exc

    def expected_order(self, order):
        return dict(no=self.ctx["order_no"], date=order.order_date, reference=order.external_reference,
                    price_mode="Net", vat_mode="With VAT", **document_addresses(order.debtor),
                    items=[line.model_dump(mode="json", exclude={"unit"}) for line in order.items],
                    net=order.source_net, vat=order.source_vat, total=order.source_total, discount="0", shipping="0")

    def resolve_debtor(self, order):
        debtor = order.debtor
        expected = dict(company=debtor.company, first_name=debtor.first_name, last_name=debtor.last_name,
                        zip=debtor.billing.zip, city=debtor.billing.city)
        self.navigate("open_debtor_selector")
        self.navigate("search_debtor")
        row = exact_match(self.read("debtor_results"), expected, identity="company")
        if row is None:
            self.progress("Debtor missing; opening a fresh Debtor editor")
            self.navigate("cancel_debtor_selector")
            self.write("new_debtor")
            draft = self.read("debtor")
            customer_id = draft["customer_id"]
            if not customer_id:
                raise ReviewRequired("Proposed Customer ID missing", stage="new_debtor")
            require(draft, dict(company="", first_name="", last_name=""), "new_debtor_blank")
            self.ctx["debtor_definition"] = {
                **debtor.model_dump(mode="json", exclude={"source_customer_id"}),
                "customer_id": customer_id, "salutation": debtor.salutation or "---", "discount": "0",
                "price_mode": "Net", "payment_method": order.payment.method,
                "separate_delivery": self.ctx['separate_delivery'],
            }
            # Contact editors have one Company/first/last name for all addresses.
            # The shared Company is verified in the selector and document
            # heading; each role's postal fields are verified independently.
            for role in ('billing', 'delivery'):
                self.ctx['debtor_definition'][role].pop('name')
            self.write("fill_debtor")
            self.ctx["debtor_tab"] = "*New Debtor"
            self.resolve_payment(order.payment.method)
            require(self.read("debtor"), self.ctx["debtor_definition"], "debtor_before_save")
            self.write("save_debtor")
            self.navigate("activate_order")
            self.navigate("open_debtor_selector")
            self.navigate("search_debtor")
            row = exact_match(self.read("debtor_results"), expected, identity="company")
            if row is None:
                raise ReviewRequired("Saved Debtor not visible", stage="debtor_saved")
        self.ctx["selected_debtor"] = row
        self.write("select_debtor")
        # Verify what selection populated before any document address writes.
        # A mismatching existing contact must not be made to appear correct.
        require(self.read("order_addresses"), document_addresses(debtor), "selected_addresses")
        self.journal.verified("debtor_selected")
        self.progress("Selected Debtor addresses verified")

    def resolve_payment(self, method):
        # The Debtor stays open throughout this conditional branch (2.10).
        methods = self.read("debtor_methods")
        matches = sum(key(name) == key(method) for name in methods)
        if matches > 1:
            raise ReviewRequired("Debtor payment method ambiguous", stage="debtor_payment",
                                 expected=method, observed=methods)
        if matches == 0:
            definition = payment_definition(method)
            self.ctx["payment_definition"] = definition
            self.navigate("open_payments")
            self.navigate("search_payment")
            payment = exact_match(self.read("payment_results"), {"name": method}, identity="name")
            if payment is None:
                self.write("new_payment")
                self.write("fill_payment")
                require(self.read("payment_draft"), definition, "payment_before_save")
                self.write("save_payment")
                self.navigate("search_payment")
                payment = exact_match(self.read("payment_results"), {"name": method}, identity="name")
                if payment is None:
                    raise ReviewRequired("Saved Payment Method not visible", stage="payment_saved")
            self.ctx["selected_payment"] = payment
            self.navigate("inspect_payment")
            require(self.read("payment"), definition, "payment_definition")
            self.navigate("activate_debtor")
            methods = self.read("debtor_methods")
            if sum(key(name) == key(method) for name in methods) != 1:
                raise ReviewRequired("Open Debtor payment dropdown did not refresh", stage="debtor_payment",
                                     expected=method, observed=methods,
                                     next_action="Inspect the open Debtor and saved payment method. No Debtor save occurred; reconcile before restarting.")
        self.write("fill_debtor_payment")

    def resolve_line(self, index, line):
        suffix = f":{index}"
        self.ctx.update(line=line.model_dump(mode="json"), index=index)
        self.navigate("activate_order")
        self.navigate("open_product_selector")
        self.navigate("search_product")
        row = exact_match(self.read("product_results"), {"sku": line.sku}, identity="sku")
        if row is None:
            self.progress("Product missing; resolving VAT before Product creation")
            self.navigate("cancel_product_selector")
            vat = dict(name=f"VAT {line.vat_percent.normalize():f}%", value=str(line.vat_percent), code="S")
            self.ctx["vat_definition"] = {**vat, "description": vat["name"]}
            self.navigate("open_vats")
            self.navigate("search_vat")
            match = exact_match(self.read("vat_results"), {"name": vat["name"]}, identity="name")
            if match is None:
                self.write("new_vat", suffix)
                self.write("fill_vat", suffix)
                require(self.read("vat_draft"), self.ctx["vat_definition"], "vat_before_save")
                self.write("save_vat", suffix)
                self.navigate("search_vat")
                match = exact_match(self.read("vat_results"), {"name": vat["name"]}, identity="name")
                if match is None:
                    raise ReviewRequired("Saved VAT not visible", stage="vat_saved")
            self.ctx["selected_vat"] = match
            self.navigate("inspect_vat")
            observed_vat = self.read("vat")
            require(observed_vat, vat, "vat_definition")
            description = observed_vat.get("description")
            if not isinstance(description, str) or not description.strip():
                raise ReviewRequired("VAT dropdown description is unreadable", stage="vat_selection")
            self.ctx["product_definition"] = dict(sku=line.sku, name=line.description, description=line.description,
                # The Product dropdown displays the VAT description. The full
                # name/rate/code was checked in VATs just above. Reuse its
                # observed description, which need not equal its internal name.
                gross=str(line.gross_master), vat_description=description, cost="0.00", stock="0.00")
            self.write("new_product", suffix)
            # A New product shortcut can reactivate a selected master in 2.2.0.
            # Confirm the fresh form before entering the source fields (3.8).
            require(self.read("product"), dict(name="", description=""), "new_product_blank")
            self.write("fill_product", suffix)
            require(self.read("product"), self.ctx["product_definition"], "product_before_save")
            self.write("save_product", suffix)
            self.navigate("activate_order")
            self.navigate("open_product_selector")
            self.navigate("search_product")
            row = exact_match(self.read("product_results"), {"sku": line.sku}, identity="sku")
            if row is None:
                raise ReviewRequired("Saved Product not visible", stage="product_saved")
        self.ctx["selected_product"] = row
        self.write("select_product", suffix)
        self.write("fill_line", suffix)
        require(self.read("line"), line.model_dump(mode="json", exclude={"unit"}), f"line_{index + 1}")
        self.journal.verified(f"line_{index + 1}")
        self.progress(f"Item {index + 1} verified")
