from uuid import UUID

from app.database import SessionLocal
from app.models import Order, OrderItem, Tenant
from app.schemas import OrderCreate, OrderItemResponse, OrderResponse


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