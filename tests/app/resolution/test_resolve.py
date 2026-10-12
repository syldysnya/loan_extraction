from app import db
from app.db import DocumentStatus
from app.ingest import ingest_folder
from app.resolution.record import BorrowerRecord
from app.resolution.resolve import resolve_all


def _process_all(folder, conn, s3, worker) -> None:
    ingest_folder(str(folder), conn, s3)
    while worker.run_once():
        pass


def test_rebuild_is_idempotent(folder, conn, s3, worker):
    _process_all(folder, conn, s3, worker)
    before = [(b.id, b.name, b.conflict_count) for b in db.list_borrowers(conn)]

    resolve_all(conn)
    resolve_all(conn)

    assert [(b.id, b.name, b.conflict_count) for b in db.list_borrowers(conn)] == before


def test_record_has_values_from_every_done_document(folder, conn, s3, worker):
    _process_all(folder, conn, s3, worker)

    [row] = db.list_borrowers(conn)
    record = BorrowerRecord.model_validate_json(row.record)

    assert record.name == "John Homeowner"
    assert {s.document_id for s in record.name_sources} == {d.id for d in db.list_documents(conn)}
    assert db.get_borrower(conn, record.id) == row


def test_failed_documents_mentions_are_ignored(folder, conn, s3, worker):
    _process_all(folder, conn, s3, worker)
    a, b = db.list_documents(conn)
    db.set_status(conn, b.id, DocumentStatus.FAILED)

    resolve_all(conn)

    [row] = db.list_borrowers(conn)
    record = BorrowerRecord.model_validate_json(row.record)
    assert {s.document_id for s in record.name_sources} == {a.id}
    linked = {m.document_id for m in db.list_mentions(conn) if m.borrower_id}
    assert linked == {a.id}
