from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: str = Field(min_length=1, max_length=100)
    tenant_id: UUID
    order_id: UUID
    occurred_at: datetime
    payload: dict[str, Any]