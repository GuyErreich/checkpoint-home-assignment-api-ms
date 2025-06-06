import boto3
from mypy_boto3_ssm import SSMClient


def get_token_from_ssm(param_name: str) -> str:
    ssm: SSMClient = boto3.client("ssm")
    response = ssm.get_parameter(Name=param_name, WithDecryption=True)
    value = response["Parameter"]["Value"]
    if not isinstance(value, str):
        raise ValueError(f"Expected string value from SSM parameter {param_name}")
    return value
