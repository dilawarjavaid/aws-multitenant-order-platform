from datetime import datetime, timezone
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from app.events import EventMessage
from app.sqs_delivery import SqsDelivery


QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/orders"


@pytest.fixture
def sqs_client():
    client = boto3.client(
        "sqs",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def message():
    return EventMessage(
        event_id=uuid4(),
        event_type="OrderCreated",
        tenant_id=uuid4(),
        order_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        payload={"schema_version": 1, "items": []},
    )


def test_sends_event_as_json(sqs_client, message):
    expected_request = {
        "QueueUrl": QUEUE_URL,
        "MessageBody": message.model_dump_json(),
    }

    with Stubber(sqs_client) as stubber:
        stubber.add_response(
            "send_message",
            {"MessageId": "test-message-id"},
            expected_request,
        )

        delivery = SqsDelivery(sqs_client, QUEUE_URL)
        delivery(message)

        stubber.assert_no_pending_responses()


def test_delivery_propagates_sqs_errors(sqs_client, message):
    expected_request = {
        "QueueUrl": QUEUE_URL,
        "MessageBody": message.model_dump_json(),
    }

    with Stubber(sqs_client) as stubber:
        stubber.add_client_error(
            "send_message",
            service_error_code="ServiceUnavailable",
            service_message="Simulated SQS failure",
            http_status_code=503,
            expected_params=expected_request,
        )

        delivery = SqsDelivery(sqs_client, QUEUE_URL)

        with pytest.raises(ClientError):
            delivery(message)

        stubber.assert_no_pending_responses()


def test_rejects_empty_queue_url(sqs_client):
    with pytest.raises(ValueError, match="queue_url must not be empty"):
        SqsDelivery(sqs_client, "   ")