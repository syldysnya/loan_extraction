import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app import db
from app.db import DocumentStatus
from app.extraction.evidence import LineIndex
from app.log import LogContext, Stage
from app.resolution.merge import build_records, mention_borrower_ids
from app.resolution.record import DocumentMentions


def logger() -> logging.Logger:
    return logging.getLogger(__name__)


@dataclass
class ResolutionResult:
    borrowers: int
    conflicts: int


def resolve_all(conn: sqlite3.Connection) -> ResolutionResult:
    """Rebuild every borrower from the mentions of all `done` documents. Idempotent."""
    docs = [
        DocumentMentions(d, LineIndex(db.get_pages(conn, d.id) or []), db.list_mentions(conn, d.id))
        for d in db.list_documents(conn)
        if d.status == DocumentStatus.DONE  # a failed re-run may leave mentions from an earlier run
    ]
    records = build_records(docs)
    now = datetime.now(UTC).isoformat()
    rows = [db.BorrowerRow(r.id, r.name, r.model_dump_json(), len(r.conflicts), now) for r in records]
    db.replace_borrowers(conn, rows, mention_borrower_ids(docs))

    ctx = LogContext(Stage.RESOLVE).extra()
    for record in records:
        for conflict in record.conflicts:
            logger().warning(f"conflict: borrower {record.id}: {conflict.field}", extra=ctx)  # IDs only, no values
    result = ResolutionResult(borrowers=len(records), conflicts=sum(len(r.conflicts) for r in records))
    logger().info(f"resolved {result.borrowers} borrowers, {result.conflicts} conflicts", extra=ctx)
    return result
