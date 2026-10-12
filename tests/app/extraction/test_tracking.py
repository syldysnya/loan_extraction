import pytest
from pydantic import BaseModel, ValidationError

from app import db
from app.extraction.llm import LLMClient, LLMRequest, Pricing, RawResponse, Usage
from app.extraction.tracking import CallContext, TrackedModel

PRICING = Pricing(input_per_1m=1.0, cached_input_per_1m=0.5, output_per_1m=2.0)
USAGE = Usage(input_tokens=1000, cached_input_tokens=0, output_tokens=500)
REQUEST = LLMRequest(system_prompt="extract", parts=[])


class Answer(BaseModel):
    value: int


class FakeClient(LLMClient):
    def __init__(self, text: str | None = None, error: Exception | None = None):
        super().__init__("fake-model", PRICING, supports_image_input=True, temperature=0.0, max_output_tokens=100)
        self.text = text
        self.error = error

    def complete(self, request: LLMRequest, schema: type[BaseModel]) -> RawResponse:
        if self.error:
            raise self.error
        return RawResponse(text=self.text or "", usage=USAGE)


def _calls(conn) -> list[db.LLMCall]:
    return [db.LLMCall(*row) for row in conn.execute(f"SELECT {db.LLM_CALL_COLUMNS} FROM llm_calls")]


def test_success_returns_validated_output_and_records_cost(conn):
    model = TrackedModel(FakeClient('{"value": 7}'), conn)

    assert model.generate(REQUEST, Answer, CallContext("doc1", "batch1", attempt=1)) == Answer(value=7)

    [call] = _calls(conn)
    assert (call.document_id, call.batch_id, call.model_id, call.attempt) == ("doc1", "batch1", "fake-model", 1)
    assert (call.input_tokens, call.output_tokens, call.error_type) == (1000, 500, None)
    assert call.cost_usd == pytest.approx((1000 * 1.0 + 500 * 2.0) / 1_000_000)


def test_invalid_output_raises_but_tokens_are_recorded(conn):
    model = TrackedModel(FakeClient('{"value": "not a number"}'), conn)

    with pytest.raises(ValidationError):
        model.generate(REQUEST, Answer, CallContext("doc1", "batch1", attempt=2))

    [call] = _calls(conn)
    assert (call.error_type, call.input_tokens, call.attempt) == ("ValidationError", 1000, 2)
    assert call.cost_usd > 0


def test_api_error_is_recorded_with_zero_tokens(conn):
    model = TrackedModel(FakeClient(error=TimeoutError("api down")), conn)

    with pytest.raises(TimeoutError):
        model.generate(REQUEST, Answer, CallContext("doc1", "batch1", attempt=1))

    [call] = _calls(conn)
    assert (call.error_type, call.input_tokens, call.cost_usd) == ("TimeoutError", 0, 0)


def test_cost_by_model_totals_and_batch_filter(conn):
    ok = TrackedModel(FakeClient('{"value": 1}'), conn)
    bad = TrackedModel(FakeClient("not json"), conn)
    ok.generate(REQUEST, Answer, CallContext("d1", "b1", 1))
    with pytest.raises(ValidationError):
        bad.generate(REQUEST, Answer, CallContext("d2", "b2", 1))

    [all_batches] = db.cost_by_model(conn)
    assert (all_batches.calls, all_batches.failed_calls, all_batches.input_tokens) == (2, 1, 2000)

    [one_batch] = db.cost_by_model(conn, batch_id="b1")
    assert (one_batch.calls, one_batch.failed_calls) == (1, 0)
