from app import db
from app.db import DocumentStatus
from app.document_worker import DocumentWorker
from app.extraction.schema import DocumentType
from app.extraction.tracking import TrackedModel
from app.ingest import ingest_folder
from app.messages import DocumentMessage
from tests.app.extraction.fakes import FixedClient, extraction_json
from tests.conftest import OCR_TEXT, statuses


def test_success_parses_marks_done_and_deletes_message(folder, conn, queue, s3, worker):
    ingest_folder(str(folder), conn, s3)

    while worker.run_once():
        pass

    assert statuses(conn) == [DocumentStatus.DONE] * 2
    assert list(queue.main.glob("*.json")) == []
    _, b = db.list_documents(conn)
    pages = db.get_pages(conn, b.id)
    assert [(p.page_no, p.ocr, [ln.text for ln in p.lines]) for p in pages] == [
        (1, False, ["Account Number: 222"]),
        (2, True, [OCR_TEXT]),
    ]
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
    assert (doc.status, doc.error) == (DocumentStatus.FAILED, "RuntimeError")  # type only: messages may hold PII


def test_malformed_message_is_deleted_not_retried(queue, worker):
    queue.send('{"wrong": "shape"}')
    queue.send(DocumentMessage(document_id="unknown").model_dump_json())

    assert worker.run_once()
    assert worker.run_once()
    assert list(queue.main.glob("*.json")) == []
    assert list(queue.dlq.glob("*.json")) == []


def test_success_stores_one_mention_per_borrower(folder, conn, s3, worker):
    ingest_folder(str(folder), conn, s3)

    while worker.run_once():
        pass

    mentions = db.list_mentions(conn)
    assert len(mentions) == 2  # one per document
    assert {m.mention.name for m in mentions} == {"John Homeowner"}
    [borrower] = db.list_borrowers(conn)  # the batch finished, so resolution ran
    assert {m.borrower_id for m in mentions} == {borrower.id}
    assert {d.document_type for d in db.list_documents(conn)} == {DocumentType.BANK_STATEMENT}


def test_extraction_failure_fails_at_once_without_values_in_error(folder, conn, queue, s3, registry):
    (folder / "b.pdf").unlink()
    ingest_folder(str(folder), conn, s3)
    bad_citation = TrackedModel(FixedClient(extraction_json(99, 99)), conn)
    worker = DocumentWorker(conn, queue, s3, registry, bad_citation)

    assert worker.run_once()

    [doc] = db.list_documents(conn)
    assert doc.status == DocumentStatus.FAILED
    assert doc.error.startswith("ExtractionFailed")
    assert "John Homeowner" not in doc.error
    assert list(queue.main.glob("*.json")) == list(queue.dlq.glob("*.json")) == []


def test_rerun_replaces_mentions_instead_of_duplicating(folder, conn, s3, worker):
    (folder / "b.pdf").unlink()
    ingest_folder(str(folder), conn, s3)
    [doc] = db.list_documents(conn)

    worker.process_document(doc)
    worker.process_document(doc)

    assert len(db.list_mentions(conn, doc.id)) == 1


def test_resolution_waits_until_the_batch_is_finished(folder, conn, s3, worker):
    ingest_folder(str(folder), conn, s3)

    assert worker.run_once()  # 1 of 2 documents done
    assert db.list_borrowers(conn) == []
    assert worker.run_once()  # batch finished
    assert len(db.list_borrowers(conn)) == 1
