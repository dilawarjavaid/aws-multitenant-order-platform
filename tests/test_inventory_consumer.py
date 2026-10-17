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
def inventory_consumer_setup(monkeypatch):
    from app import inventory_consumer, order_service
    from app.database import engine
    from app.events import EventMessage
    from app.models import OutboxEvent, Product, Tenant
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
                monkeypatch.setattr(
                    inventory_consumer, "SessionLocal", sessions
                )

                tenant_id = uuid4()
                product_id = uuid4()

                with sessions.begin() as session:
                    session.add(
                        Tenant(
                            id=tenant_id,
                            name="Inventory Consumer Retailer",
                        )
                    )
                    session.flush()
                    session.add(
                        Product(
                            id=product_id,
                            tenant_id=tenant_id,
                            name="Inventory Consumer Product",
                            currency="USD",
                            unit_price_minor=1999,
                            stock_quantity=10,
                        )
                    )

                order = order_service.create_order(
                    tenant_id,
                    OrderCreate(
                        items=[
                            {"product_id": product_id, "quantity": 3}
                        ]
                    ),
                )

                with sessions() as session:
                    event = session.scalar(
                        select(OutboxEvent).where(
                            OutboxEvent.aggregate_id == order.id
                        )
                    )
                    assert event is not None

                    message = EventMessage(
                        event_id=event.id,
                        event_type=event.event_type,
                        tenant_id=event.tenant_id,
                        order_id=event.aggregate_id,
                        occurred_at=event.created_at,
                        payload=event.payload,
                    )

                yield sessions, product_id, message
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()


def test_inventory_event_reserves_stock_once(inventory_consumer_setup):
    from app.inventory_consumer import (
        CONSUMER_NAME,
        process_inventory_event,
    )
    from app.models import (
        InventoryReservation,
        Order,
        ProcessedEvent,
        Product,
    )

    sessions, product_id, message = inventory_consumer_setup

    assert process_inventory_event(message) is True
    assert process_inventory_event(message) is False

    with sessions() as session:
        product = session.get(Product, product_id)
        assert product is not None
        assert product.stock_quantity == 7

        reservations = session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == message.order_id
            )
        ).all()

        assert len(reservations) == 1
        assert reservations[0].product_id == product_id
        assert reservations[0].quantity == 3

        receipt = session.get(
            ProcessedEvent,
            (CONSUMER_NAME, message.event_id),
        )
        assert receipt is not None

        order = session.get(Order, message.order_id)
        assert order is not None
        assert order.status == "pending"

def test_insufficient_stock_can_be_retried(inventory_consumer_setup):
    from app.inventory import InsufficientStockError
    from app.inventory_consumer import (
        CONSUMER_NAME,
        process_inventory_event,
    )
    from app.models import InventoryReservation, ProcessedEvent, Product

    sessions, product_id, message = inventory_consumer_setup

    # The order requests 3 units; make only 2 available.
    with sessions.begin() as session:
        product = session.get(Product, product_id)
        assert product is not None
        product.stock_quantity = 2

    with pytest.raises(InsufficientStockError):
        process_inventory_event(message)

    with sessions() as session:
        product = session.get(Product, product_id)
        receipt = session.get(
            ProcessedEvent,
            (CONSUMER_NAME, message.event_id),
        )
        reservations = session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == message.order_id
            )
        ).all()

        assert product is not None
        assert product.stock_quantity == 2
        assert receipt is None
        assert reservations == []

    # Replenish stock and retry the same event.
    with sessions.begin() as session:
        product = session.get(Product, product_id)
        assert product is not None
        product.stock_quantity = 10

    assert process_inventory_event(message) is True
    assert process_inventory_event(message) is False

    with sessions() as session:
        product = session.get(Product, product_id)
        receipt = session.get(
            ProcessedEvent,
            (CONSUMER_NAME, message.event_id),
        )
        reservations = session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == message.order_id
            )
        ).all()

        assert product is not None
        assert product.stock_quantity == 7
        assert receipt is not None
        assert len(reservations) == 1
        assert reservations[0].quantity == 3