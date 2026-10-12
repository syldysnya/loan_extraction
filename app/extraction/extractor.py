import logging

from app.db import Document
from app.errors import NonRetryableError, safe_error
from app.extraction.evidence import LineIndex
from app.extraction.guards import remove_ssn_like_accounts
from app.extraction.request import build_request
from app.extraction.schema import CitationContext, DocumentExtraction
from app.extraction.tracking import CallContext, TrackedModel
from app.local_s3 import LocalS3
from app.log import LogContext, Stage
from app.parsing.types import Page

MAX_ATTEMPTS = 3


def logger() -> logging.Logger:
    return logging.getLogger(__name__)


class ExtractionFailed(NonRetryableError):
    pass


def extract(document: Document, pages: list[Page], s3: LocalS3, model: TrackedModel) -> DocumentExtraction:
    """One LLM call for the whole document, up to MAX_ATTEMPTS times.

    An attempt fails on an API error, invalid JSON, or a citation to a line that doesn't exist.
    """
    images = [s3.get(page.image_key) for page in pages]
    request = build_request(pages, images, include_images=model.client.supports_image_input)
    citations = CitationContext(last_line_no=LineIndex(pages).last_line_no)

    log_ctx = LogContext(Stage.WORKER, batch_id=document.batch_id, document_id=document.id)
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            ctx = CallContext(document_id=document.id, batch_id=document.batch_id, attempt=attempt)
            result = model.generate(request, DocumentExtraction, ctx, context=citations)
        except Exception as e:
            last_error = e
            logger().warning(f"extraction attempt {attempt} failed: {safe_error(e)}", extra=log_ctx.extra())
            continue
        removed = remove_ssn_like_accounts(result)
        if removed:
            logger().warning(f"dropped SSN-like account numbers: {', '.join(removed)}", extra=log_ctx.extra())
        return result

    assert last_error is not None
    raise ExtractionFailed(f"{MAX_ATTEMPTS} attempts failed, last: {safe_error(last_error)}") from last_error
