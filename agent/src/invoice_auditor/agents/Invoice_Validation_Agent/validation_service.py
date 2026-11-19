
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

CENT = Decimal("0.01")

def is_missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and not value.strip()
    )


def as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
