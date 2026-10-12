import pytest

from app import db
from app.errors import NonRetryableError
from app.extraction.extractor import MAX_ATTEMPTS, ExtractionFailed, extract
from app.extraction.tracking import TrackedModel
from app.ingest import ingest_folder
from app.parsing.step import parse_document
from tests.app.extraction.fakes import FlakyClient, ScriptedClient, extraction_json

NAME = "John Homeowner"


@pytest.fixture
def parsed(folder, conn, s3, registry):
    """`a.pdf` from the shared fixture: one page, one line."""
    ingest_folder(str(folder), conn, s3)
    a, _ = db.list_documents(conn)
    return a, parse_document(a, s3, registry)


def _attempts(conn) -> list[tuple[int, str | None]]:
    return conn.execute("SELECT attempt, error_type FROM llm_calls ORDER BY attempt").fetchall()


def test_valid_answer_on_first_attempt(parsed, conn, s3):
    document, pages = parsed
    client = ScriptedClient(extraction_json(1, 1))

    result = extract(document, pages, s3, TrackedModel(client, conn))

    assert result.borrowers[0].name == NAME
    assert _attempts(conn) == [(1, None)]


def test_invalid_json_then_bad_citation_then_success(parsed, conn, s3):
    document, pages = parsed
    client = ScriptedClient("not json", extraction_json(99, 99), extraction_json(1, 1))

    extract(document, pages, s3, TrackedModel(client, conn))

    assert _attempts(conn) == [(1, "ValidationError"), (2, "ValidationError"), (3, None)]


def test_three_failures_raise_without_document_values(parsed, conn, s3):
    document, pages = parsed
    client = ScriptedClient(*[extraction_json(99, 99, name=NAME)] * MAX_ATTEMPTS)

    with pytest.raises(ExtractionFailed) as e:
        extract(document, pages, s3, TrackedModel(client, conn))

    assert isinstance(e.value, NonRetryableError)
    assert "borrowers.0.name_source" in str(e.value)
    assert NAME not in str(e.value)
    assert len(_attempts(conn)) == MAX_ATTEMPTS


def test_request_has_the_document_lines_and_image(parsed, conn, s3):
    document, pages = parsed
    client = ScriptedClient(extraction_json(1, 1))

    extract(document, pages, s3, TrackedModel(client, conn))

    [request] = client.requests
    assert "[1] Account Number: 111" in request.parts[1].text
    assert request.parts[2].png == s3.get(pages[0].image_key)


def test_ssn_like_account_is_dropped_but_extraction_kept(parsed, conn, s3):
    document, pages = parsed
    answer = extraction_json(1, 1).replace("123456789", "999-40-5000")

    result = extract(document, pages, s3, TrackedModel(ScriptedClient(answer), conn))

    [mention] = result.borrowers
    assert (mention.name, mention.accounts) == (NAME, [])


def test_retry_after_invalid_output_tells_the_model_what_to_fix(parsed, conn, s3):
    document, pages = parsed
    client = ScriptedClient(extraction_json(205, 25, name=NAME), extraction_json(1, 1))

    extract(document, pages, s3, TrackedModel(client, conn))

    first, second = client.requests
    feedback = second.parts[-1].text
    assert second.parts[:-1] == first.parts  # same document, plus the feedback
    assert "borrowers.0.name_source" in feedback and "cited lines are not in the document" in feedback
    assert NAME not in feedback  # paths and messages only, no document values


def test_retry_after_api_error_resends_the_same_request(parsed, conn, s3):
    document, pages = parsed
    client = FlakyClient(extraction_json(1, 1))

    extract(document, pages, s3, TrackedModel(client, conn))

    first, second = client.requests
    assert second == first
