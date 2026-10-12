import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_conn

router = APIRouter(tags=["health"])

HEALTH_QUERY = "SELECT 1"
OK = "ok"


class Health(BaseModel):
    status: str


@router.get("/health", response_model=Health)
def health(conn: sqlite3.Connection = Depends(get_conn)) -> Health:
    """The API is up and can read the database."""
    conn.execute(HEALTH_QUERY)
    return Health(status=OK)
