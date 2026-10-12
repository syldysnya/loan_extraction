from collections import defaultdict

import pymupdf

from app.parsing.ocr import Ocr
from app.parsing.types import BBox, LineNumbering, MimeType, Parser, RawPage, TextLine

DEFAULT_RENDER_DPI = 150
DEFAULT_OCR_DPI = 300  # Tesseract reads best at 300 DPI
PDF_FILETYPE = "pdf"
PNG_FORMAT = "png"
WORDS_MODE = "words"  # get_text mode: (x0, y0, x1, y1, word, block_no, line_no, word_no) per word


class PdfParser(Parser):
    """One page per PDF page: native text lines (or OCR lines if the page has none) and the page as PNG."""

    mime_types = (MimeType.PDF,)

    def __init__(self, ocr: Ocr, render_dpi: int = DEFAULT_RENDER_DPI, ocr_dpi: int = DEFAULT_OCR_DPI):
        self.ocr = ocr
        self.render_dpi = render_dpi
        self.ocr_dpi = ocr_dpi

    def parse(self, data: bytes) -> list[RawPage]:
        numbering = LineNumbering()
        pages = []
        with pymupdf.open(stream=data, filetype=PDF_FILETYPE) as pdf:
            for page_no, page in enumerate(pdf, start=1):
                text_lines = _native_lines(page)
                ocr = not text_lines
                if ocr:
                    text_lines = self.ocr.read(page.get_pixmap(dpi=self.ocr_dpi).tobytes(PNG_FORMAT))
                pages.append(
                    RawPage(
                        page_no=page_no,
                        lines=numbering.number(text_lines),
                        ocr=ocr,
                        image=page.get_pixmap(dpi=self.render_dpi).tobytes(PNG_FORMAT),
                    )
                )
        return pages


class ImageParser(Parser):
    """One page: OCR lines and the image converted to PNG."""

    mime_types = (MimeType.PNG, MimeType.JPEG)

    def __init__(self, ocr: Ocr):
        self.ocr = ocr

    def parse(self, data: bytes) -> list[RawPage]:
        image = pymupdf.Pixmap(data).tobytes(PNG_FORMAT)
        lines = LineNumbering().number(self.ocr.read(image))
        return [RawPage(page_no=1, lines=lines, ocr=True, image=image)]


def _native_lines(page: pymupdf.Page) -> list[TextLine]:
    """The page's text-layer lines, with boxes normalized to the page size."""
    width, height = page.rect.width, page.rect.height
    words_by_line: dict[tuple[int, int], list[tuple[str, BBox]]] = defaultdict(list)
    for x0, y0, x1, y1, word, block_no, line_no, _ in page.get_text(WORDS_MODE):
        box = BBox(left=x0 / width, top=y0 / height, width=(x1 - x0) / width, height=(y1 - y0) / height)
        words_by_line[(block_no, line_no)].append((word, box))
    return [
        TextLine(text=" ".join(w for w, _ in words), bbox=BBox.union([b for _, b in words]))
        for words in words_by_line.values()
    ]
