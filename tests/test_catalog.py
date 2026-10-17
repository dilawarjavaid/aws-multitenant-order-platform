import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "true",
    reason="Set RUN_DB_TESTS=true to run PostgreSQL integration tests",
)


@pytest.fixture
def catalog_setup():
    from app.database import engine
    from app.models import Product, Tenant

    test_engine = create_engine(
        engine.url.set(database="order_platform_test")
    )

    try:
        with test_engine.connect() as connection:
            transaction = connection.begin()

            try:
                with Session(bind=connection) as session:
                    owner_id = uuid4()
                    other_id = uuid4()
                    product_id = uuid4()

                    session.add_all(
                        [
                            Tenant(id=owner_id, name="Catalog Owner"),
                            Tenant(id=other_id, name="Other Retailer"),
                        ]
                    )
                    session.flush()

                    session.add(
                        Product(
                            id=product_id,
                            tenant_id=owner_id,
                            name="Test Product",
                            currency="USD",
                            unit_price_minor=1999,
                            stock_quantity=10,
                        )
                    )
                    session.flush()

                    yield session, owner_id, other_id, product_id
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()


def test_accepts_product_owned_by_tenant(catalog_setup):
    from app.catalog import get_order_products
    from app.schemas import OrderCreate

    session, owner_id, _, product_id = catalog_setup
    request = OrderCreate(
        items=[{"product_id": product_id, "quantity": 2}]
    )

    products = get_order_products(session, owner_id, request)

    assert set(products) == {product_id}
    assert products[product_id].unit_price_minor == 1999
    assert products[product_id].stock_quantity == 10


def test_rejects_another_tenants_product(catalog_setup):
    from app.catalog import ProductNotAvailableError, get_order_products
    from app.schemas import OrderCreate

    session, _, other_id, product_id = catalog_setup
    request = OrderCreate(
        items=[{"product_id": product_id, "quantity": 2}]
    )

    with pytest.raises(ProductNotAvailableError):
        get_order_products(session, other_id, request)


def test_rejects_order_with_a_missing_product(catalog_setup):
    from app.catalog import ProductNotAvailableError, get_order_products
    from app.schemas import OrderCreate

    session, owner_id, _, product_id = catalog_setup
    request = OrderCreate(
        items=[
            {"product_id": product_id, "quantity": 1},
            {"product_id": uuid4(), "quantity": 1},
        ]
    )

    with pytest.raises(ProductNotAvailableError):
        get_order_products(session, owner_id, request)