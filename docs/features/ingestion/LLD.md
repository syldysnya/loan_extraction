# Ingestion: LLD

## Commands

Hatch scripts, defined in `pyproject.toml`:

```bash
hatch run ingest folder=data/loan_data   # upload a batch
hatch run worker                         # consume the queue
hatch run redrive                        # move DLQ messages back to the queue
```

## Upload

1. Create a `batch_id`.
2. For each file, compute its sha256. Skip the file if that hash is already in `documents`.
3. Insert a `documents` row (`queued`) for every remaining file.
4. Write each file to `s3/input/{batch_id}/{filename}`.

All rows are inserted before any file is written.

## Local S3

- A folder, `s3/`.
- Writing an object under `input/` sends `{"document_id": ...}` to the queue. This is the "file event".

## Local SQS

- `queue/main/` and `queue/dlq/`. One JSON file per message: `{id, body, receive_count, visible_at}`.
- **send:** writes a new message file.
- **receive:** takes the oldest message whose `visible_at` has passed, increments `receive_count`, and sets `visible_at = now + 5 min`. If `receive_count` is already 3, the message moves to `queue/dlq/` instead of being returned.
- **delete:** removes the message file.

## Worker

| Outcome | Action |
| --- | --- |
| Received | Set the document to `processing`. |
| Success | Set the document to `done`, then delete the message. |
| Exception | Set the document back to `queued`, save the error, and leave the message. It is retried after 5 min. |
| Moved to DLQ | Set the document to `failed`. |

The per-document work (parse, extract, resolve) is added by later features.

## Redrive

For each message in `queue/dlq/`: reset its `receive_count` to 0, move it to `queue/main/`, and set its document to `queued`.

## Table: `documents`

| Column | Type |
| --- | --- |
| `id` | text, primary key |
| `batch_id` | text |
| `filename` | text |
| `sha256` | text, unique |
| `status` | `queued` \| `processing` \| `done` \| `failed` |
| `error` | text, nullable |

## Batch status

Derived from the batch's documents, not stored:

| Documents | Batch status |
| --- | --- |
| Any `queued` or `processing` | `processing` |
| All `done` or `failed` | `completed` |

## Config (`conf/config.yaml`)

`s3_dir`, `queue_dir`, `db_path`, `visibility_timeout_s: 300`, `max_receive_count: 3`
