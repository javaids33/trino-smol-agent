import logging
import sys
from src.config import settings

# Basic logging setup - consider using structlog for richer structured logs
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def get_logger(name: str):
    """Gets a logger instance."""
    return logging.getLogger(name)

logger = get_logger(__name__)
logger.info(f"Logger initialized with level: {settings.LOG_LEVEL}") 