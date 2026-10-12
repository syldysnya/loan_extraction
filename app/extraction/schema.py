import re
from dataclasses import dataclass
from datetime import date
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


class DocumentType(StrEnum):
    TAX_RETURN = "tax_return"
    W2 = "w2"
    PAYSTUB = "paystub"
    EMPLOYMENT_VERIFICATION = "employment_verification"
    BANK_STATEMENT = "bank_statement"
    CLOSING_DISCLOSURE = "closing_disclosure"
    TITLE_REPORT = "title_report"
    UNDERWRITING_SUMMARY = "underwriting_summary"
    LETTER_OF_EXPLANATION = "letter_of_explanation"
    OTHER = "other"


class IncomeKind(StrEnum):
    WAGES = "wages"
    SELF_EMPLOYMENT = "self_employment"
    OTHER = "other"
    TOTAL = "total"  # the sum of other figures, as stated on the document


class IncomeBasis(StrEnum):
    PERIOD = "period"
    YEAR_TO_DATE = "year_to_date"


class AccountKind(StrEnum):
    BANK_ACCOUNT = "bank_account"
    LOAN = "loan"


class AddressKind(StrEnum):
    RESIDENCE = "residence"
    PROPERTY = "property"


class Address(BaseModel):
    value: str = Field(description="Full address as written.")
    kind: AddressKind = Field(
        description="residence: the person's current home or mailing address. "
        "property: the property being bought, refinanced or insured (the loan's subject property)."
    )
    source: SourceRef


class IncomeEntry(BaseModel):
    amount: float = Field(description="Gross earnings in USD, as a number. Not taxes withheld or deductions.")
    kind: IncomeKind = Field(
        description="wages: W-2, paystub, employment verification. self_employment: Schedule C. "
        "total: a figure the document states as the sum of other income figures (e.g. 1040 line 9)."
    )
    basis: IncomeBasis = Field(
        description="period: earned within exactly period_start..period_end. "
        "year_to_date: a running total from January 1 up to period_end (e.g. a paystub's YTD column)."
    )
    period_start: date = Field(description="First day the amount covers. A tax year 2024 starts 2024-01-01.")
    period_end: date = Field(description="Last day the amount covers. A tax year 2024 ends 2024-12-31.")
    payer: str | None = Field(description="Employer or business name, if shown.")
    joint: bool = Field(
        description="True if the figure belongs to several people together (e.g. wages on a joint tax return), "
        "false if it is this person's alone."
    )
    source: SourceRef

    @model_validator(mode="after")
    def period_in_order(self) -> "IncomeEntry":
        if self.period_start > self.period_end:
            raise ValueError("period_start is after period_end")
        return self


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
    # First, so the model decides what the document is before extracting from it.
    document_type: DocumentType = Field(description="What kind of document this is. See the Document Types section.")
    borrowers: list[BorrowerMention]
