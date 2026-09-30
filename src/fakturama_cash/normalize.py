"""Deliberately conservative normalization: ambiguity is a review condition."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def amount(value):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("Amounts must be decimal strings, integers or Decimal, not floats/bools")
    if isinstance(value, (Decimal, int)):
        result = Decimal(value)
    else:
        text = str(value).strip().replace("\u00a0", " ")
        text = re.sub(r"^(EUR|€)\s*|\s*(EUR|€|%)$", "", text).strip()
        if not re.fullmatch(r"[+-]?[\d., ]+", text):
            raise ValueError(f"Invalid decimal value: {value!r}")
        if " " in text:
            if not re.fullmatch(r"[+-]?\d{1,3}( \d{3})+([.,]\d{1,2})?", text):
                raise ValueError("Invalid grouping")
            text = text.replace(" ", "")
        if "," in text and "." in text:
            decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
            grouping = "." if decimal_separator == "," else ","
            integer, fraction = text.rsplit(decimal_separator, 1)
            if not re.fullmatch(r"[+-]?\d{1,3}(" + re.escape(grouping) + r"\d{3})+", integer):
                raise ValueError("Invalid thousands grouping")
            text = integer.replace(grouping, "") + "." + fraction
        elif text.count(",") + text.count("."):
            separator = "," if "," in text else "."
            if text.count(separator) != 1:
                raise ValueError("Ambiguous grouping")
            integer, fraction = text.split(separator)
            # 1,234 / 1.234 could mean a decimal or thousands. Do not guess locale.
            if len(fraction) == 3:
                raise ValueError("Ambiguous three-digit fractional/grouping value")
            text = integer + "." + fraction
        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("Invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("Non-finite decimal")
    return result


def day(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError("Date must be unambiguous: ISO, DD.MM.YYYY or named month")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def key(value):
    # Whitespace/case differences are presentation-only; punctuation is identity.
    return " ".join(str(value).split()).casefold()
