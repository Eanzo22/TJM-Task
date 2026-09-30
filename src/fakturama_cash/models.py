from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .normalize import amount, day, money

Number = Annotated[Decimal, BeforeValidator(amount)]
Day = Annotated[date, BeforeValidator(day)]
Nonempty = Annotated[str, Field(min_length=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Address(Model):
    name: Nonempty
    street: Nonempty
    zip: Nonempty
    city: Nonempty
    country: Nonempty
    additional_name: str | None = None
    specification: str | None = None
    district: str | None = None


class Debtor(Model):
    company: Nonempty
    first_name: Nonempty
    last_name: Nonempty
    alias: Nonempty
    billing: Address
    delivery: Address
    email: Nonempty
    telephone: Nonempty
    salutation: str | None = None
    source_customer_id: str | None = None


class Payment(Model):
    method: Nonempty
    status: Literal["PAID", "UNPAID"]
    date: Day | None = None

    @model_validator(mode="after")
    def paid_requires_date(self):
        if self.status == "PAID" and self.date is None:
            raise ValueError("PAID requires the source payment date")
        if self.status == "UNPAID" and self.date is not None:
            raise ValueError("UNPAID with a payment date needs manual review")
        return self


class Line(Model):
    sku: Nonempty
    description: Nonempty
    quantity: Number = Field(gt=0)
    unit_net: Number = Field(ge=0)
    vat_percent: Number = Field(ge=0, le=100)
    discount_percent: Number = Field(ge=0, le=100)
    source_net: Number = Field(ge=0)
    unit: str | None = None

    @property
    def net(self):
        return money(self.quantity * self.unit_net * (1 - self.discount_percent / 100))

    @property
    def gross_master(self):
        # A Product is reusable master data; this Order's discount must not leak into it.
        return money(self.unit_net * (1 + self.vat_percent / 100))


class OrderInput(Model):
    order_date: Day
    external_reference: Nonempty
    currency: Literal["EUR"]
    debtor: Debtor
    payment: Payment
    items: list[Line] = Field(min_length=1)
    order_discount_percent: Number | None = Field(default=None, ge=0, le=100)
    shipping_net: Number | None = Field(default=None, ge=0)
    source_net: Number = Field(ge=0)
    source_vat: Number = Field(ge=0)
    source_total: Number = Field(ge=0)
    extraction_issues: list[str] = Field(default_factory=list)

    def reconcile(self):
        from .errors import ReviewRequired
        if self.extraction_issues:
            raise ReviewRequired("Extractor reported uncertain fields", observed=self.extraction_issues)
        if (self.order_discount_percent or 0) != 0 or (self.shipping_net or 0) != 0:
            raise ReviewRequired("Nonzero order discount/shipping treatment is unresolved",
                                 next_action="Confirm Fakturama tax allocation before enabling this case.")
        groups = {}
        for index, line in enumerate(self.items):
            if line.net != line.source_net:
                raise ReviewRequired(f"Line {index + 1} does not reconcile", expected=str(line.net), observed=str(line.source_net))
            groups[line.vat_percent] = groups.get(line.vat_percent, Decimal(0)) + line.net
        # Round each line net, then tax per VAT-rate subtotal; stop if Fakturama differs.
        net = sum((line.net for line in self.items), Decimal(0))
        vat = sum((money(base * rate / 100) for rate, base in groups.items()), Decimal(0))
        expected = [money(net), money(vat), money(net + vat)]
        actual = [self.source_net, self.source_vat, self.source_total]
        if actual != expected:
            raise ReviewRequired("Document totals do not reconcile", expected=list(map(str, expected)), observed=list(map(str, actual)))
        return self
