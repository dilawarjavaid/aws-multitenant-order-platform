from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.schemas import OrderItemResponse


class PaymentValidationError(Exception):
    pass


@dataclass(frozen=True)
class PaymentResult:
    status: Literal["succeeded", "failed"]
    provider_reference: str


def calculate_payment_amount(
    items: list[OrderItemResponse],
) -> tuple[int, str]:
    if not items:
        raise PaymentValidationError("Order has no items")

    currencies = set()
    amount_minor = 0

    for item in items:
        if item.unit_price_minor is None or item.currency is None:
            raise PaymentValidationError("Order item has no saved price")

        if item.unit_price_minor < 0 or item.quantity <= 0:
            raise PaymentValidationError("Invalid order item price or quantity")

        currencies.add(item.currency)
        amount_minor += item.unit_price_minor * item.quantity

    if len(currencies) != 1:
        raise PaymentValidationError("Order contains multiple currencies")

    currency = currencies.pop()
    if currency != "USD":
        raise PaymentValidationError("Simulator supports USD only")

    return amount_minor, currency


def simulate_payment(
    order_id: UUID,
    amount_minor: int,
    currency: str,
    *,
    approve: bool,
) -> PaymentResult:
    if amount_minor < 0:
        raise PaymentValidationError("Payment amount must not be negative")

    if currency != "USD":
        raise PaymentValidationError("Simulator supports USD only")

    return PaymentResult(
        status="succeeded" if approve else "failed",
        provider_reference=f"sim-{order_id}",
    )