import shutil

import pymupdf
import pytest

from app.parsing.detect import detect_mime
from app.parsing.ocr import TesseractOcr
from app.parsing.parsers import ImageParser, PdfParser
from app.parsing.registry import REGISTRY
from app.parsing.types import MimeType
from tests.conftest import OCR_TEXT, FakeOcr, make_pdf


def _image(fmt: str) -> bytes:
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False).tobytes(fmt)


def test_pdf_native_lines_with_boxes():
    [page] = PdfParser(FakeOcr()).parse(make_pdf("Account Number: 123456789"))

    assert page.ocr is False
    [line] = page.lines
    assert (line.line_no, line.text) == (1, "Account Number: 123456789")
    box = line.bbox
    assert 0 <= box.left < box.left + box.width <= 1 and 0 <= box.top < box.top + box.height <= 1


def test_pdf_page_without_text_goes_to_ocr():
    pages = PdfParser(FakeOcr()).parse(make_pdf("first", ""))

    assert [(p.page_no, p.ocr) for p in pages] == [(1, False), (2, True)]
    assert pages[1].lines[0].text == OCR_TEXT


def test_line_numbers_continue_across_pages():
    pages = PdfParser(FakeOcr()).parse(make_pdf("one", "two", ""))

    assert [ln.line_no for p in pages for ln in p.lines] == [1, 2, 3]


def test_pdf_pages_rendered_to_png():
    pages = PdfParser(FakeOcr()).parse(make_pdf("one", ""))

    assert all(detect_mime(p.image) == MimeType.PNG for p in pages)


@pytest.mark.parametrize("fmt", ["png", "jpg"])
def test_image_is_one_ocr_page_as_png(fmt):
    [page] = ImageParser(FakeOcr()).parse(_image(fmt))

    assert (page.page_no, page.ocr, page.lines[0].text) == (1, True, OCR_TEXT)
    assert detect_mime(page.image) == MimeType.PNG


def test_broken_pdf_raises():
    with pytest.raises(pymupdf.FileDataError):
        PdfParser(FakeOcr()).parse(b"%PDF-1.7\nnot really a pdf")


def test_registry_has_both_parsers():
    assert isinstance(REGISTRY.get(MimeType.PDF), PdfParser)
    assert isinstance(REGISTRY.get(MimeType.PNG), ImageParser)
    assert isinstance(REGISTRY.get(MimeType.JPEG), ImageParser)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")
def test_tesseract_reads_rendered_text():
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Account Number 123456789", fontsize=20)
        image = pdf[0].get_pixmap(dpi=300).tobytes("png")

    [line] = TesseractOcr().read(image)

    assert "123456789" in line.text
    assert 0 < line.bbox.left < 0.5 and 0 < line.bbox.top < 0.2
