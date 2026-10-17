import json
from datetime import datetime, timezone
from uuid import uuid4

from app.events import EventMessage


def test_event_message_serializes_to_json():
    event_id = uuid4()
    tenant_id = uuid4()
    order_id = uuid4()

    message = EventMessage(
        event_id=event_id,
        event_type="OrderCreated",
        tenant_id=tenant_id,
        order_id=order_id,
        occurred_at=datetime(2026, 10, 17, tzinfo=timezone.utc),
        payload={"schema_version": 1, "items": []},
    )

    body = json.loads(message.model_dump_json())

    assert body["event_id"] == str(event_id)
    assert body["event_type"] == "OrderCreated"
    assert body["tenant_id"] == str(tenant_id)
    assert body["order_id"] == str(order_id)
    assert body["occurred_at"] == "2026-10-17T00:00:00Z"
    assert body["payload"] == {"schema_version": 1, "items": []}