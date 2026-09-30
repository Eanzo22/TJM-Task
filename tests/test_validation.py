from decimal import Decimal

import pytest
from pydantic import ValidationError

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.matching import exact_match, payment_definition
from fakturama_cash.models import OrderInput
from fakturama_cash.normalize import amount, day, money


@pytest.mark.parametrize("text,expected", [("1.234,56", "1234.56"), ("1,234.56", "1234.56"),
    ("EUR 570,00", "570.00"), ("19%", "19"), ("1 234,56", "1234.56"), ("250.00", "250.00")])
def test_decimal_normalization(text, expected):
    assert amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["1,234", "1.234", "$570.00", "1,23,456.78", "NaN", True, 1.25, "1 2"])
def test_ambiguous_or_wrong_currency_is_not_guessed(text):
    with pytest.raises(ValueError):
        amount(text)


def test_dates_and_half_up():
    assert day("14.07.2026").isoformat() == "2026-07-14"
    assert day("Jul 14, 2026").isoformat() == "2026-07-14"
    assert money("1.005") == Decimal("1.01")
    with pytest.raises(ValueError):
        day("07/08/2026")


def test_fixture_arithmetic(order):
    assert [line.net for line in order.items] == [Decimal("450.00"), Decimal("120.00")]
    assert [line.gross_master for line in order.items] == [Decimal("297.50"), Decimal("47.60")]
    assert order.debtor.billing != order.debtor.delivery


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(source_total="678.31"),
    lambda p: p["items"][0].update(source_net="500.00"),
    lambda p: p.update(extraction_issues=["Unclear customer name"]),
    lambda p: p.update(shipping_net="10.00"),
    lambda p: p.update(order_discount_percent="5"),
])
def test_validation_review_conditions(payload, mutation):
    mutation(payload)
    with pytest.raises(ReviewRequired):
        OrderInput.model_validate(payload).reconcile()


@pytest.mark.parametrize("mutation", [
    lambda p: p["payment"].update(date=None),
    lambda p: p["payment"].update(status="MAYBE"),
    lambda p: p["payment"].update(status="UNPAID"),
    lambda p: p["debtor"].update(company=""),
    lambda p: p.update(currency="USD"),
    lambda p: p["items"][0].update(quantity="0"),
    lambda p: p["items"][0].update(discount_percent="101"),
])
def test_missing_or_conflicting_required_fields(payload, mutation):
    mutation(payload)
    with pytest.raises(ValidationError):
        OrderInput.model_validate(payload)


def test_exact_match_conflicts():
    assert exact_match([], {"sku": "A"}, identity="sku") is None
    assert exact_match([{"sku": " A "}], {"sku": "a"}, identity="sku")
    for rows in ([{"sku": "A"}, {"sku": "A"}], [{"name": "VAT 19%", "code": "Z"}]):
        expected = {"sku": "A"} if "sku" in rows[0] else {"name": "VAT 19%", "code": "S"}
        with pytest.raises(ReviewRequired):
            exact_match(rows, expected, identity=next(iter(expected)))


@pytest.mark.parametrize("method,code", [("Bank Transfer", "Credit transfer"), ("Credit Card", "Credit card"), ("SEPA Direct Debit", "SEPA direct debit")])
def test_payment_mapping(method, code):
    definition = payment_definition(method)
    assert definition["code"] == code
    assert definition["standard"] is False
    assert definition["account"] == ""


def test_unsupported_payment():
    with pytest.raises(ReviewRequired):
        payment_definition("Wire-ish")
