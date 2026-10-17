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
    from sqlalchemy import create_engine

    from app import order_service
    from app.database import engine
    from app.models import Order, OrderItem, OutboxEvent, Tenant
    from app.schemas import OrderCreate

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
                    session.add(
                        Tenant(id=tenant_id, name="Test Retailer")
                    )

                request = OrderCreate(
                    items=[
                        {"product_id": product_id, "quantity": 3}
                    ]
                )
                result = order_service.create_order(tenant_id, request)

                # The owning tenant can retrieve its order.
                retrieved = order_service.get_order(tenant_id, result.id)

                assert retrieved is not None
                assert retrieved.id == result.id
                assert retrieved.tenant_id == tenant_id
                assert retrieved.items[0].quantity == 3

                # Create a second, valid tenant.
                other_tenant_id = uuid4()

                with test_sessions.begin() as session:
                    session.add(
                        Tenant(
                            id=other_tenant_id,
                            name="Other Retailer",
                        )
                    )

                # Another tenant cannot retrieve the owner's order.
                assert (
                    order_service.get_order(other_tenant_id, result.id)
                    is None
                )

                # A nonexistent order also returns None.
                assert order_service.get_order(tenant_id, uuid4()) is None

                # Verify records through a separate session.
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

                    # Exactly one unpublished event accompanies the order.
                    events = session.scalars(
                        select(OutboxEvent).where(
                            OutboxEvent.aggregate_id == result.id
                        )
                    ).all()

                    assert len(events) == 1

                    event = events[0]
                    assert event.tenant_id == tenant_id
                    assert event.event_type == "OrderCreated"
                    assert event.published_at is None
                    assert event.payload == {
                        "schema_version": 1,
                        "order_id": str(result.id),
                        "tenant_id": str(tenant_id),
                        "items": [
                            {
                                "product_id": str(product_id),
                                "quantity": 3,
                            }
                        ],
                    }
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()


@pytest.mark.parametrize("failure_target", ["item", "outbox"])
def test_failed_insert_rolls_back_order(monkeypatch, failure_target):
    from sqlalchemy import create_engine, event
    from sqlalchemy.exc import IntegrityError

    from app import order_service
    from app.database import engine
    from app.models import Order, OrderItem, OutboxEvent, Tenant
    from app.schemas import OrderCreate

    test_engine = create_engine(
        engine.url.set(database="order_platform_test")
    )

    # Deliberately violate a database constraint during insertion.
    def force_invalid_insert(mapper, connection, target):
        if failure_target == "item":
            target.quantity = 0
        else:
            target.event_type = None

    failing_model = OrderItem if failure_target == "item" else OutboxEvent

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
                    session.add(
                        Tenant(id=tenant_id, name="Rollback Retailer")
                    )

                request = OrderCreate(
                    items=[{"product_id": uuid4(), "quantity": 2}]
                )

                event.listen(
                    failing_model, "before_insert", force_invalid_insert
                )
                try:
                    with pytest.raises(IntegrityError) as error:
                        order_service.create_order(tenant_id, request)
                finally:
                    event.remove(
                        failing_model, "before_insert", force_invalid_insert
                    )

                # Confirm that the intended constraint caused the failure.
                if failure_target == "item":
                    assert (
                        error.value.orig.diag.constraint_name
                        == "ck_order_items_quantity"
                    )
                else:
                    assert (
                        error.value.orig.diag.column_name == "event_type"
                    )

                # Neither the order nor its event should remain.
                with test_sessions() as session:
                    orders = session.scalars(
                        select(Order).where(Order.tenant_id == tenant_id)
                    ).all()

                    events = session.scalars(
                        select(OutboxEvent).where(
                            OutboxEvent.tenant_id == tenant_id
                        )
                    ).all()

                    assert orders == []
                    assert events == []
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()