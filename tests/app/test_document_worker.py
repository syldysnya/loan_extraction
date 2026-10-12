from app import db, document_worker
from app.db import DocumentStatus
from app.ingest import ingest_folder
from app.messages import DocumentMessage
from tests.conftest import statuses


def test_success_marks_done_and_deletes_message(folder, conn, queue, s3):
    ingest_folder(str(folder), conn, s3)

    while document_worker.run_once(conn, queue):
        pass

    assert statuses(conn) == [DocumentStatus.DONE] * 2
    assert list(queue.main.glob("*.json")) == []


def test_retries_then_dlq(folder, conn, queue, s3, monkeypatch):
    (folder / "b.pdf").unlink()
    ingest_folder(str(folder), conn, s3)

    def boom(conn, document_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(document_worker, "process_document", boom)
    for _ in range(3):  # 3 failed attempts
        assert document_worker.run_once(conn, queue)
        assert statuses(conn) == [DocumentStatus.QUEUED]
    assert not document_worker.run_once(conn, queue)  # 4th receive moves it to the DLQ

    [doc] = db.list_documents(conn)
    assert (doc.status, doc.error) == (DocumentStatus.FAILED, "boom")
    assert len(list(queue.dlq.glob("*.json"))) == 1


def test_malformed_message_is_deleted_not_retried(conn, queue):
    queue.send('{"wrong": "shape"}')
    queue.send(DocumentMessage(document_id="unknown").model_dump_json())

    assert document_worker.run_once(conn, queue)
    assert document_worker.run_once(conn, queue)
    assert list(queue.main.glob("*.json")) == []
    assert list(queue.dlq.glob("*.json")) == []
