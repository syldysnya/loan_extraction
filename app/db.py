import sqlite3
from dataclasses import astuple, dataclass, fields
from enum import StrEnum

from pydantic import TypeAdapter

from app.parsing.types import Page


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Document:
    id: str
    batch_id: str
    filename: str
    sha256: str
    status: DocumentStatus
    error: str | None = None

    def __post_init__(self) -> None:
        # Rows come back from SQLite as plain strings.
        self.status = DocumentStatus(self.status)


# Column list in Document field order, so a row maps straight onto Document(*row).
COLUMNS = ", ".join(f.name for f in fields(Document))
PLACEHOLDERS = ", ".join("?" for _ in fields(Document))

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    id       TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    sha256   TEXT NOT NULL UNIQUE,
    status   TEXT NOT NULL CHECK (status IN ({", ".join(f"'{s}'" for s in DocumentStatus)})),
    error    TEXT,
    pages    TEXT  -- JSON list of Page, set by parsing
);
"""

PAGES = TypeAdapter(list[Page])


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def insert_documents(conn: sqlite3.Connection, documents: list[Document]) -> None:
    conn.executemany(f"INSERT INTO documents ({COLUMNS}) VALUES ({PLACEHOLDERS})", [astuple(d) for d in documents])
    conn.commit()


def get_document(conn: sqlite3.Connection, document_id: str) -> Document | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM documents WHERE id = ?", (document_id,)).fetchone()
    return Document(*row) if row else None


def list_documents(conn: sqlite3.Connection, batch_id: str | None = None) -> list[Document]:
    if batch_id is None:
        rows = conn.execute(f"SELECT {COLUMNS} FROM documents ORDER BY filename").fetchall()
    else:
        rows = conn.execute(
            f"SELECT {COLUMNS} FROM documents WHERE batch_id = ? ORDER BY filename", (batch_id,)
        ).fetchall()
    return [Document(*row) for row in rows]


def sha256_exists(conn: sqlite3.Connection, sha256: str) -> bool:
    return conn.execute("SELECT 1 FROM documents WHERE sha256 = ?", (sha256,)).fetchone() is not None


def set_status(conn: sqlite3.Connection, document_id: str, status: DocumentStatus, error: str | None = None) -> None:
    """Update a document's status. The last error is kept unless a new one is given."""
    conn.execute(
        "UPDATE documents SET status = ?, error = COALESCE(?, error) WHERE id = ?",
        (status, error, document_id),
    )
    conn.commit()


def save_pages(conn: sqlite3.Connection, document_id: str, pages: list[Page]) -> None:
    conn.execute("UPDATE documents SET pages = ? WHERE id = ?", (PAGES.dump_json(pages).decode(), document_id))
    conn.commit()


def get_pages(conn: sqlite3.Connection, document_id: str) -> list[Page] | None:
    row = conn.execute("SELECT pages FROM documents WHERE id = ?", (document_id,)).fetchone()
    return PAGES.validate_json(row[0]) if row and row[0] else None
