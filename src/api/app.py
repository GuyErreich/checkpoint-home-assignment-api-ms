import json
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, request
from mypy_boto3_sqs import SQSClient

from .config import AWS_REGION, SQS_URL, TOKEN_SSM_PARAM, logger
from .deps import get_token_from_ssm

# Initialize AWS clients - fail fast if not possible
try:
    logger.debug("Initializing SQS client")
    sqs: SQSClient = boto3.client("sqs", region_name=AWS_REGION)
    logger.info("AWS SQS client initialized successfully")
except (BotoCoreError, ClientError) as e:
    logger.error(f"Failed to initialize SQS client: {e}")
    raise SystemExit(1) from e


def create_app() -> Flask:
    """Application factory function."""
    app: Flask = Flask(__name__)

    @app.route("/", methods=["GET"])
    def health_check() -> tuple[dict[str, Any], int]:
        """Health check endpoint."""
        logger.debug("Health check request received")
        return {
            "status": "healthy",
            "service": "checkpoint-home-assignment-api-ms",
            "endpoints": ["/submit"],
        }, 200

    @app.route("/submit", methods=["POST"])
    def submit() -> tuple[dict[str, Any], int]:
        logger.debug("Received submit request")

        try:
            data: dict[str, Any] = request.get_json(force=True)
            logger.debug(f"Request data received: {list(data.keys())}")
        except Exception as e:
            logger.error(f"Failed to parse JSON request: {e}")
            return {"error": "Invalid JSON payload"}, 400

        token: str | None = data.get("token")
        timestream: str | None = data.get("email_timestream")

        if not token or not timestream:
            logger.warning("Missing required fields in request")
            return {"error": "Missing token or email_timestream"}, 400

        try:
            expected_token: str = get_token_from_ssm(TOKEN_SSM_PARAM)
            logger.debug("Token retrieved from SSM successfully")
        except Exception as e:
            logger.error(f"Failed to retrieve token from SSM: {e}")
            return {"error": "Internal server error"}, 500

        if token != expected_token:
            logger.warning("Invalid token provided")
            return {"error": "Invalid token"}, 403

        try:
            datetime.fromisoformat(timestream)
            logger.debug("Timestream format validated successfully")
        except ValueError:
            logger.warning(f"Invalid timestream format: {timestream}")
            return {"error": "Invalid timestream format"}, 400

        try:
            response = sqs.send_message(QueueUrl=SQS_URL, MessageBody=json.dumps(data))
            message_id = response.get("MessageId", "unknown")
            logger.info(f"Message sent to SQS successfully: {message_id}")
            return {"message": "Payload accepted and queued."}, 200
        except Exception as e:
            logger.error(f"Failed to send message to SQS: {e}")
            return {"error": "Failed to queue message"}, 500

    return app


# Create the app instance for Gunicorn
app = create_app()


if __name__ == "__main__":
    logger.info("Starting Flask application")
    try:
        app.run(host="0.0.0.0", port=80)
    except Exception as e:
        logger.error(f"Failed to start Flask application: {e}")
        raise SystemExit(1) from e
