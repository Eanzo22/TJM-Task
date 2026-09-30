from .errors import ReviewRequired
from .normalize import amount, key

PAYMENT_CODES = {"Bank Transfer": "Credit transfer", "Credit Card": "Credit card",
                 "SEPA Direct Debit": "SEPA direct debit"}


def exact_match(rows, expected, *, identity, numeric_fields=()):
    """Select only one exact definition; same identity with different fields is a conflict."""
    plausible = [row for row in rows if key(row.get(identity, "")) == key(expected[identity])]
    def equal(field, actual, wanted):
        if field in numeric_fields:
            try:
                return amount(actual) == amount(wanted)
            except (ValueError, TypeError):
                return False
        return key(actual) == key(wanted)

    matches = [row for row in plausible if all(equal(k, row.get(k, ""), v) for k, v in expected.items())]
    if len(plausible) > 1 or (plausible and not matches):
        raise ReviewRequired("Ambiguous or conflicting master data", expected=expected, observed=plausible)
    return matches[0] if matches else None


def payment_definition(method):
    if method not in PAYMENT_CODES:
        raise ReviewRequired("Unsupported payment method", observed=method)
    return dict(name=method, description=method, code=PAYMENT_CODES[method], account="",
                discount="0", discount_days="0", net_days="0", unpaid_text="",
                deposit_text="", paid_text="", standard=False)
