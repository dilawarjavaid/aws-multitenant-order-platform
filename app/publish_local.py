import boto3
from botocore.config import Config

from app.outbox_publisher import publish_pending_events
from app.sqs_delivery import SqsDelivery


def main() -> None:
    client = boto3.client(
        "sqs",
        endpoint_url="http://localhost:9324",
        region_name="us-east-1",
        aws_access_key_id="local",
        aws_secret_access_key="local",
        config=Config(
            connect_timeout=3,
            read_timeout=5,
            retries={"mode": "standard", "total_max_attempts": 2},
        ),
    )

    try:
        queue_url = client.get_queue_url(QueueName="orders")["QueueUrl"]
        delivery = SqsDelivery(client, queue_url)
        count = publish_pending_events(send=delivery)
        print(f"Published {count} event(s) to the local orders queue.")
    finally:
        client.close()


if __name__ == "__main__":
    main()