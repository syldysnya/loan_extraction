import logging
from dataclasses import dataclass, fields
from enum import StrEnum

from pydantic import BaseModel

from app.db import DocumentStatus

# LogRecord attribute that carries the LogContext.
CONTEXT_ATTR = "context"
PLAIN_TIME_FORMAT = "%H:%M:%S"


class Stage(StrEnum):
    INGEST = "ingest"
    WORKER = "worker"
    REDRIVE = "redrive"
    RESOLVE = "resolve"


@dataclass
class LogContext:
    """Fields attached to a log line. IDs only, never PII."""

    stage: Stage
    batch_id: str | None = None
    document_id: str | None = None
    status: DocumentStatus | None = None

    def extra(self) -> dict[str, "LogContext"]:
        """The `extra=` mapping the logging API expects."""
        return {CONTEXT_ATTR: self}

    def __str__(self) -> str:
        values = ((f.name, getattr(self, f.name)) for f in fields(self))
        return " ".join(f"{name}={value}" for name, value in values if value is not None)


class LogLine(BaseModel):
    """One log line, built from a LogRecord."""

    time: str
    level: str
    logger: str
    message: str
    stage: Stage | None = None
    batch_id: str | None = None
    document_id: str | None = None
    status: DocumentStatus | None = None
    exception: str | None = None

    @classmethod
    def from_record(cls, record: logging.LogRecord, fmt: logging.Formatter, datefmt: str | None = None) -> "LogLine":
        ctx: LogContext | None = getattr(record, CONTEXT_ATTR, None)
        return cls(
            time=fmt.formatTime(record, datefmt),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
            stage=ctx.stage if ctx else None,
            batch_id=ctx.batch_id if ctx else None,
            document_id=ctx.document_id if ctx else None,
            status=ctx.status if ctx else None,
            exception=fmt.formatException(record.exc_info) if record.exc_info else None,
        )


class PlainFormatter(logging.Formatter):
    """One readable line for stdout."""

    def format(self, record: logging.LogRecord) -> str:
        line = LogLine.from_record(record, self, PLAIN_TIME_FORMAT)
        ctx: LogContext | None = getattr(record, CONTEXT_ATTR, None)
        text = f"{line.time} {line.level} {line.logger}: {line.message} {ctx or ''}".rstrip()
        return f"{text}\n{line.exception}" if line.exception else text


class JsonFormatter(logging.Formatter):
    """One JSON object per line for the log file."""

    def format(self, record: logging.LogRecord) -> str:
        return LogLine.from_record(record, self).model_dump_json(exclude_none=True)
