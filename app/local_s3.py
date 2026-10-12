from pathlib import Path

from app.local_sqs import LocalSQS
from app.messages import DocumentMessage

INPUT_PREFIX = "input"
PAGES_PREFIX = "pages"
PAGE_IMAGE_SUFFIX = ".png"


def input_key(batch_id: str, filename: str) -> str:
    return f"{INPUT_PREFIX}/{batch_id}/{filename}"


def page_key(document_id: str, page_no: int) -> str:
    return f"{PAGES_PREFIX}/{document_id}/{page_no}{PAGE_IMAGE_SUFFIX}"


class LocalS3:
    """Folder-based stand-in for S3.

    Writing an object under `INPUT_PREFIX` sends a file event to the queue,
    like an S3 → SQS event notification.
    """

    def __init__(self, s3_dir: str, queue: LocalSQS):
        self.root = Path(s3_dir)
        self.queue = queue

    def put(self, key: str, data: bytes, document_id: str | None = None) -> None:
        """Write an object. Keys under `INPUT_PREFIX` need a `document_id` for the file event."""
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if key.startswith(f"{INPUT_PREFIX}/"):
            if document_id is None:
                raise ValueError(f"{INPUT_PREFIX}/ objects need a document_id")
            self.queue.send(DocumentMessage(document_id=document_id).model_dump_json())

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()
