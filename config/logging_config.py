import sys

from loguru import logger


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    logger.remove()

    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

    logger.add(
        f"{log_dir}/quantos_{{time:YYYY-MM-DD}}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
    )
