import logging
import sqlite3
import time

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


def process_document(conn: sqlite3.Connection, document_id: str) -> None:
    """Per-document work. Parsing, extraction and resolution are added by later features."""


def run_once(conn: sqlite3.Connection, queue: LocalSQS) -> bool:
    """Handle one message. Returns False if the queue had nothing visible."""

    def on_dead_letter(body: str) -> None:
        message = DocumentMessage.parse(body)
        document_id = message.document_id if message else None
        if document_id:
            db.set_status(conn, document_id, DocumentStatus.FAILED)
        logger().error("moved to DLQ", extra=_ctx(conn, document_id, DocumentStatus.FAILED).extra())

    received = queue.receive(on_dead_letter)
    if received is None:
        return False

    # A malformed message can't be fixed by redelivery, so delete it instead of retrying.
    message = DocumentMessage.parse(received.body)
    if message is None or db.get_document(conn, message.document_id) is None:
        queue.delete(received.receipt_handle)
        logger().error(f"deleted malformed message {received.receipt_handle}", extra=LogContext(Stage.WORKER).extra())
        return True
    document_id = message.document_id

    db.set_status(conn, document_id, DocumentStatus.PROCESSING)
    logger().info("processing", extra=_ctx(conn, document_id, DocumentStatus.PROCESSING).extra())
    try:
        process_document(conn, document_id)
    except Exception as e:
        # Leave the message: it becomes visible again after the visibility timeout.
        db.set_status(conn, document_id, DocumentStatus.QUEUED, error=str(e))
        logger().exception("failed, will retry", extra=_ctx(conn, document_id, DocumentStatus.QUEUED).extra())
        return True

    db.set_status(conn, document_id, DocumentStatus.DONE)
    queue.delete(received.receipt_handle)
    logger().info("done", extra=_ctx(conn, document_id, DocumentStatus.DONE).extra())
    return True


def _ctx(conn: sqlite3.Connection, document_id: str | None, status: DocumentStatus) -> LogContext:
    doc = db.get_document(conn, document_id) if document_id else None
    return LogContext(Stage.WORKER, batch_id=doc.batch_id if doc else None, document_id=document_id, status=status)


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    conn = db.connect(cfg.db_path)
    queue = instantiate(cfg.queue)
    logger().info("started, polling queue", extra=LogContext(Stage.WORKER).extra())
    while True:
        if not run_once(conn, queue):
            time.sleep(cfg.poll_interval_s)


if __name__ == "__main__":
    main()
