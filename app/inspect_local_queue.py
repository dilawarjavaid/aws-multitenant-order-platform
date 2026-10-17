import json

import boto3
from botocore.config import Config


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
            VisibilityTimeout=5,
        )

        messages = response.get("Messages", [])
        if not messages:
            print("No message available.")
            return

        body = json.loads(messages[0]["Body"])
        print(json.dumps(body, indent=2))
        print("\nMessage retained; it becomes visible again after 5 seconds.")
    finally:
        client.close()


if __name__ == "__main__":
    main()