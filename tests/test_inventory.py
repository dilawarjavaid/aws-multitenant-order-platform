import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "true",
    reason="Set RUN_DB_TESTS=true to run PostgreSQL integration tests",
)


@pytest.fixture
def inventory_setup(monkeypatch):
    from app import order_service
    from app.database import engine
    from app.models import Product, Tenant
    from app.schemas import OrderCreate

    test_engine = create_engine(
        engine.url.set(database="order_platform_test")
    )

    try:
        with test_engine.connect() as connection:
            transaction = connection.begin()
            sessions = sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

            try:
                monkeypatch.setattr(order_service, "SessionLocal", sessions)

                tenant_id = uuid4()
                product_id = uuid4()

                with sessions.begin() as session:
                    session.add(
                        Tenant(id=tenant_id, name="Inventory Test Retailer")
                    )
                    session.flush()
                    session.add(
                        Product(
                            id=product_id,
                            tenant_id=tenant_id,
                            name="Inventory Test Product",
                            currency="USD",
                            unit_price_minor=1999,
                            stock_quantity=10,
                        )
                    )

                # Repeated product lines should become one reservation.
                order = order_service.create_order(
                    tenant_id,
                    OrderCreate(
                        items=[
                            {"product_id": product_id, "quantity": 2},
                            {"product_id": product_id, "quantity": 3},
                        ]
                    ),
                )

                yield sessions, tenant_id, product_id, order.id
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()


def test_reservation_deducts_stock_only_once(inventory_setup):
    from app.inventory import reserve_inventory
    from app.models import InventoryReservation, Product

    sessions, tenant_id, product_id, order_id = inventory_setup

    with sessions.begin() as session:
        reservations = reserve_inventory(session, tenant_id, order_id)

        assert len(reservations) == 1
        assert reservations[0].quantity == 5
        reservation_id = reservations[0].id

    # Retry in a separate session.
    with sessions.begin() as session:
        repeated = reserve_inventory(session, tenant_id, order_id)

        assert len(repeated) == 1
        assert repeated[0].id == reservation_id

    with sessions() as session:
        product = session.get(Product, product_id)
        saved = session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order_id
            )
        ).all()

        assert product is not None
        assert product.stock_quantity == 5
        assert len(saved) == 1
        assert saved[0].quantity == 5

def test_insufficient_stock_leaves_no_reservation(inventory_setup):
    from app.inventory import InsufficientStockError, reserve_inventory
    from app.models import InventoryReservation, Product

    sessions, tenant_id, product_id, order_id = inventory_setup

    # The order needs 5 units, but only 4 are available.
    with sessions.begin() as session:
        product = session.get(Product, product_id)
        assert product is not None
        product.stock_quantity = 4

    with pytest.raises(InsufficientStockError, match="Insufficient stock"):
        with sessions.begin() as session:
            reserve_inventory(session, tenant_id, order_id)

    with sessions() as session:
        product = session.get(Product, product_id)
        reservations = session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order_id
            )
        ).all()

        assert product is not None
        assert product.stock_quantity == 4
        assert reservations == []

def test_later_failure_rolls_back_stock_and_reservation(inventory_setup):
    from app.inventory import reserve_inventory
    from app.models import InventoryReservation, Product

    sessions, tenant_id, product_id, order_id = inventory_setup

    with pytest.raises(RuntimeError, match="Simulated processing failure"):
        with sessions.begin() as session:
            reserve_inventory(session, tenant_id, order_id)
            raise RuntimeError("Simulated processing failure")

    with sessions() as session:
        product = session.get(Product, product_id)
        reservations = session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order_id
            )
        ).all()

        assert product is not None
        assert product.stock_quantity == 10
        assert reservations == []

def test_concurrent_orders_cannot_oversell():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import delete, text

    from app.database import engine
    from app.inventory import InsufficientStockError, reserve_inventory
    from app.models import (
        InventoryReservation,
        Order,
        OrderItem,
        Product,
        Tenant,
    )

    test_engine = create_engine(
        engine.url.set(database="order_platform_test"),
        pool_size=2,
        max_overflow=0,
    )
    sessions = sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
    )

    tenant_id = uuid4()
    product_id = uuid4()
    order_ids = [uuid4(), uuid4()]
    barrier = Barrier(2)

    def reserve(order_id):
        barrier.wait(timeout=10)

        try:
            with sessions.begin() as session:
                session.execute(text("SET LOCAL lock_timeout = '5s'"))
                reserve_inventory(session, tenant_id, order_id)
            return "reserved"
        except InsufficientStockError:
            return "insufficient"

    try:
        # Commit setup so both independent connections can see it.
        with sessions.begin() as session:
            session.add(
                Tenant(id=tenant_id, name="Concurrent Inventory Retailer")
            )
            session.flush()

            session.add(
                Product(
                    id=product_id,
                    tenant_id=tenant_id,
                    name="Contended Product",
                    currency="USD",
                    unit_price_minor=1999,
                    stock_quantity=10,
                )
            )
            session.add_all(
                [
                    Order(id=order_id, tenant_id=tenant_id)
                    for order_id in order_ids
                ]
            )
            session.flush()

            session.add_all(
                [
                    OrderItem(
                        order_id=order_id,
                        product_id=product_id,
                        quantity=7,
                        unit_price_minor=1999,
                        currency="USD",
                    )
                    for order_id in order_ids
                ]
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(reserve, order_id)
                for order_id in order_ids
            ]
            results = [future.result(timeout=20) for future in futures]

        assert sorted(results) == ["insufficient", "reserved"]

        with sessions() as session:
            product = session.get(Product, product_id)
            reservations = session.scalars(
                select(InventoryReservation).where(
                    InventoryReservation.order_id.in_(order_ids)
                )
            ).all()

            assert product is not None
            assert product.stock_quantity == 3
            assert len(reservations) == 1
            assert reservations[0].quantity == 7
    finally:
        # Remove only the records created by this test.
        try:
            with sessions.begin() as session:
                session.execute(
                    delete(InventoryReservation).where(
                        InventoryReservation.order_id.in_(order_ids)
                    )
                )
                session.execute(
                    delete(OrderItem).where(
                        OrderItem.order_id.in_(order_ids)
                    )
                )
                session.execute(
                    delete(Order).where(Order.id.in_(order_ids))
                )
                session.execute(
                    delete(Product).where(Product.id == product_id)
                )
                session.execute(
                    delete(Tenant).where(Tenant.id == tenant_id)
                )
        finally:
            test_engine.dispose()