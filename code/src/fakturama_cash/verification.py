from .errors import ReviewRequired
from .normalize import amount, day, key

NUMERIC = {"quantity", "unit_net", "vat_percent", "discount_percent", "source_net",
           "net", "vat", "total", "discount", "shipping", "value", "gross", "cost", "stock",
           "discount_days", "net_days"}
DATES = {"date", "order_date", "invoice_date", "service_date", "payment_date"}


def equal(actual, expected, field=""):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and equal(actual[k], v, k) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(equal(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, bool) or expected is None:
        return actual is expected
    try:
        if field in NUMERIC:
            return amount(actual) == amount(expected)
        if field in DATES:
            return day(actual) == day(expected)
    except (ValueError, TypeError):
        return False
    return key(actual) == key(expected)


def require(actual, expected, stage):
    if not equal(actual, expected):
        raise ReviewRequired("Displayed or persisted values do not match", stage=stage, expected=expected, observed=actual)


def document_row(rows, expected, stage):
    candidates = [row for row in rows if row.get("type") == expected["type"] and row.get("no") == expected["no"]]
    if len(candidates) != 1:
        raise ReviewRequired("Expected one persisted document row", stage=stage, expected=expected, observed=candidates)
    require(candidates[0], expected, stage)
    return candidates[0]
