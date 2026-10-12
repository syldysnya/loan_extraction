import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, ValidationInfo, model_validator

SSN_LAST4_DIGITS = 4
NON_DIGIT = re.compile(r"\D")


@dataclass
class CitationContext:
    """Passed as Pydantic validation context, so citations are checked against the document's lines."""

    last_line_no: int


class SourceRef(BaseModel):
    line_start: int = Field(description="First line of the evidence, using the [line number] shown in the document.")
    line_end: int = Field(description="Last line of the evidence (same as line_start for a single line).")

    @model_validator(mode="after")
    def lines_exist(self, info: ValidationInfo) -> "SourceRef":
        ctx = info.context
        if isinstance(ctx, CitationContext) and not 1 <= self.line_start <= self.line_end <= ctx.last_line_no:
            raise ValueError("cited lines are not in the document")
        return self


def _keep_last4_only(value: str | None) -> str | None:
    """Never keep more than the last 4 digits, even if the model returns a full or masked SSN."""
    digits = NON_DIGIT.sub("", value or "")
    return digits[-SSN_LAST4_DIGITS:] if len(digits) >= SSN_LAST4_DIGITS else None


SsnLast4 = Annotated[str | None, AfterValidator(_keep_last4_only)]


class IncomeKind(StrEnum):
    WAGES = "wages"
    SELF_EMPLOYMENT = "self_employment"
    OTHER = "other"


class AccountKind(StrEnum):
    BANK_ACCOUNT = "bank_account"
    LOAN = "loan"


class Address(BaseModel):
    value: str = Field(description="Full address as written.")
    source: SourceRef


class IncomeEntry(BaseModel):
    amount: float = Field(description="Earnings in USD, as a number. Not taxes withheld or deductions.")
    period: str = Field(description="Period as written, e.g. '2024' or '04/12/25 - 04/25/25'.")
    kind: IncomeKind = Field(description="wages: W-2, paystub, employment verification. self_employment: Schedule C.")
    payer: str | None = Field(description="Employer or business name, if shown.")
    source: SourceRef


class Account(BaseModel):
    number: str = Field(description="Bank account or loan number exactly as written. Never an SSN or tax ID.")
    kind: AccountKind
    source: SourceRef


class BorrowerMention(BaseModel):
    name: str = Field(description="Full name of the person.")
    name_source: SourceRef
    ssn_last4: SsnLast4 = Field(description="Last 4 digits of the SSN if shown. Never the full SSN.")
    addresses: list[Address]
    income: list[IncomeEntry]
    accounts: list[Account]

    def refs(self) -> list[SourceRef]:
        return [
            self.name_source,
            *(a.source for a in self.addresses),
            *(i.source for i in self.income),
            *(a.source for a in self.accounts),
        ]


class DocumentExtraction(BaseModel):
    borrowers: list[BorrowerMention]
