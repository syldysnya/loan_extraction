# Query API: LLD

## Endpoints (`app/api/`)

| Endpoint | Response | Errors |
| --- | --- | --- |
| `GET /borrowers` | `list[BorrowerSummary]`, sorted by name | – |
| `GET /borrowers/{id}` | `BorrowerRecord` (the stored record, as built by resolution) | `404` if the id is unknown |
| `GET /health` | `{"status": "ok"}` if the database can be read | – |

```python
class BorrowerSummary(BaseModel):
    id: str
    name: str
    conflict_count: int
```

`BorrowerRecord` is the resolution model (`app/resolution/record.py`): name, SSN last 4 values, residence and property addresses, accounts, income history and conflicts, each value with its `Source`s (document, type, pages, quote).

OpenAPI docs are generated at `/docs`.

## App

| Module | Contents |
| --- | --- |
| `main.py` | `create_app(db_path)` (a factory, so tests can point it at a test database) and the Hydra entry point |
| `borrowers_api.py`, `health_api.py` | One `APIRouter` per resource, with `response_model`s for the OpenAPI docs |
| `dependencies.py` | `get_conn`, injected with `Depends` |
| `request_id.py` | `RequestIDMiddleware`: takes `X-Request-Id` from the caller or makes one, returns it, and logs each request with it |

GZip compresses large responses. Authentication, authorization, rate limiting and CORS are not implemented: comments in the code say what production would add and where.

- Each request opens its own **read-only** connection (`sqlite3.connect("file:{path}?mode=ro", uri=True)`) through a FastAPI dependency and closes it afterwards. The API can't write, and nothing is shared between request threads.

## Database

- `db.connect` turns on WAL mode (`PRAGMA journal_mode=WAL`), so readers don't block the worker's writes and the other way round. WAL is stored in the database file, so read-only connections use it too.
- `db.connect_read_only(path)` opens the read-only connection, without creating the schema.

## Running

`hatch run api` runs `python -m app.api.main` (a Hydra entry point, like the other commands), which starts Uvicorn with:

```yaml
# conf/config.yaml
api:
  host: 127.0.0.1   # localhost only: the records hold PII
  port: 8000
```

## Logging

The API logs each request as method, path and status code under a new `api` log stage, with its request ID. Paths contain borrower IDs only, never names. Uvicorn's own access log is turned off, since it would repeat each line without the request ID.

## Dependencies

`fastapi`, `uvicorn`.

## PR

One PR: endpoints, read-only connections, WAL, config, `hatch run api`.

Tests (FastAPI `TestClient`, no server):

- List returns every borrower's id, name and conflict count.
- Detail returns the full record, including sources and conflicts.
- Unknown id returns 404.
- The API's connection can't write.
- End to end: run the pipeline on a fixture batch, then read the borrower through the API.
