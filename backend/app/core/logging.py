"""Structured JSON logging with secret redaction and rotation (P-01 §11).

Redaction is defence-in-depth: a filter masks (a) values of configured
secrets, (b) substrings that look like ``key=value`` secrets, passwords,
bearer tokens and API keys in any log message.
"""
from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
]


def redact_text(text: str, secret_values: tuple[str, ...] = ()) -> str:
    out = text
    for value in secret_values:
        if value and len(value) >= 4:
            out = out.replace(value, "***REDACTED***")
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=***REDACTED***"
                           if ("=" in m.group(0) or ":" in m.group(0)) else "***REDACTED***", out)
    return out


class RedactionFilter(logging.Filter):
    def __init__(self, secret_values: tuple[str, ...] = ()):
        super().__init__()
        self.secret_values = secret_values

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact_text(message, self.secret_values)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None),
            "task_id": getattr(record, "task_id", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", log_file: Path | None = None,
                      max_bytes: int = 1_000_000, backup_count: int = 5,
                      secret_values: tuple[str, ...] = ()) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    formatter = JsonFormatter()
    redaction = RedactionFilter(secret_values)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(redaction)
    root.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redaction)
        root.addHandler(file_handler)

    # Keep uvicorn's own loggers inside the same pipeline.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


def get_logger(component: str) -> logging.Logger:
    return logging.LoggerAdapter(logging.getLogger(component), {"component": component})
