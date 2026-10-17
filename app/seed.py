from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal
from app.models import Product, Tenant


NORTHWIND_ID = UUID("11111111-1111-4111-8111-111111111111")
CONTOSO_ID = UUID("22222222-2222-4222-8222-222222222222")

DEMO_TENANTS = [
    {"id": NORTHWIND_ID, "name": "Northwind Retail"},
    {"id": CONTOSO_ID, "name": "Contoso Shop"},
]

DEMO_PRODUCTS = [
    {
        "id": UUID("b8f00bc2-b494-4c02-8cad-7ad0f3336290"),
        "tenant_id": NORTHWIND_ID,
        "name": "Wireless Mouse",
        "currency": "USD",
        "unit_price_minor": 1999,
        "stock_quantity": 100,
    },
    {
        "id": UUID("33333333-3333-4333-8333-333333333333"),
        "tenant_id": CONTOSO_ID,
        "name": "Mechanical Keyboard",
        "currency": "USD",
        "unit_price_minor": 7999,
        "stock_quantity": 50,
    },
]


def main() -> None:
    with SessionLocal.begin() as session:
        session.execute(
            insert(Tenant)
            .values(DEMO_TENANTS)
            .on_conflict_do_nothing(index_elements=["id"])
        )

        session.execute(
            insert(Product)
            .values(DEMO_PRODUCTS)
            .on_conflict_do_nothing(index_elements=["id"])
        )

    print("Demo tenants and products ready.")


if __name__ == "__main__":
    main()