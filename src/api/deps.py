import boto3
from mypy_boto3_ssm import SSMClient

from .config import AWS_REGION, logger


def get_token_from_ssm(param_name: str) -> str:
    """Get token from SSM Parameter Store using the configured AWS region."""
    try:
        logger.debug(f"Retrieving SSM parameter: {param_name}")
        ssm: SSMClient = boto3.client("ssm", region_name=AWS_REGION)
        response = ssm.get_parameter(Name=param_name, WithDecryption=True)
        value = response["Parameter"]["Value"]
        if not isinstance(value, str):
            raise ValueError(f"Expected string value from SSM parameter {param_name}")
        logger.debug("SSM parameter retrieved successfully")
        return value
    except Exception as e:
        logger.error(f"Failed to retrieve SSM parameter {param_name}: {e}")
        raise
