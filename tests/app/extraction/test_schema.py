import pytest
from pydantic import ValidationError

from app.extraction.schema import CitationContext, DocumentExtraction
from tests.app.extraction.fakes import extraction_json


def test_refs_cover_every_value():
    [mention] = DocumentExtraction.model_validate_json(extraction_json(2, 3)).borrowers

    assert [(r.line_start, r.line_end) for r in mention.refs()] == [(2, 3), (2, 3)]


def test_citation_within_document_is_valid():
    DocumentExtraction.model_validate_json(extraction_json(1, 5), context=CitationContext(last_line_no=5))


@pytest.mark.parametrize(("start", "end"), [(0, 1), (4, 6), (3, 2)])
def test_citation_outside_document_or_reversed_is_invalid(start, end):
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate_json(extraction_json(start, end), context=CitationContext(last_line_no=5))


def test_no_context_skips_the_citation_check():
    DocumentExtraction.model_validate_json(extraction_json(100, 200))
