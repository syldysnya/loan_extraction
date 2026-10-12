import sqlite3
from collections.abc import Iterator

from fastapi import Request

from app import db


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """A read-only connection per request, closed afterwards: the API can't write, and nothing is shared
    between request threads."""
    conn = db.connect_read_only(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


# Production: authentication and authorization as a dependency on every borrower route, e.g.
#
#     def require_auth(token: str = Depends(oauth2_scheme)) -> User:
#         """Validate the bearer token (JWT from the identity provider) and return the caller."""
#
#     def require_borrower_access(borrower_id: str, user: User = Depends(require_auth)) -> None:
#         """403 unless the caller may read this borrower (e.g. their organization owns the loan file)."""
#
# Every read of a borrower would also be written to an audit log (who, which borrower, when).
