from app.db import Document
from app.local_s3 import LocalS3, input_key, page_key
from app.parsing.detect import detect_mime
from app.parsing.registry import ParserRegistry
from app.parsing.types import Page


def parse_document(document: Document, s3: LocalS3, registry: ParserRegistry) -> list[Page]:
    """Read the document from S3, parse it, and write each page image back to S3."""
    data = s3.get(input_key(document.batch_id, document.filename))
    raw_pages = registry.get(detect_mime(data)).parse(data)

    pages = []
    for raw in raw_pages:
        key = page_key(document.id, raw.page_no)
        s3.put(key, raw.image)
        pages.append(Page(page_no=raw.page_no, lines=raw.lines, ocr=raw.ocr, image_key=key))
    return pages
