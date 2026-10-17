import boto3
from botocore.config import Config

from app.events import EventMessage
from app.order_consumer import process_order_created


def main() -> None:
    client = boto3.client(
        "sqs",
        endpoint_url="http://localhost:9324",
        region_name="us-east-1",
        aws_access_key_id="local",
        aws_secret_access_key="local",
        config=Config(
            connect_timeout=3,
            read_timeout=10,
            retries={"mode": "standard", "total_max_attempts": 2},
        ),
    )

    try:
        queue_url = client.get_queue_url(QueueName="orders")["QueueUrl"]

        response = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
            VisibilityTimeout=30,
        )

        messages = response.get("Messages", [])
        if not messages:
            print("No message available.")
            return

        queue_message = messages[0]
        event = EventMessage.model_validate_json(queue_message["Body"])

        processed = process_order_created(event)

        # Processing has committed before we acknowledge the queue message.
        client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=queue_message["ReceiptHandle"],
        )

        if processed:
            print(f"Processed and acknowledged event {event.event_id}")
        else:
            print(f"Acknowledged duplicate event {event.event_id}")
    finally:
        client.close()


if __name__ == "__main__":
    main()