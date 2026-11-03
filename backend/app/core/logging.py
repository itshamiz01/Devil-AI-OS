from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings

_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._\-]+")
_REDACT = re.compile(
    r"(?i)(password|api_key|apikey|token|secret|authorization)(\"?\s*[:=]\s*\"?)([^\s\",}]+)"
)


def redact(text: str) -> str:
    text = _BEARER.sub("Bearer [REDACTED]", text)

    def repl(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(2)}[REDACTED]"

    return _REDACT.sub(repl, text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key in ("correlation_id", "task_id", "component"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    formatter = JsonFormatter()
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        Path(settings.log_dir) / "autonomus.log",
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(stream)
    root.addHandler(file_handler)
