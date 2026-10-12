import pymupdf

from app.parsing.types import MimeType, Parser, RawPage

DEFAULT_RENDER_DPI = 150
PDF_FILETYPE = "pdf"
PNG_FORMAT = "png"


class PdfParser(Parser):
    """One page per PDF page: the text layer (None if empty) and the page rendered to PNG."""

    mime_types = (MimeType.PDF,)

    def __init__(self, render_dpi: int = DEFAULT_RENDER_DPI):
        self.render_dpi = render_dpi

    def parse(self, data: bytes) -> list[RawPage]:
        with pymupdf.open(stream=data, filetype=PDF_FILETYPE) as pdf:
            return [
                RawPage(
                    page_no=page_no,
                    text=page.get_text().strip() or None,
                    image=page.get_pixmap(dpi=self.render_dpi).tobytes(PNG_FORMAT),
                )
                for page_no, page in enumerate(pdf, start=1)
            ]


class ImageParser(Parser):
    """One page with no text, the image converted to PNG."""

    mime_types = (MimeType.PNG, MimeType.JPEG)

    def parse(self, data: bytes) -> list[RawPage]:
        return [RawPage(page_no=1, text=None, image=pymupdf.Pixmap(data).tobytes(PNG_FORMAT))]
