from app import db
from app.ingest import ingest_folder
from app.local_s3 import page_key
from app.parsing.registry import REGISTRY
from app.parsing.step import parse_document


def test_writes_page_images_and_returns_pages(folder, conn, s3):
    ingest_folder(str(folder), conn, s3)
    _, b = db.list_documents(conn)

    pages = parse_document(b, s3, REGISTRY)

    assert [p.image_key for p in pages] == [page_key(b.id, 1), page_key(b.id, 2)]
    assert all(s3.get(p.image_key) for p in pages)
