from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryReservation, Order, OrderItem, Payment
from app.payment_simulator import (
    PaymentValidationError,
    calculate_payment_amount,
    simulate_payment,
)
from app.schemas import OrderItemResponse


def confirm_order_payment(
    session: Session,
    tenant_id: UUID,
    order_id: UUID,
) -> Payment:
    # Serialize payment attempts for this order.
    order = session.scalar(
        select(Order)
        .where(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
        )
        .with_for_update()
    )

    if order is None:
        raise PaymentValidationError("Order not found for retailer")

    existing = session.scalar(
        select(Payment).where(Payment.order_id == order_id)
    )

    if existing is not None:
        if existing.status == "succeeded" and order.status == "confirmed":
            return existing
        raise PaymentValidationError("Order has an incompatible payment state")

    if order.status != "pending":
        raise PaymentValidationError("Only pending orders can be paid")

    items = session.scalars(
        select(OrderItem).where(OrderItem.order_id == order_id)
    ).all()

    amount_minor, currency = calculate_payment_amount(
        [OrderItemResponse.model_validate(item) for item in items]
    )

    required: dict[UUID, int] = defaultdict(int)
    for item in items:
        required[item.product_id] += item.quantity

    reservations = session.scalars(
        select(InventoryReservation).where(
            InventoryReservation.order_id == order_id
        )
    ).all()

    reserved = {
        reservation.product_id: reservation.quantity
        for reservation in reservations
    }

    if reserved != dict(required):
        raise PaymentValidationError("Order inventory is not fully reserved")

    result = simulate_payment(
        order_id,
        amount_minor,
        currency,
        approve=True,
    )

    payment = Payment(
        order_id=order_id,
        amount_minor=amount_minor,
        currency=currency,
        status=result.status,
        provider_reference=result.provider_reference,
    )
    session.add(payment)
    order.status = "confirmed"
    session.flush()

    return payment