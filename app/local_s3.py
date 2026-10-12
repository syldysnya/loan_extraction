from pathlib import Path

from app.local_sqs import LocalSQS
from app.messages import DocumentMessage

INPUT_PREFIX = "input"


def input_key(batch_id: str, filename: str) -> str:
    return f"{INPUT_PREFIX}/{batch_id}/{filename}"


class LocalS3:
    """Folder-based stand-in for S3.

    Writing an object under `INPUT_PREFIX` sends a file event to the queue,
    like an S3 → SQS event notification.
    """

    def __init__(self, s3_dir: str, queue: LocalSQS):
        self.root = Path(s3_dir)
        self.queue = queue

    def put(self, key: str, data: bytes, document_id: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if key.startswith(f"{INPUT_PREFIX}/"):
            self.queue.send(DocumentMessage(document_id=document_id).model_dump_json())
