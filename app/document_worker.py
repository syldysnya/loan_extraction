import logging
import sqlite3
import time

import hydra
from hydra.utils import instantiate
from omegaconf import DictConfig

from app import db
from app.config import CONFIG_NAME, CONFIG_PATH, HYDRA_VERSION_BASE
from app.db import DocumentStatus
from app.local_s3 import LocalS3
from app.local_sqs import LocalSQS, ReceivedMessage
from app.log import LogContext, Stage
from app.messages import DocumentMessage
from app.parsing.registry import ParserRegistry, build_registry
from app.parsing.step import parse_document
from app.parsing.types import UnsupportedFileType


def logger() -> logging.Logger:
    return logging.getLogger(__name__)


class DocumentWorker:
    def __init__(self, conn: sqlite3.Connection, queue: LocalSQS, s3: LocalS3, registry: ParserRegistry):
        self.conn = conn
        self.queue = queue
        self.s3 = s3
        self.registry = registry

    def process_document(self, document_id: str) -> None:
        """Per-document work: parse. Extraction and resolution are added by later features."""
        document = db.get_document(self.conn, document_id)
        pages = parse_document(document, self.s3, self.registry)
        db.save_pages(self.conn, document_id, pages)

    def run_once(self) -> bool:
        """Handle one message. Returns False if the queue had nothing visible."""
        received = self.queue.receive(self._on_dead_letter)
        if received is None:
            return False

        # A malformed message can't be fixed by redelivery, so delete it instead of retrying.
        message = DocumentMessage.parse(received.body)
        if message is None or db.get_document(self.conn, message.document_id) is None:
            self.queue.delete(received.receipt_handle)
            ctx = LogContext(Stage.WORKER)
            logger().error(f"deleted malformed message {received.receipt_handle}", extra=ctx.extra())
            return True
        document_id = message.document_id

        db.set_status(self.conn, document_id, DocumentStatus.PROCESSING)
        logger().info("processing", extra=self._ctx(document_id, DocumentStatus.PROCESSING).extra())
        try:
            self.process_document(document_id)
        except UnsupportedFileType as e:
            # A retry can't change the file type, so fail now instead of going through the DLQ.
            self._fail_now(received, document_id, str(e))
            return True
        except Exception as e:
            # Leave the message: it becomes visible again after the visibility timeout.
            db.set_status(self.conn, document_id, DocumentStatus.QUEUED, error=str(e))
            logger().exception("failed, will retry", extra=self._ctx(document_id, DocumentStatus.QUEUED).extra())
            return True

        db.set_status(self.conn, document_id, DocumentStatus.DONE)
        self.queue.delete(received.receipt_handle)
        logger().info("done", extra=self._ctx(document_id, DocumentStatus.DONE).extra())
        return True

    def _fail_now(self, received: ReceivedMessage, document_id: str, error: str) -> None:
        db.set_status(self.conn, document_id, DocumentStatus.FAILED, error=error)
        self.queue.delete(received.receipt_handle)
        logger().error(f"failed, not retried: {error}", extra=self._ctx(document_id, DocumentStatus.FAILED).extra())

    def _on_dead_letter(self, body: str) -> None:
        message = DocumentMessage.parse(body)
        document_id = message.document_id if message else None
        if document_id:
            db.set_status(self.conn, document_id, DocumentStatus.FAILED)
        logger().error("moved to DLQ", extra=self._ctx(document_id, DocumentStatus.FAILED).extra())

    def _ctx(self, document_id: str | None, status: DocumentStatus) -> LogContext:
        doc = db.get_document(self.conn, document_id) if document_id else None
        return LogContext(Stage.WORKER, batch_id=doc.batch_id if doc else None, document_id=document_id, status=status)


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    queue = instantiate(cfg.queue)
    worker = DocumentWorker(
        conn=db.connect(cfg.db_path),
        queue=queue,
        s3=instantiate(cfg.s3, queue=queue),
        registry=build_registry(cfg.parsing.render_dpi),
    )
    logger().info("started, polling queue", extra=LogContext(Stage.WORKER).extra())
    while True:
        if not worker.run_once():
            time.sleep(cfg.poll_interval_s)


if __name__ == "__main__":
    main()
