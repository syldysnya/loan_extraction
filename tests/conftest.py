import pytest

from app import db
from app.local_s3 import LocalS3
from app.local_sqs import LocalSQS


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"a")
    (folder / "b.pdf").write_bytes(b"b")
    return folder


@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "test.db"))


@pytest.fixture
def queue(tmp_path):
    # Visibility timeout 0 so retries are immediate.
    return LocalSQS(str(tmp_path / "queue"), visibility_timeout_s=0, max_receive_count=3)


@pytest.fixture
def s3(tmp_path, queue):
    return LocalS3(str(tmp_path / "s3"), queue)


def statuses(conn) -> list[db.DocumentStatus]:
    return [d.status for d in db.list_documents(conn)]
