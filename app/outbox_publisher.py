from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.events import EventMessage
from app.models import OutboxEvent


def publish_pending_events(
    send: Callable[[EventMessage], None],
    batch_size: int = 10,
) -> int:
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")

    with SessionLocal.begin() as session:
        events = session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()

        for event in events:
            message = EventMessage(
                event_id=event.id,
                event_type=event.event_type,
                tenant_id=event.tenant_id,
                order_id=event.aggregate_id,
                occurred_at=event.created_at,
                payload=event.payload,
            )

            send(message)
            event.published_at = datetime.now(timezone.utc)

    return len(events)