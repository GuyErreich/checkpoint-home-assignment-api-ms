import os
import json
from typing import Any
from flask import Flask, request
from datetime import datetime
from .deps import get_token_from_ssm
import boto3
from mypy_boto3_sqs import SQSClient

app: Flask = Flask(__name__)

sqs: SQSClient = boto3.client("sqs")
SQS_QUEUE_URL: str | None = os.environ.get("SQS_QUEUE_URL")
TOKEN_SSM_PARAM: str = os.environ.get("TOKEN_SSM_PARAM", "/api/token")


@app.route("/submit", methods=["POST"])
def submit() -> tuple[dict[str, Any], int]:
    data: dict[str, Any] = request.get_json(force=True)

    token: str | None = data.get("token")
    timestream: str | None = data.get("email_timestream")

    if not token or not timestream:
        return {"error": "Missing token or email_timestream"}, 400

    expected_token: str = get_token_from_ssm(TOKEN_SSM_PARAM)
    if token != expected_token:
        return {"error": "Invalid token"}, 403

    try:
        datetime.fromisoformat(timestream)
    except ValueError:
        return {"error": "Invalid timestream format"}, 400

    try:
        if SQS_QUEUE_URL is None:
            return {"error": "SQS_QUEUE_URL not configured"}, 500
        sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(data))
        return {"message": "Payload accepted and queued."}, 200
    except Exception as e:
        return {"error": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
