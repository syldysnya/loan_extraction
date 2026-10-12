# Extraction: LLD

## Extraction schema (`app/extraction/schema.py`)

The LLM returns one `DocumentExtraction` per document. Every value carries its source.

```python
class SourceRef(BaseModel):
    line_start: int               # document-wide line numbers, as shown to the model
    line_end: int

class IncomeKind(StrEnum):
    WAGES = "wages"               # W-2, paystub, EVOE
    SELF_EMPLOYMENT = "self_employment"   # Schedule C
    OTHER = "other"

class AccountKind(StrEnum):
    BANK_ACCOUNT = "bank_account"
    LOAN = "loan"

class Address(BaseModel):
    value: str
    source: SourceRef

class IncomeEntry(BaseModel):
    amount: float
    period: str                   # as written, e.g. "2024" or "04/12/25 - 04/25/25"
    kind: IncomeKind
    payer: str | None             # employer or business
    source: SourceRef

class Account(BaseModel):
    number: str
    kind: AccountKind
    source: SourceRef

class BorrowerMention(BaseModel):
    name: str
    name_source: SourceRef
    ssn_last4: str | None         # last 4 digits only, never the full SSN
    addresses: list[Address]
    income: list[IncomeEntry]
    accounts: list[Account]

class DocumentExtraction(BaseModel):
    borrowers: list[BorrowerMention]
```

A joint document (e.g. the joint 1040) gives one `BorrowerMention` per person, and shared values such as a joint account appear under each of them.

The model cites line numbers only. The page, the quote (the cited lines' text) and the bounding boxes are looked up from `documents.pages`, so they can't be invented:

`resolve(ref, pages) -> Evidence(page_no, quote, bboxes)`

## LLM clients (`app/extraction/llm.py`)

```python
class Pricing(BaseModel):         # USD per 1M tokens
    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float

class Usage(BaseModel):
    input_tokens: int             # includes cached tokens
    cached_input_tokens: int
    output_tokens: int            # includes thinking tokens

class LLMClient(ABC):
    model_id: str
    pricing: Pricing
    supports_image_input: bool
    def complete(self, request: LLMRequest, schema: type[BaseModel]) -> RawResponse: ...  # RawResponse: text (JSON), usage

# LLMRequest: system_prompt + parts (TextPart | ImagePart)
```

| Client | SDK | Structured output | Usage fields |
| --- | --- | --- | --- |
| `GeminiClient` | `google-genai` | `response_schema=DocumentExtraction` | `prompt_token_count`, `cached_content_token_count`, `candidates_token_count + thoughts_token_count` |
| `OpenAIClient` | `openai` | `response_format=DocumentExtraction` | `prompt_tokens`, `prompt_tokens_details.cached_tokens`, `completion_tokens` |

Cost = `(input − cached) × input_per_1m + cached × cached_input_per_1m + output × output_per_1m`, all ÷ 1M.

## Model config (`conf/model/`)

Each config builds a `TrackedModel` around its client, so tracking can't be skipped. The DB connection is passed in at runtime: `instantiate(cfg.model, conn=conn)`.

```yaml
# conf/model/gemini.yaml
_target_: app.extraction.tracking.TrackedModel
client:
  _target_: app.extraction.llm.GeminiClient
  model_id: gemini-3.5-flash-lite
  api_key: ${oc.env:GOOGLE_API_KEY}
  supports_image_input: true
  temperature: 0.0
  max_output_tokens: 8192
  pricing: {_target_: app.extraction.llm.Pricing, input_per_1m: 0.30, cached_input_per_1m: 0.03, output_per_1m: 2.50}

# conf/model/openai.yaml: same shape, OpenAIClient, gpt-4o-mini, OPENAI_API_KEY,
# pricing 0.15 / 0.075 / 0.60
```

Default: `model: gemini`. Switch with `model=openai`. A missing API key fails at startup ("environment variable not found"). Prices were checked on 2026-10-12; confirm against the providers' pricing pages before relying on cost totals.

## Tracking (`app/extraction/tracking.py`)

`TrackedModel` wraps an `LLMClient`. `generate(request, schema, ctx)` calls the client, validates the JSON against `schema`, and writes one `llm_calls` row whether it succeeds or fails. Validation happens here, after the usage is known, so an invalid answer still records its tokens. Errors are re-raised.

| Column | Type |
| --- | --- |
| `id` | text, primary key |
| `document_id`, `batch_id` | text |
| `model_id` | text |
| `attempt` | int (1–3) |
| `input_tokens`, `cached_input_tokens`, `output_tokens` | int (0 if the call failed before a response) |
| `cost_usd` | real |
| `duration_ms` | int |
| `error_type` | text, nullable (exception class name only) |
| `created_at` | text |

No prompts or responses are stored.

## Request

- **System prompt:** extract every borrower, cite the line range each value comes from, SSN last 4 only, return JSON matching the schema.
- **One part per page,** in order: `Page {n}:`, then its lines as `[line_no] text`, then the page image from S3. OCR'd pages are marked so the model knows their text may contain OCR errors.
- If the model has `supports_image_input: false`, images are left out.

## Extractor (`app/extraction/extractor.py`)

`extract(document, pages, model) -> DocumentExtraction`

- Up to 3 attempts. An attempt fails on an API error, output that fails validation, or a cited line number that doesn't exist in the document.
- After the 3rd failure, raises `ExtractionFailed`.

## Errors

- `NonRetryableError`: a new base class. `UnsupportedFileType` and `ExtractionFailed` extend it. The worker fails these documents at once (no queue retry).
- `safe_error(e) -> str`: the exception type plus, for validation errors, the field paths only (e.g. `ValidationError: borrowers.0.income.2.amount`). Never the values. Used for `documents.error` and logs everywhere, replacing `str(e)`.

## Storage: `borrower_mentions`

One row per `BorrowerMention`, replacing the planned `extracted_fields` table: all of a mention's values belong to the same person, so resolution links the mention, not each field.

| Column | Type |
| --- | --- |
| `id` | text, primary key |
| `document_id` | text |
| `data` | JSON (`BorrowerMention`) |
| `borrower_id` | text, nullable, set by resolution |

A re-run of a document replaces its mentions, so retries don't duplicate them.

## Worker step

`process_document`: parse → `extract` → save mentions → `done`.

## Costs CLI

`hatch run costs [batch_id=<id>]` prints, per model: calls, failed calls, input / cached / output tokens, and total cost in USD.

## PRs

| PR | Scope | Tests |
| --- | --- | --- |
| 1. LLM clients + tracking | `Pricing`, `Usage`, `LLMClient`, `GeminiClient`, `OpenAIClient`, Hydra model configs, `TrackedModel`, `llm_calls`, `hatch run costs` | Cost formula; a row per call, including failures; costs totals. Fake client, no network. |
| 2. Schema + extractor | Schema, `resolve`, request building, `extract` with 3 attempts, `ExtractionFailed`, `NonRetryableError`, `safe_error` | Valid output; unknown line number → retry; retry then success; 3 failures raise; `resolve` returns page, quote and boxes; `safe_error` never contains values |
| 3. Worker wiring | `borrower_mentions`, extraction in `process_document`, `safe_error` in the worker | Worker stores mentions; extraction failure fails at once. End to end on the corpus with both models (needs API keys). |
