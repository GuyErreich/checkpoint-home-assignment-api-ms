import logging
import os
import sys


class LevelBasedFormatter(logging.Formatter):
    """Custom formatter that uses different formats based on log level."""

    def __init__(self) -> None:
        # Format for INFO and above (simple)
        self.info_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        # Format for DEBUG (with function name and line number)
        self.debug_format = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"

        self.info_formatter = logging.Formatter(self.info_format)
        self.debug_formatter = logging.Formatter(self.debug_format)

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno == logging.DEBUG:
            return self.debug_formatter.format(record)
        else:
            return self.info_formatter.format(record)


# Configure single logger with level-based formatting
logger = logging.getLogger("api")
logger.setLevel(logging.DEBUG)

# Remove any existing handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Add custom handler with level-based formatter
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(LevelBasedFormatter())
logger.addHandler(handler)
logger.propagate = False

# Shared AWS configuration - fail fast if not set
try:
    AWS_REGION: str = os.environ["AWS_DEFAULT_REGION"]
    SQS_URL: str = os.environ["SQS_QUEUE_URL"]
    TOKEN_SSM_PARAM: str = os.environ.get("TOKEN_SSM_PARAM", "/api/token")
    logger.info(
        f"Environment configured: region={AWS_REGION}, ssm_param={TOKEN_SSM_PARAM}"
    )
    logger.debug(f"AWS Region: {AWS_REGION}")
    logger.debug(f"SQS URL: {SQS_URL}")
    logger.debug(f"Token SSM Param: {TOKEN_SSM_PARAM}")
except KeyError as e:
    logger.error(f"Missing required environment variable: {e}")
    raise SystemExit(1) from e
