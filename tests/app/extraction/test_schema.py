from datetime import date

import pytest
from pydantic import ValidationError

from app.extraction.schema import CitationContext, DocumentExtraction, IncomeBasis, IncomeEntry
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


def _income(start: str, end: str) -> dict:
    return {
        "amount": 4500.0,
        "kind": "wages",
        "basis": "period",
        "period_start": start,
        "period_end": end,
        "payer": "ABC Technologies",
        "joint": False,
        "source": {"line_start": 1, "line_end": 1},
    }


def test_income_period_dates_parse():
    entry = IncomeEntry.model_validate(_income("2025-04-12", "2025-04-25"))

    assert (entry.period_start, entry.period_end) == (date(2025, 4, 12), date(2025, 4, 25))
    assert entry.basis == IncomeBasis.PERIOD


def test_income_period_end_before_start_is_invalid():
    with pytest.raises(ValidationError):
        IncomeEntry.model_validate(_income("2025-04-25", "2025-04-12"))
