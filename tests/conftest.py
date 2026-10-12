import pymupdf
import pytest

from app import db
from app.document_worker import DocumentWorker
from app.local_s3 import LocalS3
from app.local_sqs import LocalSQS
from app.parsing.registry import REGISTRY


def make_pdf(*page_texts: str) -> bytes:
    """A PDF with one page per text; an empty string gives a page with no text layer."""
    with pymupdf.open() as pdf:
        for text in page_texts:
            page = pdf.new_page()
            if text:
                page.insert_text((72, 72), text)
        return pdf.tobytes()


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(make_pdf("Account Number: 111"))
    (folder / "b.pdf").write_bytes(make_pdf("Account Number: 222", ""))
    return folder


@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "test.db"))


@pytest.fixture
def queue(tmp_path):
    # Visibility timeout 0 so retries are immediate.
    return LocalSQS(str(tmp_path / "queue"), visibility_timeout_s=0, max_receive_count=3)


@pytest.fixture
def s3(tmp_path, queue):
    return LocalS3(str(tmp_path / "s3"), queue)


@pytest.fixture
def worker(conn, queue, s3):
    return DocumentWorker(conn, queue, s3, REGISTRY)


def statuses(conn) -> list[db.DocumentStatus]:
    return [d.status for d in db.list_documents(conn)]
