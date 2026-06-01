import json
import os
import sys
from datetime import datetime, timezone

from loguru import logger

from config.settings import LOG_DIR, LOG_LEVEL

# 是否启用 JSON 结构化日志（适合日志聚合工具：ELK/Loki/Datadog）
LOG_JSON_ENABLED = os.getenv("LOG_JSON_ENABLED", "0").strip() == "1"

# JSON 日志文件独立路径（可选，不设置则和普通日志一起写）
LOG_JSON_FILE = os.getenv("LOG_JSON_FILE", "").strip()


def _json_serializer(message) -> str:
    """将 loguru record 序列化为单行 JSON。"""
    record = message.record
    log_entry = {
        "ts": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": record["level"].name,
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    if record["exception"] is not None:
        log_entry["exception"] = str(record["exception"])
    extra = record.get("extra")
    if extra:
        log_entry["extra"] = {k: str(v) for k, v in extra.items()}
    return json.dumps(log_entry, ensure_ascii=False, separators=(",", ":")) + "\n"


def setup_logger(log_name: str = "crypto_data"):
    """配置控制台与文件日志输出。

    环境变量控制：
      LOG_LEVEL          — 日志级别（默认 INFO）
      LOG_JSON_ENABLED=1 — 启用 JSON 结构化输出（控制台 + 文件）
      LOG_JSON_FILE      — JSON 日志独立文件路径（可选）
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    safe_log_name = (
        (log_name or "crypto_data")
        .replace(os.sep, "_")
        .replace(" ", "_")
    )

    logger.remove()

    if LOG_JSON_ENABLED:
        # JSON 结构化控制台输出
        logger.add(
            sys.stderr,
            level=LOG_LEVEL,
            format=_json_serializer,
            colorize=False,
        )
        # JSON 结构化文件输出
        json_path = LOG_JSON_FILE or f"{LOG_DIR}/{safe_log_name}_{{time:YYYY-MM-DD}}.jsonl"
        logger.add(
            json_path,
            level=LOG_LEVEL,
            format=_json_serializer,
            rotation="00:00",
            retention="30 days",
            encoding="utf-8",
        )
    else:
        # 传统人类可读格式
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
