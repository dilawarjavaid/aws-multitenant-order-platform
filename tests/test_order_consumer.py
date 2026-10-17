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
def consumer_setup(monkeypatch):
    from app import order_consumer, order_service
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
                monkeypatch.setattr(order_consumer, "SessionLocal", sessions)

                tenant_id = uuid4()
                product_id = uuid4()

                with sessions.begin() as session:
                    session.add(
                        Tenant(id=tenant_id, name="Consumer Test Retailer")
                    )
                    session.flush()

                    session.add(
                        Product(
                            id=product_id,
                            tenant_id=tenant_id,
                            name="Consumer Test Product",
                            currency="USD",
                            unit_price_minor=1999,
                            stock_quantity=10,
                        )
                    )

                order = order_service.create_order(
                    tenant_id,
                    OrderCreate(
                        items=[
                            {"product_id": product_id, "quantity": 2}
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

                yield sessions, message
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()


def test_duplicate_event_is_processed_once(consumer_setup):
    from app.models import Order, ProcessedEvent
    from app.order_consumer import CONSUMER_NAME, process_order_created

    sessions, message = consumer_setup

    assert process_order_created(message) is True
    assert process_order_created(message) is False

    with sessions() as session:
        receipts = session.scalars(
            select(ProcessedEvent).where(
                ProcessedEvent.consumer_name == CONSUMER_NAME,
                ProcessedEvent.event_id == message.event_id,
            )
        ).all()

        assert len(receipts) == 1

        order = session.get(Order, message.order_id)
        assert order is not None
        assert order.status == "pending"


def test_failed_processing_rolls_back_receipt(consumer_setup):
    from app.models import ProcessedEvent
    from app.order_consumer import CONSUMER_NAME, process_order_created

    sessions, message = consumer_setup

    # Use a nonexistent order ID in both the envelope and payload.
    missing_order_id = uuid4()
    invalid_message = message.model_copy(
        update={
            "order_id": missing_order_id,
            "payload": {
                **message.payload,
                "order_id": str(missing_order_id),
            },
        }
    )

    with pytest.raises(
        ValueError,
        match="Order not found for event tenant",
    ):
        process_order_created(invalid_message)

    # Failed processing must roll back the receipt.
    with sessions() as session:
        receipt = session.get(
            ProcessedEvent,
            (CONSUMER_NAME, message.event_id),
        )

        assert receipt is None

    # The original valid message can still be processed.
    assert process_order_created(message) is True
    assert process_order_created(message) is False