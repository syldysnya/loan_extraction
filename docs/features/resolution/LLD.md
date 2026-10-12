# Resolution: LLD

## Record (`app/resolution/record.py`)

What resolution builds for each person. Every value carries all of its sources.

```python
class Source(BaseModel):
    document_id: str
    filename: str
    document_type: DocumentType | None
    page_nos: list[int]
    quote: str                    # the cited lines' text (from parsing, never from the LLM)

class SourcedValue(BaseModel):
    value: str
    sources: list[Source]

class RecordAddress(BaseModel):
    value: str
    kind: AddressKind
    sources: list[Source]

class RecordAccount(BaseModel):
    number: str
    kind: AccountKind
    sources: list[Source]

class RecordIncome(BaseModel):
    amount: float
    kind: IncomeKind
    basis: IncomeBasis
    period_start: date
    period_end: date
    payer: str | None
    joint: bool
    sources: list[Source]

class ConflictField(StrEnum):
    SSN_LAST4 = "ssn_last4"
    INCOME = "income"

class Conflict(BaseModel):
    field: ConflictField
    key: str                      # what was compared, e.g. "wages, ABC Technologies, 2024-01-01..2024-12-31, period"
    values: list[SourcedValue]    # the different values, each with its sources

class BorrowerRecord(BaseModel):
    id: str
    name: str
    name_sources: list[Source]
    ssn_last4: list[SourcedValue] # usually one; more than one is also a conflict
    residence_addresses: list[RecordAddress]
    property_addresses: list[RecordAddress]
    accounts: list[RecordAccount]
    income: list[RecordIncome]    # sorted by period_start, then kind
    conflicts: list[Conflict]
```

## Matching (`app/resolution/matching.py`)

`person_key(name) -> str`: lowercase, drop punctuation, drop single-letter tokens (middle initials), and turn "Last, First" into "First Last". "JOHN A. HOMEOWNER" and "Homeowner, John" both give `john homeowner`.

Mentions with the same key are one person. Account numbers and SSN last 4 are not used to match (see HLD).

`borrower_id = sha256(person_key)[:16]`: the same person keeps the same ID across rebuilds, so API links stay valid.

Only mentions from documents with status `done` are used: a document that failed on a re-run may still hold mentions from an earlier run.

## Merging (`app/resolution/merge.py`)

Within one person, values that are the same are merged into one entry with all their sources:

| Value | Same if |
| --- | --- |
| Name (display) | The most common spelling across mentions |
| SSN last 4 | Same 4 digits |
| Address | Same kind and same text after lowercasing and dropping punctuation and extra spaces |
| Account | Same number, keeping only letters and digits |
| Income | Same amount, kind, basis, period and joint flag, and the payers match or one is missing (as in extraction's duplicate check) |

Before merging, a `year_to_date` income covering Jan 1 to Dec 31 of one year becomes `period`: it is that year's figure.

No income is summed across documents.

## Conflicts (`app/resolution/conflicts.py`)

| Field | Conflict when |
| --- | --- |
| `ssn_last4` | A person has more than one value |
| `income` | Two figures share kind, payer, basis and period but have different amounts |

Each conflict lists every value with its sources. It is logged as `borrower {id}: {field}` only: no values.

## Run (`app/resolution/resolve.py`)

`resolve_all(conn) -> ResolutionResult` (borrowers, conflicts):

1. Load mentions of `done` documents, with their documents and pages (to resolve sources).
2. Group by `person_key`, merge, find conflicts.
3. In one transaction: delete all `borrowers` rows, insert the new ones, set `borrower_mentions.borrower_id`.

The rebuild is idempotent: the same mentions always give the same records and IDs.

## Trigger

- **Worker:** after a document ends as `done` or `failed` (including through the DLQ), if its batch has no `queued` or `processing` documents left, it calls `resolve_all`.
- **Command:** `hatch run resolve` runs it on demand, e.g. after a redrive or a re-extraction.
- An error in resolution is logged with `safe_error` and doesn't fail any document. Run the command again after fixing it.

## Storage: `borrowers`

| Column | Type |
| --- | --- |
| `id` | text, primary key (`sha256(person_key)[:16]`) |
| `name` | text |
| `record` | JSON (`BorrowerRecord`) |
| `conflict_count` | int |
| `updated_at` | text |

## PRs

| PR | Scope | Tests |
| --- | --- | --- |
| 1. Record, matching, merging, conflicts | `record.py`, `matching.py`, `merge.py`, `conflicts.py`: pure functions from mentions to records | Name keys (case, initials, "Last, First"); the corpus cases: VanAssens separate from the Homeowners, John and Mary separate despite shared accounts, Mary's two SSN values kept and flagged, the same income from two documents merged with both sources, full-year YTD shown as the year, W-2 wages vs EVOE base pay not a conflict |
| 2. Storage, trigger, command | `borrowers` table, `resolve_all`, worker trigger, `hatch run resolve` | Rebuild is idempotent; batch completion triggers resolution; failed documents' mentions ignored; end to end on the corpus |
