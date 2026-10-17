from typing import Any

from app.events import EventMessage


class SqsDelivery:
    def __init__(self, client: Any, queue_url: str) -> None:
        if not queue_url.strip():
            raise ValueError("queue_url must not be empty")

        self.client = client
        self.queue_url = queue_url

    def __call__(self, message: EventMessage) -> None:
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=message.model_dump_json(),
        )