import json
import logging

from app.db import DocumentStatus
from app.log import JsonFormatter, LogContext, PlainFormatter, Stage


def _record(ctx: LogContext | None) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "done", None, None)
    if ctx:
        record.__dict__.update(ctx.extra())
    return record


CTX = LogContext(Stage.WORKER, batch_id="b1", document_id="d1", status=DocumentStatus.DONE)


def test_plain_line_has_message_and_context():
    line = PlainFormatter().format(_record(CTX))

    assert line.endswith("test: done stage=worker batch_id=b1 document_id=d1 status=done")


def test_json_line_has_context_fields_and_no_empty_ones():
    entry = json.loads(JsonFormatter().format(_record(LogContext(Stage.INGEST, batch_id="b1"))))

    assert (entry["message"], entry["stage"], entry["batch_id"]) == ("done", "ingest", "b1")
    assert "document_id" not in entry and "status" not in entry


def test_line_without_context():
    entry = json.loads(JsonFormatter().format(_record(None)))

    assert "stage" not in entry
