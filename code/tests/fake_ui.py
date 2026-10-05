"""In-memory simulator only. This does not validate any Fakturama UI controls."""
from copy import deepcopy


class FakeUI:
    def __init__(self, order, existing=False, fail=None):
        self.input = order
        self.fail = fail
        self.actions = []
        self.documents = []
        self.order = {}
        self.invoice = {}
        self.debtor = {}
        self.product = {}
        self.payments = []
        self.payment_draft = {}
        self.vat_draft = {}
        self.vats = []
        self.products = []
        d = order.debtor
        self.debtors = [dict(company=d.company, first_name=d.first_name, last_name=d.last_name,
                             zip=d.billing.zip, city=d.billing.city)] if existing else []
        if existing:
            self.products = [{"sku": line.sku} for line in order.items]
        self.methods = [order.payment.method]
        self.debtor_methods = []
        self.auto_accept_single_product = False

    def preflight(self, *_):
        pass

    def capture(self, directory, stage):
        return {"kind": "fake_test_observation", "stage": stage}

    def act(self, name, ctx):
        self.actions.append(name)
        inp = ctx["input"]
        if name == "open_order":
            self.order = dict(no="TEST-ORDER-01", items=[])
        elif name == 'disable_product_auto_accept':
            self.auto_accept_single_product = False
        elif name == "fill_order_header":
            self.order.update(date=inp["order_date"], reference=inp["external_reference"], price_mode="Net", vat_mode="With VAT")
        elif name == "fill_payment":
            self.payment_draft = deepcopy(ctx["payment_definition"])
        elif name == "save_payment":
            self.payments.append(deepcopy(ctx["payment_definition"]))
            self.debtor_methods.append(ctx['payment_definition']['name'])
        elif name == "new_debtor":
            self.debtor = {"customer_id": "TEST-CUSTOMER-01", "company": "", "first_name": "", "last_name": ""}
        elif name == "fill_debtor":
            self.debtor.update(deepcopy(ctx["debtor_definition"]))
            self.debtor['payment_method'] = ''
        elif name == 'fill_debtor_payment':
            self.debtor['payment_method'] = ctx['debtor_definition']['payment_method']
        elif name == "save_debtor":
            d = self.debtor
            self.debtors.append(dict(company=d["company"], first_name=d["first_name"], last_name=d["last_name"],
                                     zip=d["billing"]["zip"], city=d["billing"]["city"]))
        elif name == "select_debtor":
            # Fakturama renders the contact Company on both role addresses.
            self.order.update(invoice_address={**deepcopy(inp["debtor"]["billing"]), 'name': inp['debtor']['company']},
                              delivery_address={**deepcopy(inp["debtor"]["delivery"]), 'name': inp['debtor']['company']})
        elif name == 'fill_order_addresses':
            self.order.update(invoice_address=deepcopy(inp['debtor']['billing']), delivery_address=deepcopy(inp['debtor']['delivery']))
        elif name == "fill_vat":
            self.vat_draft = deepcopy(ctx["vat_definition"])
        elif name == "save_vat":
            self.vats.append(deepcopy(ctx["vat_definition"]))
        elif name == "new_product":
            self.product = dict(sku="", name="", description="")
        elif name == "fill_product":
            self.product = deepcopy(ctx["product_definition"])
        elif name == "save_product":
            self.products.append(deepcopy(self.product))
        elif name == "select_product":
            self.order["items"].append({})
        elif name == "fill_line":
            self.order["items"][ctx["index"]] = {k: v for k, v in deepcopy(ctx["line"]).items() if k != "unit"}
        elif name == "fill_order_totals":
            self.order.update(net=inp["source_net"], vat=inp["source_vat"], total=inp["source_total"], discount="0", shipping="0")
        elif name == "save_order":
            self.documents = [r for r in self.documents if not (r.get('type') == 'Order' and r.get('no') == self.order['no'])]
            self.documents.append({"type": "Order", "no": self.order["no"], "date": self.order["date"],
                "reference": inp["external_reference"], "company": inp["debtor"]["company"], "state": "open", "total": inp["source_total"]})
        elif name == "create_linked_invoice":
            self.invoice = deepcopy(self.order)
            self.invoice.update(no="TEST-INVOICE-01", order_no=self.order["no"], order_date=self.order["date"],
                                invoice_date="2026-09-29", service_date="2026-09-29")
        elif name == "fill_invoice_payment":
            self.invoice.update(deepcopy(ctx["invoice_payment"]))
        elif name == "save_invoice":
            self.documents.append({"type": "Invoice", "no": self.invoice["no"], "reference": inp["external_reference"],
                "state": "paid" if self.invoice["paid"] else "unpaid", "total": inp["source_total"]})
        # Simulate the hardest case: a successful application write followed by timeout.
        if name == self.fail:
            raise TimeoutError("Simulated timeout after the application accepted the action")

    def read(self, name, ctx):
        values = {"environment": {"currency": "EUR"}, "documents": self.documents,
                  'product_selection_settings': {'auto_accept_single_product': self.auto_accept_single_product},
                  "order": self.order, "order_header": self.order, 'order_addresses': self.order,
                  "invoice": self.invoice, "debtor": self.debtor,
                  "debtor_results": self.debtors, "payment_results": self.payments,
                  "product_results": [r for r in self.products if r["sku"] == ctx.get("line", {}).get("sku")],
                  "vat_results": self.vats, "product": self.product, "invoice_methods": self.methods,
                  "debtor_methods": self.debtor_methods}
        values.update(payment_draft=self.payment_draft, vat_draft=self.vat_draft,
                      payment=ctx.get("selected_payment"), vat=ctx.get("selected_vat"))
        if name == "line":
            return deepcopy(self.order["items"][ctx["index"]])
        return deepcopy(values[name])
