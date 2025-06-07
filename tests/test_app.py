import json
import os
from collections.abc import Generator

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


@pytest.fixture
def client_no_queue_url(mocker: MockerFixture) -> Generator[FlaskClient, None, None]:
    # Set up environment variables without SQS_QUEUE_URL
    env_vars = {
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
    }
    # Clear SQS_QUEUE_URL if it exists
    if "SQS_QUEUE_URL" in os.environ:
        env_vars["SQS_QUEUE_URL"] = ""

    mocker.patch.dict(os.environ, env_vars, clear=True)

    # Mock boto3 client
    mock_sqs = mocker.MagicMock()
    mocker.patch("boto3.client", return_value=mock_sqs)

    # Mock SSM function
    mocker.patch("api.deps.get_token_from_ssm", return_value="correct-token")

    # Patch SQS_QUEUE_URL to be None in the app module
    mocker.patch("api.app.SQS_QUEUE_URL", None)

    # Import after mocking
    from api import app as flask_app

    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as client:
        yield client


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
    payload = {}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing token or email_timestream"


def test_submit_no_queue_url_configured(client_no_queue_url: FlaskClient) -> None:
    payload = {"token": "correct-token", "email_timestream": "2024-06-01T12:00:00"}
    response = client_no_queue_url.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 500
    assert response.get_json()["error"] == "SQS_QUEUE_URL not configured"


def test_submit_sqs_exception(client: FlaskClient, mocker: MockerFixture) -> None:
    # Mock SQS to raise an exception - need to patch the already imported sqs instance
    mock_sqs = mocker.MagicMock()
    mock_sqs.send_message.side_effect = Exception("SQS error")
    mocker.patch("api.app.sqs", mock_sqs)

    payload = {"token": "correct-token", "email_timestream": "2024-06-01T12:00:00"}
    response = client.post(
        "/submit", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 500
    assert "SQS error" in response.get_json()["error"]


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
