import pymupdf
import pytest

from app import db
from app.document_worker import DocumentWorker
from app.extraction.tracking import TrackedModel
from app.local_s3 import LocalS3
from app.local_sqs import LocalSQS
from app.parsing.ocr import Ocr
from app.parsing.parsers import ImageParser, PdfParser
from app.parsing.registry import ParserRegistry
from app.parsing.types import BBox, TextLine
from tests.app.extraction.fakes import FixedClient, extraction_json

OCR_TEXT = "text read by OCR"


class FakeOcr(Ocr):
    """Returns one fixed line, so tests don't need the Tesseract binary."""

    def read(self, image: bytes) -> list[TextLine]:
        return [TextLine(text=OCR_TEXT, bbox=BBox(left=0.1, top=0.1, width=0.5, height=0.05))]


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
def registry() -> ParserRegistry:
    ocr = FakeOcr()
    return ParserRegistry([PdfParser(ocr), ImageParser(ocr)])


@pytest.fixture
def model(conn) -> TrackedModel:
    """A fake LLM that always extracts one borrower, citing line 1."""
    return TrackedModel(FixedClient(extraction_json(1, 1)), conn)


@pytest.fixture
def worker(conn, queue, s3, registry, model):
    return DocumentWorker(conn, queue, s3, registry, model)


def statuses(conn) -> list[db.DocumentStatus]:
    return [d.status for d in db.list_documents(conn)]
