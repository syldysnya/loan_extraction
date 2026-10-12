import re
from collections import Counter, defaultdict
from datetime import date

from app.extraction.schema import AddressKind, BorrowerMention, IncomeBasis, IncomeEntry, SourceRef
from app.resolution.conflicts import find_conflicts
from app.resolution.matching import borrower_id, person_key
from app.resolution.record import (
    BorrowerRecord,
    DocumentMentions,
    RecordAccount,
    RecordAddress,
    RecordIncome,
    Source,
    SourcedValue,
)

NOT_ALNUM = re.compile(r"[^A-Za-z0-9]")
NOT_WORD = re.compile(r"[^a-z0-9\s]")
YEAR_START = (1, 1)
YEAR_END = (12, 31)

Cited = tuple[DocumentMentions, BorrowerMention]


def build_records(docs: list[DocumentMentions]) -> list[BorrowerRecord]:
    """One record per person across all documents. Mentions with the same normalized name are one person."""
    people: dict[str, list[Cited]] = defaultdict(list)
    for dm in docs:
        for stored in dm.mentions:
            key = person_key(stored.mention.name)
            if key:
                people[key].append((dm, stored.mention))
    return [_build(key, cited) for key, cited in sorted(people.items())]


def mention_borrower_ids(docs: list[DocumentMentions]) -> dict[str, str]:
    """mention id -> borrower id, for linking `borrower_mentions` rows to their records."""
    return {
        stored.id: borrower_id(person_key(stored.mention.name))
        for dm in docs
        for stored in dm.mentions
        if person_key(stored.mention.name)
    }


def _build(key: str, cited: list[Cited]) -> BorrowerRecord:
    ssn: dict[str, list[Source]] = defaultdict(list)
    addresses: dict[tuple[AddressKind, str], RecordAddress] = {}
    accounts: dict[str, RecordAccount] = {}
    income: list[RecordIncome] = []

    for dm, m in cited:
        if m.ssn_last4:
            ssn[m.ssn_last4].append(_source(dm, m.ssn_source or m.name_source))  # no SSN citation: the person's
        for a in m.addresses:
            address_key = (a.kind, _normalize_text(a.value))
            if address_key not in addresses:
                addresses[address_key] = RecordAddress(value=a.value, kind=a.kind, sources=[])
            addresses[address_key].sources.append(_source(dm, a.source))
        for acc in m.accounts:
            number = NOT_ALNUM.sub("", acc.number).upper()
            if number not in accounts:
                accounts[number] = RecordAccount(number=acc.number, kind=acc.kind, sources=[])
            accounts[number].sources.append(_source(dm, acc.source))
        for entry in m.income:
            _add_income(income, _as_full_year(entry), _source(dm, entry.source))

    ssn_values = [SourcedValue(value=v, sources=s) for v, s in ssn.items()]
    income.sort(key=lambda i: (i.period_start, i.kind, i.amount))
    return BorrowerRecord(
        id=borrower_id(key),
        name=Counter(m.name for _, m in cited).most_common(1)[0][0],
        name_sources=[_source(dm, m.name_source) for dm, m in cited],
        ssn_last4=ssn_values,
        residence_addresses=[a for a in addresses.values() if a.kind == AddressKind.RESIDENCE],
        property_addresses=[a for a in addresses.values() if a.kind == AddressKind.PROPERTY],
        accounts=list(accounts.values()),
        income=income,
        conflicts=find_conflicts(ssn_values, income),
    )


def _source(dm: DocumentMentions, ref: SourceRef) -> Source:
    evidence = dm.lines.resolve(ref)
    return Source(
        document_id=dm.document.id,
        filename=dm.document.filename,
        document_type=dm.document.document_type,
        page_nos=evidence.page_nos,
        quote=evidence.quote,
    )


def _as_full_year(entry: IncomeEntry) -> IncomeEntry:
    """A year-to-date figure covering Jan 1 to Dec 31 of one year is that year's figure."""
    start, end = entry.period_start, entry.period_end
    full_year = start == date(start.year, *YEAR_START) and end == date(start.year, *YEAR_END)
    if entry.basis == IncomeBasis.YEAR_TO_DATE and full_year:
        return entry.model_copy(update={"basis": IncomeBasis.PERIOD})
    return entry


def _add_income(income: list[RecordIncome], entry: IncomeEntry, source: Source) -> None:
    """Merge into an existing figure if it's the same money (the payer may be missing on one side)."""
    for existing in income:
        payers_agree = existing.payer is None or entry.payer is None or existing.payer == entry.payer
        if payers_agree and (
            existing.amount,
            existing.kind,
            existing.basis,
            existing.period_start,
            existing.period_end,
            existing.joint,
        ) == (entry.amount, entry.kind, entry.basis, entry.period_start, entry.period_end, entry.joint):
            existing.sources.append(source)
            existing.payer = existing.payer or entry.payer
            return
    income.append(
        RecordIncome(
            amount=entry.amount,
            kind=entry.kind,
            basis=entry.basis,
            period_start=entry.period_start,
            period_end=entry.period_end,
            payer=entry.payer,
            joint=entry.joint,
            sources=[source],
        )
    )


def _normalize_text(text: str) -> str:
    return " ".join(NOT_WORD.sub(" ", text.lower()).split())
