import pytest

from app.local_s3 import input_key, page_key


def test_get_returns_what_put_wrote(s3):
    s3.put(page_key("doc1", 1), b"png bytes")

    assert s3.get(page_key("doc1", 1)) == b"png bytes"


def test_only_input_objects_send_a_file_event(s3, queue):
    s3.put(page_key("doc1", 1), b"png bytes")
    assert list(queue.main.glob("*.json")) == []

    s3.put(input_key("batch1", "a.pdf"), b"pdf bytes", document_id="doc1")
    assert len(list(queue.main.glob("*.json"))) == 1


def test_input_object_without_document_id_raises(s3):
    with pytest.raises(ValueError):
        s3.put(input_key("batch1", "a.pdf"), b"pdf bytes")
