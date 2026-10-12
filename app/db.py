import sqlite3
import uuid
from dataclasses import astuple, dataclass, fields
from enum import StrEnum

from pydantic import TypeAdapter

from app.extraction.schema import BorrowerMention, DocumentType
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
    document_type: DocumentType | None = None  # set by extraction

    def __post_init__(self) -> None:
        # Rows come back from SQLite as plain strings.
        self.status = DocumentStatus(self.status)
        if self.document_type is not None:
            self.document_type = DocumentType(self.document_type)


@dataclass
class LLMCall:
    """One LLM call: what it used and cost. No prompt or response (they contain PII)."""

    id: str
    document_id: str
    batch_id: str
    model_id: str
    attempt: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    error_type: str | None
    created_at: str


@dataclass
class StoredMention:
    id: str
    document_id: str
    mention: BorrowerMention
    borrower_id: str | None


@dataclass
class ModelCost:
    """Totals for one model, as printed by `hatch run costs`."""

    model_id: str
    calls: int
    failed_calls: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cost_usd: float


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
    document_type TEXT,  -- set by extraction
    pages    TEXT  -- JSON list of Page, set by parsing
);

CREATE TABLE IF NOT EXISTS borrower_mentions (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    data        TEXT NOT NULL,  -- JSON BorrowerMention
    borrower_id TEXT            -- set by resolution
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id                  TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL,
    batch_id            TEXT NOT NULL,
    model_id            TEXT NOT NULL,
    attempt             INTEGER NOT NULL,
    input_tokens        INTEGER NOT NULL,
    cached_input_tokens INTEGER NOT NULL,
    output_tokens       INTEGER NOT NULL,
    cost_usd            REAL NOT NULL,
    duration_ms         INTEGER NOT NULL,
    error_type          TEXT,  -- exception class name only, never the message
    created_at          TEXT NOT NULL
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


def set_document_type(conn: sqlite3.Connection, document_id: str, document_type: DocumentType) -> None:
    conn.execute("UPDATE documents SET document_type = ? WHERE id = ?", (document_type, document_id))
    conn.commit()


def save_pages(conn: sqlite3.Connection, document_id: str, pages: list[Page]) -> None:
    conn.execute("UPDATE documents SET pages = ? WHERE id = ?", (PAGES.dump_json(pages).decode(), document_id))
    conn.commit()


def get_pages(conn: sqlite3.Connection, document_id: str) -> list[Page] | None:
    row = conn.execute("SELECT pages FROM documents WHERE id = ?", (document_id,)).fetchone()
    return PAGES.validate_json(row[0]) if row and row[0] else None


LLM_CALL_COLUMNS = ", ".join(f.name for f in fields(LLMCall))
LLM_CALL_PLACEHOLDERS = ", ".join("?" for _ in fields(LLMCall))


def insert_llm_call(conn: sqlite3.Connection, call: LLMCall) -> None:
    conn.execute(f"INSERT INTO llm_calls ({LLM_CALL_COLUMNS}) VALUES ({LLM_CALL_PLACEHOLDERS})", astuple(call))
    conn.commit()


def cost_by_model(conn: sqlite3.Connection, batch_id: str | None = None) -> list[ModelCost]:
    """Totals per model, for one batch or all of them. Column order matches ModelCost."""
    totals = """
        SELECT model_id, COUNT(*), COUNT(error_type), SUM(input_tokens), SUM(cached_input_tokens),
               SUM(output_tokens), SUM(cost_usd)
        FROM llm_calls {where} GROUP BY model_id ORDER BY model_id
    """
    if batch_id is None:
        rows = conn.execute(totals.format(where="")).fetchall()
    else:
        rows = conn.execute(totals.format(where="WHERE batch_id = ?"), (batch_id,)).fetchall()
    return [ModelCost(*row) for row in rows]


def replace_mentions(conn: sqlite3.Connection, document_id: str, mentions: list[BorrowerMention]) -> None:
    """Store a document's mentions, replacing any from an earlier run, so retries don't duplicate them."""
    with conn:
        conn.execute("DELETE FROM borrower_mentions WHERE document_id = ?", (document_id,))
        conn.executemany(
            "INSERT INTO borrower_mentions (id, document_id, data) VALUES (?, ?, ?)",
            [(uuid.uuid4().hex, document_id, m.model_dump_json()) for m in mentions],
        )


def list_mentions(conn: sqlite3.Connection, document_id: str | None = None) -> list[StoredMention]:
    query = "SELECT id, document_id, data, borrower_id FROM borrower_mentions"
    if document_id is None:
        rows = conn.execute(f"{query} ORDER BY document_id").fetchall()
    else:
        rows = conn.execute(f"{query} WHERE document_id = ?", (document_id,)).fetchall()
    return [
        StoredMention(id, doc_id, BorrowerMention.model_validate_json(data), borrower_id)
        for id, doc_id, data, borrower_id in rows
    ]
