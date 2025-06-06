import json
import os
from typing import Any
from unittest.mock import Mock, patch

import pytest

# Mock AWS before importing the app
with (
    patch.dict(
        os.environ,
        {
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
        },
    ),
    patch("boto3.client") as mock_boto3,
):
    mock_sqs = Mock()
    mock_sqs.send_message.return_value = {"MessageId": "123"}
    mock_boto3.return_value = mock_sqs

    from api import app as flask_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    # Patch the environment variable value in the app module
    monkeypatch.setattr("api.app.SQS_QUEUE_URL", "https://dummy-url")

    # Patch SSM client
    monkeypatch.setattr("api.app.get_token_from_ssm", lambda name: "correct-token")

    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as client:
        yield client


def test_submit_success(client: Any) -> None:
    payload = {"token": "correct-token", "email_timestream": "2024-06-01T12:00:00"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200
    assert response.get_json()["message"] == "Payload accepted and queued."


def test_submit_invalid_token(client: Any) -> None:
    payload = {"token": "wrong-token", "email_timestream": "2024-06-01T12:00:00"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 403


def test_submit_invalid_time(client: Any) -> None:
    payload = {"token": "correct-token", "email_timestream": "not-a-timestamp"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
