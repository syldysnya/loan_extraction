import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app import db
from app.api.dependencies import get_conn
from app.resolution.record import BorrowerRecord

router = APIRouter(prefix="/borrowers", tags=["borrowers"])

NOT_FOUND = "Borrower not found"


class BorrowerSummary(BaseModel):
    id: str
    name: str
    conflict_count: int


# Production: each route would also take `_user: User = Depends(require_auth)` (see dependencies.py), and be
# rate limited per client, e.g. with slowapi: `@limiter.limit("60/minute")`, or at the API gateway.


@router.get("", response_model=list[BorrowerSummary])
def list_borrowers(conn: sqlite3.Connection = Depends(get_conn)) -> list[BorrowerSummary]:
    """Every resolved borrower, sorted by name."""
    return [BorrowerSummary(id=b.id, name=b.name, conflict_count=b.conflict_count) for b in db.list_borrowers(conn)]


@router.get("/{borrower_id}", response_model=BorrowerRecord)
def get_borrower(borrower_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> BorrowerRecord:
    """One borrower's full record: addresses, accounts, income history and conflicts, each value with its sources."""
    row = db.get_borrower(conn, borrower_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return BorrowerRecord.model_validate_json(row.record)
