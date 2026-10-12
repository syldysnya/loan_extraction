import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db
from app.api.main import create_app
from app.api.request_id import REQUEST_ID_HEADER
from app.ingest import ingest_folder


@pytest.fixture
def client(folder, conn, s3, worker, tmp_path):
    """The pipeline (fake model) run on the fixture batch, then the API on that database."""
    ingest_folder(str(folder), conn, s3)
    while worker.run_once():
        pass
    return TestClient(create_app(str(tmp_path / "test.db")))


def test_list_returns_each_borrower_summary(client, conn):
    response = client.get("/borrowers")

    assert response.status_code == 200
    [borrower] = db.list_borrowers(conn)
    assert response.json() == [{"id": borrower.id, "name": "John Homeowner", "conflict_count": 0}]


def test_detail_returns_the_full_record_with_sources(client, conn):
    [borrower] = db.list_borrowers(conn)

    record = client.get(f"/borrowers/{borrower.id}").json()

    assert record["name"] == "John Homeowner"
    assert {s["filename"] for s in record["name_sources"]} == {"a.pdf", "b.pdf"}
    assert record["accounts"][0]["number"] == "123456789"
    assert record["conflicts"] == []


def test_unknown_borrower_is_404(client):
    assert client.get("/borrowers/unknown").status_code == 404


def test_request_id_is_returned_and_kept_if_given(client):
    assert client.get("/health").headers[REQUEST_ID_HEADER]
    assert client.get("/health", headers={REQUEST_ID_HEADER: "abc"}).headers[REQUEST_ID_HEADER] == "abc"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_api_connection_cannot_write(tmp_path):
    db.connect(str(tmp_path / "test.db")).close()
    conn = db.connect_read_only(str(tmp_path / "test.db"))

    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM borrowers")
