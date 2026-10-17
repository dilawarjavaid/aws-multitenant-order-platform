from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal
from app.events import EventMessage
from app.models import Order, ProcessedEvent


CONSUMER_NAME = "order-receipt-v1"


def process_order_created(message: EventMessage) -> bool:
    if message.event_type != "OrderCreated":
        raise ValueError("Unsupported event type")

    if message.payload.get("schema_version") != 1:
        raise ValueError("Unsupported event schema version")

    if message.payload.get("order_id") != str(message.order_id):
        raise ValueError("Payload order ID does not match envelope")

    if message.payload.get("tenant_id") != str(message.tenant_id):
        raise ValueError("Payload tenant ID does not match envelope")

    with SessionLocal.begin() as session:
        statement = (
            insert(ProcessedEvent)
            .values(
                consumer_name=CONSUMER_NAME,
                event_id=message.event_id,
            )
            .on_conflict_do_nothing(
                index_elements=["consumer_name", "event_id"]
            )
            .returning(ProcessedEvent.event_id)
        )

        inserted_id = session.execute(statement).scalar_one_or_none()

        if inserted_id is None:
            return False

        order = session.scalar(
            select(Order).where(
                Order.id == message.order_id,
                Order.tenant_id == message.tenant_id,
            )
        )

        if order is None:
            raise ValueError("Order not found for event tenant")

    return True