from app.db import DocumentStatus
from app.ingest import ingest_folder
from app.local_s3 import input_key
from tests.conftest import statuses


def test_registers_writes_and_queues(folder, conn, queue, s3):
    batch_id = ingest_folder(str(folder), conn, s3)

    assert statuses(conn) == [DocumentStatus.QUEUED] * 2
    assert (s3.root / input_key(batch_id, "a.pdf")).exists()
    assert len(list(queue.main.glob("*.json"))) == 2


def test_skips_duplicates(folder, conn, queue, s3):
    ingest_folder(str(folder), conn, s3)
    ingest_folder(str(folder), conn, s3)

    assert len(statuses(conn)) == 2
    assert len(list(queue.main.glob("*.json"))) == 2
