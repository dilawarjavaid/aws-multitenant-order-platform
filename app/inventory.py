from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryReservation, Order, OrderItem, Product


class InventoryError(Exception):
    pass


class InsufficientStockError(InventoryError):
    pass


def reserve_inventory(
    session: Session,
    tenant_id: UUID,
    order_id: UUID,
) -> list[InventoryReservation]:
    # Serialize reservation attempts for the same order.
    order = session.scalar(
        select(Order)
        .where(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
        )
        .with_for_update()
    )

    if order is None:
        raise InventoryError("Order not found for retailer")

    if order.status != "pending":
        raise InventoryError("Only pending orders can reserve stock")

    existing = session.scalars(
        select(InventoryReservation).where(
            InventoryReservation.order_id == order_id
        )
    ).all()

    if existing:
        return list(existing)

    items = session.scalars(
        select(OrderItem).where(OrderItem.order_id == order_id)
    ).all()

    if not items:
        raise InventoryError("Order has no items")

    quantities: dict[UUID, int] = defaultdict(int)
    for item in items:
        quantities[item.product_id] += item.quantity

    # Lock products in a consistent order to reduce deadlock risk.
    products = session.scalars(
        select(Product)
        .where(
            Product.tenant_id == tenant_id,
            Product.id.in_(quantities),
        )
        .order_by(Product.id)
        .with_for_update()
    ).all()

    if {product.id for product in products} != set(quantities):
        raise InventoryError("Products unavailable for retailer")

    # Check every product before changing any stock.
    for product in products:
        if product.stock_quantity < quantities[product.id]:
            raise InsufficientStockError("Insufficient stock")

    reservations = []

    for product in products:
        quantity = quantities[product.id]
        product.stock_quantity -= quantity

        reservation = InventoryReservation(
            order_id=order_id,
            product_id=product.id,
            quantity=quantity,
        )
        session.add(reservation)
        reservations.append(reservation)

    session.flush()
    return reservations