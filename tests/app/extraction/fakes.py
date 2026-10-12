from pydantic import BaseModel

from app.extraction.llm import LLMClient, LLMRequest, Pricing, RawResponse, Usage
from app.extraction.schema import Account, AccountKind, BorrowerMention, DocumentExtraction, SourceRef

PRICING = Pricing(input_per_1m=1.0, cached_input_per_1m=0.5, output_per_1m=2.0)


class ScriptedClient(LLMClient):
    """Answers with the given texts in order, one per call."""

    def __init__(self, *answers: str, supports_image_input: bool = True):
        super().__init__("fake-model", PRICING, supports_image_input, temperature=0.0, max_output_tokens=100)
        self.answers = list(answers)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest, schema: type[BaseModel]) -> RawResponse:
        self.requests.append(request)
        return RawResponse(text=self.answers.pop(0), usage=Usage(input_tokens=100, output_tokens=10))


def extraction_json(line_start: int = 1, line_end: int = 1, name: str = "John Homeowner") -> str:
    ref = SourceRef(line_start=line_start, line_end=line_end)
    mention = BorrowerMention(
        name=name,
        name_source=ref,
        ssn_last4="5000",
        addresses=[],
        income=[],
        accounts=[Account(number="123456789", kind=AccountKind.BANK_ACCOUNT, source=ref)],
    )
    return DocumentExtraction(borrowers=[mention]).model_dump_json()
