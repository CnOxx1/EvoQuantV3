import os
import sys

from loguru import logger

from config.settings import LOG_DIR, LOG_LEVEL


def setup_logger(log_name: str = "crypto_data"):
    """配置控制台与文件日志输出。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    safe_log_name = (
        (log_name or "crypto_data")
        .replace(os.sep, "_")
        .replace(" ", "_")
    )

    logger.remove()
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )
    logger.add(
        f"{LOG_DIR}/{safe_log_name}_{{time:YYYY-MM-DD}}.log",
        level=LOG_LEVEL,
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
    )
