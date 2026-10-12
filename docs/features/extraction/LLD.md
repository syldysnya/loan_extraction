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
    TOTAL = "total"               # stated as the sum of other figures (e.g. 1040 line 9)

class AccountKind(StrEnum):
    BANK_ACCOUNT = "bank_account"
    LOAN = "loan"

class AddressKind(StrEnum):
    RESIDENCE = "residence"       # the person's current home or mailing address
    PROPERTY = "property"         # the loan's subject property (being bought, refinanced or insured)

class Address(BaseModel):
    value: str
    kind: AddressKind
    source: SourceRef

class IncomeBasis(StrEnum):
    PERIOD = "period"             # earned within exactly period_start..period_end
    YEAR_TO_DATE = "year_to_date" # running total from Jan 1 up to period_end

class IncomeEntry(BaseModel):
    amount: float                 # gross, before taxes
    kind: IncomeKind
    basis: IncomeBasis
    period_start: date            # a tax year 2024 → 2024-01-01 … 2024-12-31
    period_end: date              # must not be before period_start
    payer: str | None             # employer or business
    joint: bool                   # belongs to several people together (e.g. wages on a joint return)
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

class DocumentType(StrEnum):
    TAX_RETURN, W2, PAYSTUB, EMPLOYMENT_VERIFICATION, BANK_STATEMENT, CLOSING_DISCLOSURE,
    TITLE_REPORT, UNDERWRITING_SUMMARY, LETTER_OF_EXPLANATION, OTHER

class DocumentExtraction(BaseModel):
    document_type: DocumentType   # first, so the model classifies before extracting
    borrowers: list[BorrowerMention]
```

Income periods are structured so totals can be computed without double counting. Extraction only records them; resolution totals them:

- The same person, payer and period from different documents (e.g. W-2, 1040 and EVOE for 2024) is one figure, counted once.
- `year_to_date` figures are never added to `period` figures for the same span.
- Different periods with the same amount (two paychecks) are added.
- A stated total is its own kind, `IncomeKind.TOTAL` (e.g. 1040 line 9), never wages or other. The model is asked to label it; code (`income.mark_totals`) is the safety net: within one person and period, a figure equal to the sum of at least two non-total figures (within $1) is set to `total`. Totals are never added to their parts: resolution sums the parts and shows the stated total next to them.
- Repeated figures are dropped in code (`income.remove_duplicate_income`): same person, amount, basis, period and joint flag, with matching payers or one payer missing. Documents show the same money twice, e.g. Schedule C line 31 and Schedule 1 line 3 on a 1040.
- `joint` income is counted once for the people who share it, not once per person.
- A `year_to_date` figure covering a full calendar year (Jan 1 to Dec 31) is treated as that year's `period` figure. This is done in code, not asked of the model: a prompt rule for it made extraction less stable.
- Pay rates are not returned.

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

## Prompts (`app/extraction/prompts.py`) and request (`app/extraction/request.py`)

Prompts live in their own module, as named constants with builder functions:

- `EXTRACTION_SYSTEM_PROMPT`: the role, then markdown sections `# Input`, `# Your Task`, `# Rules` (numbered: cite the value's own lines, one entry per person on joint documents, income is earnings only, SSNs and tax IDs are never account numbers, property vs residence addresses, read OCR pages from the image, don't guess) and `# Output Format`.
- The system prompt also has a `# Document Types` section: for each `DocumentType`, what it always contains (e.g. a tax return has wages, business income and total income for every year, all joint on a joint return). The model classifies the document first, then uses this list to check nothing is missed. This made Flash-Lite consistent on the 1040, so the cheaper model stays the default.
- `EXTRACTION_USER_PROMPT_TEMPLATE`: the task and `## Document ({page_count} pages, lines 1-{last_line_no})`.
- `build_system_prompt()`, `build_user_prompt(page_count, last_line_no)`.

`build_request` sends the user prompt, then per page: `### Page {n}` (marked when OCR), its lines as `[line_no] text`, and the page image. Images are left out if the model has `supports_image_input: false`.

## Extractor (`app/extraction/extractor.py`)

`extract(document, pages, model) -> DocumentExtraction`

- Up to 3 attempts. An attempt fails on an API error, output that fails validation, or a cited line number that doesn't exist in the document. The line check runs inside Pydantic validation (`CitationContext` as validation context), so it is recorded in `llm_calls` like any invalid output.
- After invalid output, the next attempt adds feedback to the request: each error's field path and message (no document values), and the valid line range. At temperature 0 the same request would get the same answer, so a plain retry can't fix invalid output. After an API error, the same request is resent.
- After a valid answer, `remove_ssn_like_accounts` drops account numbers shaped like an SSN (`ddd-dd-dddd`, also masked) and logs their field paths. Bare 9-digit numbers are kept: real account numbers look like that too.
- `ssn_last4` always keeps the last 4 digits only, even if the model returns a full or masked SSN.
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

`process_document`: parse → `extract` → save `documents.document_type` and the mentions → `done`.

## Costs CLI

`hatch run costs [batch_id=<id>]` prints, per model: calls, failed calls, input / cached / output tokens, and total cost in USD.

## PRs

| PR | Scope | Tests |
| --- | --- | --- |
| 1. LLM clients + tracking | `Pricing`, `Usage`, `LLMClient`, `GeminiClient`, `OpenAIClient`, Hydra model configs, `TrackedModel`, `llm_calls`, `hatch run costs` | Cost formula; a row per call, including failures; costs totals. Fake client, no network. |
| 2. Schema + extractor | Schema, `resolve`, request building, `extract` with 3 attempts, `ExtractionFailed`, `NonRetryableError`, `safe_error` | Valid output; unknown line number → retry; retry then success; 3 failures raise; `resolve` returns page, quote and boxes; `safe_error` never contains values |
| 3. Worker wiring | `borrower_mentions`, extraction in `process_document`, `safe_error` in the worker | Worker stores mentions; extraction failure fails at once. End to end on the corpus with both models (needs API keys). |
