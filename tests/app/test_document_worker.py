from app import db
from app.db import DocumentStatus
from app.document_worker import DocumentWorker
from app.ingest import ingest_folder
from app.messages import DocumentMessage
from tests.conftest import statuses


def test_success_parses_marks_done_and_deletes_message(folder, conn, queue, s3, worker):
    ingest_folder(str(folder), conn, s3)

    while worker.run_once():
        pass

    assert statuses(conn) == [DocumentStatus.DONE] * 2
    assert list(queue.main.glob("*.json")) == []
    _, b = db.list_documents(conn)
    pages = db.get_pages(conn, b.id)
    assert [(p.page_no, p.text) for p in pages] == [(1, "Account Number: 222"), (2, None)]
    assert all((s3.root / p.image_key).exists() for p in pages)


def test_unsupported_type_fails_at_once(folder, conn, queue, s3, worker):
    for path in folder.iterdir():
        path.unlink()
    (folder / "note.txt").write_text("plain text")
    ingest_folder(str(folder), conn, s3)

    assert worker.run_once()

    [doc] = db.list_documents(conn)
    assert doc.status == DocumentStatus.FAILED
    assert "unknown file type" in doc.error
    assert list(queue.main.glob("*.json")) == []
    assert list(queue.dlq.glob("*.json")) == []


def test_broken_file_retries_then_dlq(folder, conn, queue, s3, worker):
    for path in folder.iterdir():
        path.unlink()
    (folder / "broken.pdf").write_bytes(b"%PDF-1.7\nnot really a pdf")
    ingest_folder(str(folder), conn, s3)

    for _ in range(3):  # 3 failed attempts
        assert worker.run_once()
        assert statuses(conn) == [DocumentStatus.QUEUED]
    assert not worker.run_once()  # 4th receive moves it to the DLQ

    [doc] = db.list_documents(conn)
    assert doc.status == DocumentStatus.FAILED
    assert len(list(queue.dlq.glob("*.json"))) == 1


def test_retries_keep_last_error(folder, conn, queue, s3, worker, monkeypatch):
    (folder / "b.pdf").unlink()
    ingest_folder(str(folder), conn, s3)

    def boom(self, document):
        raise RuntimeError("boom")

    monkeypatch.setattr(DocumentWorker, "process_document", boom)
    for _ in range(4):
        worker.run_once()

    [doc] = db.list_documents(conn)
    assert (doc.status, doc.error) == (DocumentStatus.FAILED, "boom")


def test_malformed_message_is_deleted_not_retried(queue, worker):
    queue.send('{"wrong": "shape"}')
    queue.send(DocumentMessage(document_id="unknown").model_dump_json())

    assert worker.run_once()
    assert worker.run_once()
    assert list(queue.main.glob("*.json")) == []
    assert list(queue.dlq.glob("*.json")) == []
