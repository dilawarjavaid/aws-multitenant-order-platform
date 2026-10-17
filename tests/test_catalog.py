import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
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

@pytest.mark.parametrize("product_case", ["other_tenant", "missing"])
def test_create_order_rejects_unavailable_products(
    catalog_setup,
    monkeypatch,
    product_case,
):
    from sqlalchemy.orm import sessionmaker

    from app import order_service
    from app.catalog import ProductNotAvailableError
    from app.models import Order, OutboxEvent
    from app.schemas import OrderCreate

    session, owner_id, other_id, product_id = catalog_setup

    # Bind the service to the fixture's existing test transaction.
    sessions = sessionmaker(
        bind=session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(order_service, "SessionLocal", sessions)

    if product_case == "other_tenant":
        tenant_id = other_id
        requested_product_id = product_id
    else:
        tenant_id = owner_id
        requested_product_id = uuid4()

    request = OrderCreate(
        items=[
            {
                "product_id": requested_product_id,
                "quantity": 1,
            }
        ]
    )

    with pytest.raises(ProductNotAvailableError):
        order_service.create_order(tenant_id, request)

    orders = session.scalars(
        select(Order).where(Order.tenant_id == tenant_id)
    ).all()

    events = session.scalars(
        select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id)
    ).all()

    assert orders == []
    assert events == []

def test_api_rejects_another_tenants_product(catalog_setup, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import order_service
    from app.main import app
    from app.models import Order, OutboxEvent

    session, _, other_id, product_id = catalog_setup

    sessions = sessionmaker(
        bind=session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(order_service, "SessionLocal", sessions)
    monkeypatch.setenv("ENABLE_DEV_ORDER_API", "true")

    with TestClient(app) as client:
        response = client.post(
            "/orders",
            headers={"X-Tenant-ID": str(other_id)},
            json={
                "items": [
                    {
                        "product_id": str(product_id),
                        "quantity": 1,
                    }
                ]
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "One or more products are unavailable for this retailer"
    }

    orders = session.scalars(
        select(Order).where(Order.tenant_id == other_id)
    ).all()

    events = session.scalars(
        select(OutboxEvent).where(OutboxEvent.tenant_id == other_id)
    ).all()

    assert orders == []
    assert events == []

def test_order_keeps_price_after_catalog_changes(catalog_setup, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app import order_service
    from app.models import OrderItem, Product
    from app.schemas import OrderCreate

    session, owner_id, _, product_id = catalog_setup

    sessions = sessionmaker(
        bind=session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(order_service, "SessionLocal", sessions)

    request = OrderCreate(
        items=[{"product_id": product_id, "quantity": 2}]
    )
    order = order_service.create_order(owner_id, request)

    # Change the catalog price after the order has been created.
    with sessions.begin() as update_session:
        product = update_session.get(Product, product_id)
        assert product is not None
        product.unit_price_minor = 2999

    # Read the stored order price independently of the catalog.
    with sessions() as read_session:
        item = read_session.scalar(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )
        product = read_session.get(Product, product_id)

        assert item is not None
        assert product is not None
        assert product.unit_price_minor == 2999
        assert item.unit_price_minor == 1999
        assert item.currency == "USD"
        assert item.quantity == 2

def test_api_returns_saved_order_prices(catalog_setup, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import order_service
    from app.main import app
    from app.models import Product

    session, owner_id, _, product_id = catalog_setup

    sessions = sessionmaker(
        bind=session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(order_service, "SessionLocal", sessions)
    monkeypatch.setenv("ENABLE_DEV_ORDER_API", "true")

    headers = {"X-Tenant-ID": str(owner_id)}

    with TestClient(app) as client:
        created = client.post(
            "/orders",
            headers=headers,
            json={
                "items": [
                    {
                        "product_id": str(product_id),
                        "quantity": 2,
                    }
                ]
            },
        )

        assert created.status_code == 201
        order = created.json()
        assert order["items"][0]["unit_price_minor"] == 1999
        assert order["items"][0]["currency"] == "USD"

        # A later catalog price change must not alter the API's order price.
        with sessions.begin() as update_session:
            product = update_session.get(Product, product_id)
            assert product is not None
            product.unit_price_minor = 2999

        retrieved = client.get(
            f"/orders/{order['id']}",
            headers=headers,
        )

        assert retrieved.status_code == 200
        assert retrieved.json()["items"][0]["unit_price_minor"] == 1999
        assert retrieved.json()["items"][0]["currency"] == "USD"