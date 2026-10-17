import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "true",
    reason="Set RUN_DB_TESTS=true to run PostgreSQL integration tests",
)


def test_create_order_persists_items(monkeypatch):
    from app import order_service
    from app.database import engine
    from app.models import Order, OrderItem, Tenant
    from app.schemas import OrderCreate
    from sqlalchemy import create_engine

    test_engine = create_engine(
        engine.url.set(database="order_platform_test")
    )

    try:
        with test_engine.connect() as connection:
            transaction = connection.begin()
            test_sessions = sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

            try:
                monkeypatch.setattr(
                    order_service, "SessionLocal", test_sessions
                )

                tenant_id = uuid4()
                product_id = uuid4()

                with test_sessions.begin() as session:
                    session.add(Tenant(id=tenant_id, name="Test Retailer"))

                request = OrderCreate(
                    items=[
                        {"product_id": product_id, "quantity": 3}
                    ]
                )
                result = order_service.create_order(tenant_id, request)

                # Read through a separate session after the service commits.
                with test_sessions() as session:
                    saved_order = session.get(Order, result.id)
                    saved_items = session.scalars(
                        select(OrderItem).where(
                            OrderItem.order_id == result.id
                        )
                    ).all()

                    assert saved_order is not None
                    assert saved_order.tenant_id == tenant_id
                    assert saved_order.status == "pending"
                    assert len(saved_items) == 1
                    assert saved_items[0].product_id == product_id
                    assert saved_items[0].quantity == 3
                    assert result.items[0].id == saved_items[0].id
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()

def test_failed_item_insert_rolls_back_order(monkeypatch):
    from sqlalchemy import create_engine, event
    from sqlalchemy.exc import IntegrityError

    from app import order_service
    from app.database import engine
    from app.models import Order, OrderItem, Tenant
    from app.schemas import OrderCreate

    test_engine = create_engine(
        engine.url.set(database="order_platform_test")
    )

    def force_invalid_quantity(mapper, connection, target):
        target.quantity = 0

    try:
        with test_engine.connect() as connection:
            transaction = connection.begin()
            test_sessions = sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

            try:
                monkeypatch.setattr(
                    order_service, "SessionLocal", test_sessions
                )

                tenant_id = uuid4()

                with test_sessions.begin() as session:
                    session.add(Tenant(id=tenant_id, name="Rollback Retailer"))

                request = OrderCreate(
                    items=[{"product_id": uuid4(), "quantity": 2}]
                )

                event.listen(
                    OrderItem, "before_insert", force_invalid_quantity
                )
                try:
                    with pytest.raises(IntegrityError) as error:
                        order_service.create_order(tenant_id, request)
                finally:
                    event.remove(
                        OrderItem, "before_insert", force_invalid_quantity
                    )

                assert (
                    error.value.orig.diag.constraint_name
                    == "ck_order_items_quantity"
                )

                with test_sessions() as session:
                    orders = session.scalars(
                        select(Order).where(Order.tenant_id == tenant_id)
                    ).all()

                    assert orders == []
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()