from uuid import UUID

from app.database import SessionLocal
from app.models import Order, OrderItem, Tenant
from app.schemas import OrderCreate, OrderItemResponse, OrderResponse
from sqlalchemy import select


class TenantNotFoundError(Exception):
    pass


def create_order(tenant_id: UUID, request: OrderCreate) -> OrderResponse:
    with SessionLocal.begin() as session:
        if session.get(Tenant, tenant_id) is None:
            raise TenantNotFoundError("Tenant does not exist")

        order = Order(tenant_id=tenant_id)
        session.add(order)
        session.flush()

        items = [
            OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
            )
            for item in request.items
        ]
        session.add_all(items)
        session.flush()

        response = OrderResponse(
            id=order.id,
            tenant_id=order.tenant_id,
            status=order.status,
            created_at=order.created_at,
            items=[
                OrderItemResponse.model_validate(item)
                for item in items
            ],
        )

    return response

def get_order(tenant_id: UUID, order_id: UUID) -> OrderResponse | None:
    with SessionLocal() as session:
        order = session.scalar(
            select(Order).where(
                Order.id == order_id,
                Order.tenant_id == tenant_id,
            )
        )

        if order is None:
            return None

        items = session.scalars(
            select(OrderItem)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.id)
        ).all()

        return OrderResponse(
            id=order.id,
            tenant_id=order.tenant_id,
            status=order.status,
            created_at=order.created_at,
            items=[
                OrderItemResponse.model_validate(item)
                for item in items
            ],
        )