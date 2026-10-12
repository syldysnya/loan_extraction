import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel

from app import db
from app.extraction.llm import LLMClient, LLMRequest, Usage

T = TypeVar("T", bound=BaseModel)

MS_PER_SECOND = 1000


@dataclass
class CallContext:
    document_id: str
    batch_id: str
    attempt: int


class TrackedModel:
    """Wraps an LLMClient: every call is validated and recorded in `llm_calls`, success or not."""

    def __init__(self, client: LLMClient, conn: sqlite3.Connection):
        self.client = client
        self.conn = conn

    def generate(self, request: LLMRequest, schema: type[T], ctx: CallContext, context: object = None) -> T:
        """`context` is passed to Pydantic validation (e.g. to check citations against the document)."""
        started = time.monotonic()
        usage = Usage()
        error_type = None
        try:
            raw = self.client.complete(request, schema)
            usage = raw.usage  # set before validation, so an invalid answer still counts its tokens
            return schema.model_validate_json(raw.text, context=context)
        except Exception as e:
            error_type = type(e).__name__
            raise
        finally:
            db.insert_llm_call(
                self.conn,
                db.LLMCall(
                    id=uuid.uuid4().hex,
                    document_id=ctx.document_id,
                    batch_id=ctx.batch_id,
                    model_id=self.client.model_id,
                    attempt=ctx.attempt,
                    input_tokens=usage.input_tokens,
                    cached_input_tokens=usage.cached_input_tokens,
                    output_tokens=usage.output_tokens,
                    cost_usd=self.client.pricing.cost(usage),
                    duration_ms=round((time.monotonic() - started) * MS_PER_SECOND),
                    error_type=error_type,
                    created_at=datetime.now(UTC).isoformat(),
                ),
            )
