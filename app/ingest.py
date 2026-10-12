import hashlib
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

import hydra
from hydra.utils import instantiate
from omegaconf import DictConfig

from app import db
from app.config import CONFIG_NAME, CONFIG_PATH, HYDRA_VERSION_BASE
from app.db import Document, DocumentStatus
from app.local_s3 import LocalS3, input_key
from app.log import LogContext, Stage

HIDDEN_FILE_PREFIX = "."


def logger() -> logging.Logger:
    return logging.getLogger(__name__)


@dataclass
class NewFile:
    document: Document
    data: bytes


def ingest_folder(folder: str, conn: sqlite3.Connection, s3: LocalS3) -> str:
    """Register every new file in `folder` as a batch, then write it to S3 (which queues it)."""
    batch_id = uuid.uuid4().hex
    paths = sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.name.startswith(HIDDEN_FILE_PREFIX))

    new: list[NewFile] = []
    seen: set[str] = set()
    for path in paths:
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        if sha256 in seen or db.sha256_exists(conn, sha256):
            logger().info("skipped duplicate", extra=LogContext(Stage.INGEST, batch_id=batch_id).extra())
            continue
        seen.add(sha256)
        document = Document(uuid.uuid4().hex, batch_id, path.name, sha256, DocumentStatus.QUEUED)
        new.append(NewFile(document, data))

    # Register the whole batch before any file is written, so the worker never sees a partial batch.
    db.insert_documents(conn, [f.document for f in new])

    for f in new:
        s3.put(input_key(batch_id, f.document.filename), f.data, f.document.id)
        ctx = LogContext(Stage.INGEST, batch_id=batch_id, document_id=f.document.id, status=DocumentStatus.QUEUED)
        logger().info("queued", extra=ctx.extra())

    logger().info(f"batch created with {len(new)} documents", extra=LogContext(Stage.INGEST, batch_id=batch_id).extra())
    return batch_id


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    conn = db.connect(cfg.db_path)
    queue = instantiate(cfg.queue)
    ingest_folder(cfg.folder, conn, instantiate(cfg.s3, queue=queue))


if __name__ == "__main__":
    main()
