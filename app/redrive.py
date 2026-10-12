import logging
import sqlite3

import hydra
from hydra.utils import instantiate
from omegaconf import DictConfig

from app import db
from app.config import CONFIG_NAME, CONFIG_PATH, HYDRA_VERSION_BASE
from app.db import DocumentStatus
from app.local_sqs import LocalSQS
from app.log import LogContext, Stage
from app.messages import DocumentMessage


def logger() -> logging.Logger:
    return logging.getLogger(__name__)


def redrive(conn: sqlite3.Connection, queue: LocalSQS, batch_id: str | None = None) -> int:
    """Move DLQ messages back to the queue (only `batch_id`'s, if given) and re-queue their documents."""

    def keep(body: str) -> bool:
        message = DocumentMessage.parse(body)
        if message is None:
            return False
        if batch_id is None:
            return True
        doc = db.get_document(conn, message.document_id)
        return doc is not None and doc.batch_id == batch_id

    moved = [DocumentMessage.model_validate_json(body) for body in queue.redrive(keep)]
    for message in moved:
        db.set_status(conn, message.document_id, DocumentStatus.QUEUED)
        ctx = LogContext(Stage.REDRIVE, document_id=message.document_id, status=DocumentStatus.QUEUED)
        logger().info("redriven", extra=ctx.extra())
    logger().info(f"redrove {len(moved)} messages", extra=LogContext(Stage.REDRIVE, batch_id=batch_id).extra())
    return len(moved)


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    conn = db.connect(cfg.db_path)
    queue = instantiate(cfg.queue)
    redrive(conn, queue, cfg.batch_id)


if __name__ == "__main__":
    main()
