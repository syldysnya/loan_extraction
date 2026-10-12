from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from app.db import Document, StoredMention
from app.extraction.evidence import LineIndex
from app.extraction.schema import AccountKind, AddressKind, DocumentType, IncomeBasis, IncomeKind


class Source(BaseModel):
    document_id: str
    filename: str
    document_type: DocumentType | None
    page_nos: list[int]
    quote: str  # the cited lines' text (from parsing, never from the LLM)


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
    key: str  # what was compared, e.g. "wages, ABC Technologies, 2024-01-01..2024-12-31, period, w2"
    values: list[SourcedValue]  # the different values, each with its sources


class BorrowerRecord(BaseModel):
    id: str
    name: str
    name_sources: list[Source]
    ssn_last4: list[SourcedValue]  # usually one; more than one is also a conflict
    residence_addresses: list[RecordAddress]
    property_addresses: list[RecordAddress]
    accounts: list[RecordAccount]
    income: list[RecordIncome]  # sorted by period_start, then kind
    conflicts: list[Conflict]


@dataclass
class DocumentMentions:
    """One document's mentions, with what's needed to turn citations into sources."""

    document: Document
    lines: LineIndex
    mentions: list[StoredMention]
