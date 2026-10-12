from app import db
from app.db import DocumentStatus
from app.ingest import ingest_folder
from app.redrive import redrive
from tests.conftest import statuses


def _dead_letter_all(conn, queue):
    """Move every queued message to the DLQ, as after 3 failed attempts."""
    for path in queue.main.glob("*.json"):
        path.rename(queue.dlq / path.name)
    for doc in db.list_documents(conn):
        db.set_status(conn, doc.id, DocumentStatus.FAILED)


def test_redrive_by_batch(folder, conn, queue, s3):
    batch_id = ingest_folder(str(folder), conn, s3)
    _dead_letter_all(conn, queue)

    assert redrive(conn, queue, batch_id="other-batch") == 0
    assert redrive(conn, queue, batch_id=batch_id) == 2
    assert statuses(conn) == [DocumentStatus.QUEUED] * 2
    assert len(list(queue.main.glob("*.json"))) == 2


def test_redrive_all(folder, conn, queue, s3):
    ingest_folder(str(folder), conn, s3)
    _dead_letter_all(conn, queue)

    assert redrive(conn, queue) == 2
    assert list(queue.dlq.glob("*.json")) == []
