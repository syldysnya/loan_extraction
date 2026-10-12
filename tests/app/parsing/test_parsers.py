import pymupdf
import pytest

from app.parsing.detect import detect_mime
from app.parsing.parsers import ImageParser, PdfParser
from app.parsing.registry import REGISTRY
from app.parsing.types import MimeType


@pytest.fixture
def pdf_bytes() -> bytes:
    """Two pages: one with text, one blank (like a scanned page with no text layer)."""
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Account Number: 123456789")
        pdf.new_page()
        return pdf.tobytes()


def _image(fmt: str) -> bytes:
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False).tobytes(fmt)


def test_pdf_page_per_page_with_text_or_none(pdf_bytes):
    pages = PdfParser().parse(pdf_bytes)

    assert [p.page_no for p in pages] == [1, 2]
    assert pages[0].text == "Account Number: 123456789"
    assert pages[1].text is None


def test_pdf_pages_rendered_to_png(pdf_bytes):
    pages = PdfParser().parse(pdf_bytes)

    assert all(detect_mime(p.image) == MimeType.PNG for p in pages)


@pytest.mark.parametrize("fmt", ["png", "jpg"])
def test_image_is_one_page_without_text_as_png(fmt):
    [page] = ImageParser().parse(_image(fmt))

    assert (page.page_no, page.text) == (1, None)
    assert detect_mime(page.image) == MimeType.PNG


def test_broken_pdf_raises():
    with pytest.raises(pymupdf.FileDataError):
        PdfParser().parse(b"%PDF-1.7\nnot really a pdf")


def test_registry_has_both_parsers():
    assert isinstance(REGISTRY.get(MimeType.PDF), PdfParser)
    assert isinstance(REGISTRY.get(MimeType.PNG), ImageParser)
    assert isinstance(REGISTRY.get(MimeType.JPEG), ImageParser)
