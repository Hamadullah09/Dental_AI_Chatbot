from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from app.core.config import get_settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        record.user_id = user_id_var.get("")
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json as json_mod

        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
            "user_id": getattr(record, "user_id", ""),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data
        return json_mod.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        rid = getattr(record, "request_id", "")
        uid = getattr(record, "user_id", "")
        prefix = f"{color}[{record.levelname}]{self.RESET}"
        rid_str = f" [{rid[:8]}]" if rid else ""
        uid_str = f" user={uid}" if uid else ""
        msg = f"{prefix} {record.name}{rid_str}{uid_str}: {record.getMessage()}"
        if record.exc_info and record.exc_info[0]:
            msg += f"\n{self.formatException(record.exc_info)}"
        return msg


def setup_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(HumanFormatter())

    handler.addFilter(RequestContextFilter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class Timer:
    def __init__(self, logger: logging.Logger, operation: str, extra: dict[str, Any] | None = None) -> None:
        self.logger = logger
        self.operation = operation
        self.extra = extra or {}
        self.start: float = 0
        self.duration_ms: float = 0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.duration_ms = round((time.perf_counter() - self.start) * 1000, 2)
        self.logger.info(
            f"{self.operation} completed in {self.duration_ms}ms",
            extra={"extra_data": {**self.extra, "duration_ms": self.duration_ms, "operation": self.operation}},
        )
