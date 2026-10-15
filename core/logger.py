"""Observability and logging setup for Marketing OS using Logfire."""

import logging
import sys
from typing import Optional
import logfire

from core.config import settings

# Configure standard Python logger
logger = logging.getLogger("marketing-os")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def setup_logger() -> logfire:
    """Configure Logfire with service name 'marketing-os', or fallback gracefully if token is absent."""
    token: Optional[str] = settings.LOGFIRE_TOKEN
    if token and token.strip():
        try:
            logfire.configure(
                service_name="marketing-os",
                token=token.strip(),
            )
            logger.info("Logfire initialized with service 'marketing-os'.")
        except Exception as exc:
            logger.warning(
                f"Failed to configure Logfire with provided token: {exc}. Falling back to local logging."
            )
            logfire.configure(
                service_name="marketing-os",
                send_to_logfire=False,
            )
    else:
        logger.info(
            "LOGFIRE_TOKEN absent or empty. Gracefully falling back to standard Python logging & local traces."
        )
        logfire.configure(
            service_name="marketing-os",
            send_to_logfire=False,
        )

    return logfire


# Initialize logging on module load
setup_logger()

__all__ = ["logger", "logfire", "setup_logger"]
