import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

MAIN_DIR = "main"
DLQ_DIR = "dlq"
MESSAGE_SUFFIX = ".json"
TMP_SUFFIX = ".tmp"


class QueueMessage(BaseModel):
    """A message as stored on disk. The body is a string, as in SQS."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    body: str
    receive_count: int = 0
    visible_at: float = 0


@dataclass
class ReceivedMessage:
    receipt_handle: str
    body: str


class LocalSQS:
    """File-based stand-in for SQS with a DLQ. One JSON file per message.

    File names start with a nanosecond timestamp, so sorting them gives oldest first.
    The receipt handle is the file name.
    """

    def __init__(self, queue_dir: str, visibility_timeout_s: int, max_receive_count: int):
        self.main = Path(queue_dir) / MAIN_DIR
        self.dlq = Path(queue_dir) / DLQ_DIR
        self.main.mkdir(parents=True, exist_ok=True)
        self.dlq.mkdir(parents=True, exist_ok=True)
        self.visibility_timeout_s = visibility_timeout_s
        self.max_receive_count = max_receive_count

    def send(self, body: str) -> None:
        message = QueueMessage(body=body)
        _write(self.main / f"{time.time_ns()}-{message.id}{MESSAGE_SUFFIX}", message)

    def receive(self, on_dead_letter: Callable[[str], None]) -> ReceivedMessage | None:
        """Return the oldest visible message, or None.

        A message that becomes visible after its last allowed receive is moved to the DLQ
        and its body passed to `on_dead_letter` instead of being returned.
        """
        now = time.time()
        for path in sorted(self.main.glob(f"*{MESSAGE_SUFFIX}")):
            message = _read(path)
            if message.visible_at > now:
                continue
            if message.receive_count >= self.max_receive_count:
                path.rename(self.dlq / path.name)
                on_dead_letter(message.body)
                continue
            message.receive_count += 1
            message.visible_at = now + self.visibility_timeout_s
            _write(path, message)
            return ReceivedMessage(receipt_handle=path.name, body=message.body)
        return None

    def delete(self, receipt_handle: str) -> None:
        (self.main / receipt_handle).unlink(missing_ok=True)

    def redrive(self, keep: Callable[[str], bool]) -> list[str]:
        """Move DLQ messages whose body passes `keep` back to the main queue. Returns their bodies."""
        moved = []
        for path in sorted(self.dlq.glob(f"*{MESSAGE_SUFFIX}")):
            message = _read(path)
            if not keep(message.body):
                continue
            message.receive_count = 0
            message.visible_at = 0
            _write(self.main / path.name, message)
            path.unlink()
            moved.append(message.body)
        return moved


def _read(path: Path) -> QueueMessage:
    return QueueMessage.model_validate_json(path.read_text())


def _write(path: Path, message: QueueMessage) -> None:
    # Write to a temp file and rename, so a reader never sees a half-written message.
    tmp = path.with_suffix(TMP_SUFFIX)
    tmp.write_text(message.model_dump_json())
    tmp.replace(path)
