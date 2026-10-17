import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "true",
    reason="Set RUN_DB_TESTS=true to run PostgreSQL integration tests",
)


@pytest.fixture
def outbox_setup(monkeypatch):
    from app import order_service, outbox_publisher
    from app.database import engine
    from app.models import OutboxEvent, Tenant
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
                monkeypatch.setattr(outbox_publisher, "SessionLocal", sessions)

                tenant_id = uuid4()

                with sessions.begin() as session:
                    # Temporarily exclude any pre-existing pending events.
                    # The outer rollback restores them after the test.
                    session.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.published_at.is_(None))
                        .values(published_at=func.now())
                    )
                    session.add(
                        Tenant(id=tenant_id, name="Publisher Test Retailer")
                    )

                order = order_service.create_order(
                    tenant_id,
                    OrderCreate(
                        items=[{"product_id": uuid4(), "quantity": 2}]
                    ),
                )

                yield sessions, order
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()


def test_publisher_delivers_and_marks_event(outbox_setup):
    from app.models import OutboxEvent
    from app.outbox_publisher import publish_pending_events

    sessions, order = outbox_setup
    delivered = []

    count = publish_pending_events(send=delivered.append)

    assert count == 1
    assert len(delivered) == 1

    message = delivered[0]
    assert message.order_id == order.id
    assert message.tenant_id == order.tenant_id
    assert message.event_type == "OrderCreated"

    with sessions() as session:
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == order.id
            )
        )

        assert event is not None
        assert message.event_id == event.id
        assert event.published_at is not None

    # Published events must not be sent again on the next successful run.
    assert publish_pending_events(send=delivered.append) == 0
    assert len(delivered) == 1

def test_failed_delivery_keeps_event_pending(outbox_setup):
    from app.models import OutboxEvent
    from app.outbox_publisher import publish_pending_events

    sessions, order = outbox_setup
    attempted = []

    def failing_send(message):
        attempted.append(message)
        raise RuntimeError("Simulated delivery failure")

    with pytest.raises(RuntimeError, match="Simulated delivery failure"):
        publish_pending_events(send=failing_send)

    assert len(attempted) == 1

    # Failed delivery must leave the event available for retry.
    with sessions() as session:
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == order.id
            )
        )

        assert event is not None
        assert event.published_at is None
        assert event.id == attempted[0].event_id

    # A later successful attempt delivers the same event ID.
    delivered = []
    count = publish_pending_events(send=delivered.append)

    assert count == 1
    assert len(delivered) == 1
    assert delivered[0].event_id == attempted[0].event_id

    with sessions() as session:
        event = session.get(OutboxEvent, delivered[0].event_id)

        assert event is not None
        assert event.published_at is not None