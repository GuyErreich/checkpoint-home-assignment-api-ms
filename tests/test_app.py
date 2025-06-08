import json
import os
from collections.abc import Generator
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient
from pytest_mock import MockerFixture


@pytest.fixture
def client(mocker: MockerFixture) -> Generator[FlaskClient, None, None]:
    # Set up environment variables
    mocker.patch.dict(
        os.environ,
        {
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "SQS_QUEUE_URL": "https://dummy-url",
        },
    )

    # Mock boto3 client
    mock_sqs = mocker.MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "123"}
    mocker.patch("boto3.client", return_value=mock_sqs)

    # Mock SSM function
    mocker.patch("api.deps.get_token_from_ssm", return_value="correct-token")

    # Import after mocking
    from api import app as flask_app

    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as client:
        yield client


def test_missing_environment_variable() -> None:
    """Test that the app fails fast when required environment variables are missing."""
    # Test missing AWS_DEFAULT_REGION
    with patch.dict(os.environ, {}, clear=True), pytest.raises(SystemExit):
        # This import should trigger SystemExit due to missing AWS_DEFAULT_REGION
        import api.app  # noqa: F401

    # Test missing SQS_QUEUE_URL
    with (
        patch.dict(os.environ, {"AWS_DEFAULT_REGION": "us-east-1"}, clear=True),
        pytest.raises(SystemExit),
    ):
        # This import should trigger SystemExit due to missing SQS_QUEUE_URL
        import api.app  # noqa: F401


def test_submit_success(client: FlaskClient) -> None:
    payload = {"token": "correct-token", "email_timestream": "2024-06-01T12:00:00"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200
    assert response.get_json()["message"] == "Payload accepted and queued."


def test_submit_invalid_token(client: FlaskClient) -> None:
    payload = {"token": "wrong-token", "email_timestream": "2024-06-01T12:00:00"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 403


def test_submit_invalid_time(client: FlaskClient) -> None:
    payload = {"token": "correct-token", "email_timestream": "not-a-timestamp"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400


def test_submit_missing_token(client: FlaskClient) -> None:
    payload = {"email_timestream": "2024-06-01T12:00:00"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing token or email_timestream"


def test_submit_missing_timestream(client: FlaskClient) -> None:
    payload = {"token": "correct-token"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing token or email_timestream"


def test_submit_missing_both_fields(client: FlaskClient) -> None:
    payload: dict[str, str] = {}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing token or email_timestream"


def test_submit_sqs_exception(client: FlaskClient, mocker: MockerFixture) -> None:
    # Mock SQS to raise an exception - need to patch the sqs variable directly
    mock_sqs = mocker.MagicMock()
    mock_sqs.send_message.side_effect = Exception("SQS error")
    mocker.patch("api.app.sqs", mock_sqs)

    payload = {"token": "correct-token", "email_timestream": "2024-06-01T12:00:00"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 500
    assert "Failed to queue message" in response.get_json()["error"]


def test_get_token_from_ssm(mocker: MockerFixture) -> None:
    # Mock SSM client
    mock_ssm = mocker.MagicMock()
    mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "test-token"}}
    mocker.patch("boto3.client", return_value=mock_ssm)

    from api.deps import get_token_from_ssm

    result = get_token_from_ssm("/test/param")
    assert result == "test-token"
    mock_ssm.get_parameter.assert_called_once_with(
        Name="/test/param", WithDecryption=True
    )


def test_get_token_from_ssm_invalid_type(mocker: MockerFixture) -> None:
    # Mock SSM client to return non-string value
    mock_ssm = mocker.MagicMock()
    mock_ssm.get_parameter.return_value = {
        "Parameter": {"Value": 123}  # Non-string value
    }
    mocker.patch("boto3.client", return_value=mock_ssm)

    from api.deps import get_token_from_ssm

    with pytest.raises(ValueError, match="Expected string value from SSM parameter"):
        get_token_from_ssm("/test/param")
