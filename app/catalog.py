from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.schemas import OrderCreate


class ProductNotAvailableError(Exception):
    pass


def get_order_products(
    session: Session,
    tenant_id: UUID,
    request: OrderCreate,
) -> dict[UUID, Product]:
    requested_ids = {item.product_id for item in request.items}

    products = session.scalars(
        select(Product).where(
            Product.tenant_id == tenant_id,
            Product.id.in_(requested_ids),
        )
    ).all()

    products_by_id = {product.id: product for product in products}

    if requested_ids != set(products_by_id):
        raise ProductNotAvailableError(
            "One or more products are unavailable for this retailer"
        )

    return products_by_id