import logging
import sqlite3
import time

import hydra
from hydra.utils import instantiate
from omegaconf import DictConfig

from app import db
from app.config import CONFIG_NAME, CONFIG_PATH, HYDRA_VERSION_BASE
from app.db import Document, DocumentStatus
from app.errors import NonRetryableError, safe_error
from app.extraction.extractor import extract
from app.extraction.tracking import TrackedModel
from app.local_s3 import LocalS3
from app.local_sqs import LocalSQS, ReceivedMessage
from app.log import LogContext, Stage
from app.messages import DocumentMessage
from app.parsing.registry import ParserRegistry
from app.parsing.step import parse_document
from app.resolution.resolve import resolve_all


def logger() -> logging.Logger:
    return logging.getLogger(__name__)


class DocumentWorker:
    def __init__(
        self,
        conn: sqlite3.Connection,
        queue: LocalSQS,
        s3: LocalS3,
        registry: ParserRegistry,
        model: TrackedModel,
    ):
        self.conn = conn
        self.queue = queue
        self.s3 = s3
        self.registry = registry
        self.model = model

    def process_document(self, document: Document) -> None:
        """Per-document work: parse, then extract. Resolution is added by a later feature."""
        pages = parse_document(document, self.s3, self.registry)
        db.save_pages(self.conn, document.id, pages)
        extraction = extract(document, pages, self.s3, self.model)
        db.set_document_type(self.conn, document.id, extraction.document_type)
        db.replace_mentions(self.conn, document.id, extraction.borrowers)

    def run_once(self) -> bool:
        """Handle one message. Returns False if the queue had nothing visible."""
        received = self.queue.receive(self._on_dead_letter)
        if received is None:
            return False

        # A malformed message can't be fixed by redelivery, so delete it instead of retrying.
        message = DocumentMessage.parse(received.body)
        document = db.get_document(self.conn, message.document_id) if message else None
        if document is None:
            self.queue.delete(received.receipt_handle)
            ctx = LogContext(Stage.WORKER)
            logger().error(f"deleted malformed message {received.receipt_handle}", extra=ctx.extra())
            return True
        document_id = document.id

        db.set_status(self.conn, document_id, DocumentStatus.PROCESSING)
        logger().info("processing", extra=self._ctx(document_id, DocumentStatus.PROCESSING).extra())
        try:
            self.process_document(document)
        except NonRetryableError as e:
            # e.g. an unsupported file type, or extraction failing all its attempts: fail now, no DLQ round trip.
            self._fail_now(received, document_id, safe_error(e))
            self._resolve_if_batch_finished(document.batch_id)
            return True
        except Exception as e:
            # Leave the message: it becomes visible again after the visibility timeout.
            # Only the safe description is stored and logged: messages and tracebacks can contain document data.
            error = safe_error(e)
            db.set_status(self.conn, document_id, DocumentStatus.QUEUED, error=error)
            logger().error(f"failed, will retry: {error}", extra=self._ctx(document_id, DocumentStatus.QUEUED).extra())
            return True

        db.set_status(self.conn, document_id, DocumentStatus.DONE)
        self.queue.delete(received.receipt_handle)
        logger().info("done", extra=self._ctx(document_id, DocumentStatus.DONE).extra())
        self._resolve_if_batch_finished(document.batch_id)
        return True

    def _fail_now(self, received: ReceivedMessage, document_id: str, error: str) -> None:
        db.set_status(self.conn, document_id, DocumentStatus.FAILED, error=error)
        self.queue.delete(received.receipt_handle)
        logger().error(f"failed, not retried: {error}", extra=self._ctx(document_id, DocumentStatus.FAILED).extra())

    def _on_dead_letter(self, body: str) -> None:
        message = DocumentMessage.parse(body)
        document_id = message.document_id if message else None
        document = db.get_document(self.conn, document_id) if document_id else None
        if document:
            db.set_status(self.conn, document.id, DocumentStatus.FAILED)
        logger().error("moved to DLQ", extra=self._ctx(document_id, DocumentStatus.FAILED).extra())
        if document:
            self._resolve_if_batch_finished(document.batch_id)

    def _resolve_if_batch_finished(self, batch_id: str) -> None:
        """Rebuild borrowers once nothing in the batch is queued or processing. Never fails a document."""
        if db.unfinished_count(self.conn, batch_id) > 0:
            return
        try:
            resolve_all(self.conn)
        except Exception as e:
            ctx = LogContext(Stage.RESOLVE, batch_id=batch_id)
            logger().error(f"resolution failed: {safe_error(e)}", extra=ctx.extra())

    def _ctx(self, document_id: str | None, status: DocumentStatus) -> LogContext:
        doc = db.get_document(self.conn, document_id) if document_id else None
        return LogContext(Stage.WORKER, batch_id=doc.batch_id if doc else None, document_id=document_id, status=status)


@hydra.main(version_base=HYDRA_VERSION_BASE, config_path=CONFIG_PATH, config_name=CONFIG_NAME)
def main(cfg: DictConfig) -> None:
    conn = db.connect(cfg.db_path)
    queue = instantiate(cfg.queue)
    worker = DocumentWorker(
        conn=conn,
        queue=queue,
        s3=instantiate(cfg.s3, queue=queue),
        registry=instantiate(cfg.parsing),
        model=instantiate(cfg.model, conn=conn),
    )
    logger().info("started, polling queue", extra=LogContext(Stage.WORKER).extra())
    while True:
        if not worker.run_once():
            time.sleep(cfg.poll_interval_s)


if __name__ == "__main__":
    main()
