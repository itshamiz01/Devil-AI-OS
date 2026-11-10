"""Currency-safe money (§5.1, §14).

Amounts are integer minor units end-to-end. ``Decimal`` is used only
at the parse/format boundary; floats are rejected outright — a float
amount raises instead of being silently rounded, so no binary
floating-point value can ever enter a financial computation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from ..core.exceptions import ValidationError
from . import constants as C


class CurrencyRegistry:
    """Currency code -> minor-unit exponent. Seeded from ISO 4217
    defaults; the owner may extend/override via ``financial.currencies``
    in system_config (applied at service construction)."""

    def __init__(self, overrides: dict | None = None):
        self._exponents: dict[str, int] = dict(C.DEFAULT_CURRENCIES)
        for code, exp in (overrides or {}).items():
            self._exponents[str(code).upper()] = int(exp)

    def exponent(self, currency: str) -> int:
        code = str(currency or "").upper()
        if code not in self._exponents:
            raise ValidationError(
                f"unknown currency {currency!r}: not in the configured "
                "currency registry (owner may add it to financial.currencies)")
        return self._exponents[code]

    def is_known(self, currency: str) -> bool:
        return str(currency or "").upper() in self._exponents

    def codes(self) -> list[str]:
        return sorted(self._exponents)


@dataclass(frozen=True)
class Money:
    """An amount in integer minor units of one currency."""

    minor: int
    currency: str

    def __post_init__(self):
        if isinstance(self.minor, bool) or not isinstance(self.minor, int):
            raise ValidationError("money minor units must be an integer")
        object.__setattr__(self, "currency", str(self.currency).upper())

    # -- arithmetic (same-currency only; conversion is explicit, §14)
    def _same(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValidationError(
                f"currency mismatch: {self.currency} vs {other.currency} — "
                "convert explicitly with a documented rate first (§14)")

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.minor - other.minor, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.minor, self.currency)

    def __eq__(self, other) -> bool:
        return (isinstance(other, Money) and self.minor == other.minor
                and self.currency == other.currency)

    def __lt__(self, other: "Money") -> bool:
        self._same(other)
        return self.minor < other.minor

    def __le__(self, other: "Money") -> bool:
        self._same(other)
        return self.minor <= other.minor

    def __hash__(self):
        return hash((self.minor, self.currency))

    @property
    def is_zero(self) -> bool:
        return self.minor == 0

    def to_decimal_string(self, registry: CurrencyRegistry) -> str:
        return decimal_string(self.minor, self.currency, registry)


def parse_amount(value, currency: str, registry: CurrencyRegistry,
                 *, field: str = "amount") -> Money:
    """Parse an API amount into Money. Accepts decimal strings and
    integers (whole major units are NOT assumed — an int is rejected
    to avoid unit ambiguity, except 0). Floats are always rejected."""
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a decimal string")
    if isinstance(value, float):
        raise ValidationError(
            f"{field}: floating-point amounts are forbidden (§5.1); "
            "pass a decimal string such as \"10000.00\"")
    if isinstance(value, int):
        if value == 0:
            return Money(0, currency)
        raise ValidationError(
            f"{field}: pass a decimal string such as \"10000.00\" "
            "(bare integers are ambiguous about units)")
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a decimal string")
    text = value.strip().replace(",", "")
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{field}: {value!r} is not a valid decimal amount")
    if amount.is_nan() or amount.is_infinite():
        raise ValidationError(f"{field}: amount must be finite")
    exponent = registry.exponent(currency)
    scaled = amount.scaleb(exponent)
    if scaled != scaled.to_integral_value():
        raise ValidationError(
            f"{field}: {value!r} has more precision than currency "
            f"{currency.upper()} allows ({exponent} decimal places)")
    return Money(int(scaled), currency)


def from_minor(minor: int, currency: str) -> Money:
    return Money(int(minor), currency)


def require_positive(money: Money, *, field: str = "amount") -> Money:
    if money.minor <= 0:
        raise ValidationError(f"{field} must be positive")
    return money


def require_non_negative(money: Money, *, field: str = "amount") -> Money:
    if money.minor < 0:
        raise ValidationError(f"{field} cannot be negative")
    return money


def decimal_string(minor: int, currency: str, registry: CurrencyRegistry) -> str:
    exponent = registry.exponent(currency)
    value = Decimal(int(minor)).scaleb(-exponent)
    quant = Decimal(1).scaleb(-exponent)
    return str(value.quantize(quant, rounding=ROUND_HALF_EVEN))


def convert(money: Money, to_currency: str, rate: Decimal,
            registry: CurrencyRegistry) -> Money:
    """Convert with an explicit documented rate (units of target per
    1 unit of source). Banker's rounding at the target exponent."""
    if money.currency == to_currency.upper():
        return money
    if not isinstance(rate, Decimal) or rate <= 0:
        raise ValidationError("conversion requires a positive Decimal rate")
    from_exp = registry.exponent(money.currency)
    to_exp = registry.exponent(to_currency)
    major = Decimal(money.minor).scaleb(-from_exp)
    converted = (major * rate).scaleb(to_exp)
    rounded = converted.quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    return Money(int(rounded), to_currency)


def _indian_group(int_part: str) -> str:
    """Indian digit grouping: last 3 digits, then pairs (1,23,456)."""
    if len(int_part) <= 3:
        return int_part
    head, tail = int_part[:-3], int_part[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def _western_group(int_part: str) -> str:
    parts = []
    while len(int_part) > 3:
        parts.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    if int_part:
        parts.insert(0, int_part)
    return ",".join(parts)


_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def format_money(money: Money, registry: CurrencyRegistry) -> str:
    """Human display: symbol + grouped amount + explicit code.
    INR uses Indian grouping; other currencies western grouping."""
    text = decimal_string(money.minor, money.currency, registry)
    negative = text.startswith("-")
    text = text.lstrip("-")
    if "." in text:
        int_part, frac_part = text.split(".")
    else:
        int_part, frac_part = text, ""
    grouped = (_indian_group(int_part) if money.currency == "INR"
               else _western_group(int_part))
    rendered = grouped + (f".{frac_part}" if frac_part else "")
    symbol = _SYMBOLS.get(money.currency, "")
    sign = "-" if negative else ""
    return f"{sign}{symbol}{rendered} {money.currency}".strip()
