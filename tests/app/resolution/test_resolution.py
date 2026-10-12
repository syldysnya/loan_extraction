from datetime import date

import pytest

from app.db import Document, DocumentStatus, StoredMention
from app.extraction.evidence import LineIndex
from app.extraction.schema import (
    Account,
    AccountKind,
    Address,
    AddressKind,
    BorrowerMention,
    DocumentType,
    IncomeBasis,
    IncomeEntry,
    IncomeKind,
    SourceRef,
)
from app.parsing.types import BBox, Line, Page
from app.resolution.matching import borrower_id, person_key
from app.resolution.merge import build_records, mention_borrower_ids
from app.resolution.record import BorrowerRecord, ConflictField, DocumentMentions

REF = SourceRef(line_start=1, line_end=1)
BOX = BBox(left=0, top=0, width=1, height=0.1)
Y2024 = (date(2024, 1, 1), date(2024, 12, 31))
CHECKING = Account(number="123456789", kind=AccountKind.BANK_ACCOUNT, source=REF)


def _doc(doc_id: str, document_type: DocumentType, *mentions: BorrowerMention) -> DocumentMentions:
    document = Document(doc_id, "batch", f"{doc_id}.pdf", doc_id, DocumentStatus.DONE, None, document_type)
    page = Page(page_no=1, lines=[Line(line_no=1, text=f"{doc_id} line", bbox=BOX)], ocr=False, image_key="p")
    stored = [StoredMention(f"{doc_id}-{i}", doc_id, m, None) for i, m in enumerate(mentions)]
    return DocumentMentions(document=document, lines=LineIndex([page]), mentions=stored)


def _person(name: str, ssn: str | None = None, **values: list) -> BorrowerMention:
    return BorrowerMention(
        name=name,
        name_source=REF,
        ssn_last4=ssn,
        ssn_source=REF if ssn else None,
        addresses=values.get("addresses", []),
        income=values.get("income", []),
        accounts=values.get("accounts", []),
    )


def _wages(amount: float, payer: str | None = "ABC Technologies", basis: IncomeBasis = IncomeBasis.PERIOD):
    return IncomeEntry(
        amount=amount,
        kind=IncomeKind.WAGES,
        basis=basis,
        period_start=Y2024[0],
        period_end=Y2024[1],
        payer=payer,
        joint=False,
        source=REF,
    )


def _by_name(records: list[BorrowerRecord]) -> dict[str, BorrowerRecord]:
    return {r.name: r for r in records}


@pytest.mark.parametrize("name", ["John Homeowner", "JOHN A. HOMEOWNER", "Homeowner, John", " john  homeowner "])
def test_spellings_of_one_name_share_a_key(name):
    assert person_key(name) == "john homeowner"


def test_households_and_spouses_stay_separate_even_with_shared_accounts():
    docs = [
        _doc(
            "checking",
            DocumentType.BANK_STATEMENT,
            _person("John Homeowner", accounts=[CHECKING]),
            _person("Mary Homeowner", accounts=[CHECKING]),
        ),
        _doc("title", DocumentType.TITLE_REPORT, _person("Robert VanAssen"), _person("Andrea VanAssen")),
    ]

    records = _by_name(build_records(docs))

    assert set(records) == {"John Homeowner", "Mary Homeowner", "Robert VanAssen", "Andrea VanAssen"}
    assert records["John Homeowner"].accounts[0].number == records["Mary Homeowner"].accounts[0].number


def test_conflicting_ssn_values_are_kept_and_flagged():
    docs = [
        _doc("1040", DocumentType.TAX_RETURN, _person("Mary Homeowner", ssn="2000")),
        _doc("1008", DocumentType.UNDERWRITING_SUMMARY, _person("Mary Homeowner", ssn="2222")),
    ]

    [mary] = build_records(docs)

    assert sorted(v.value for v in mary.ssn_last4) == ["2000", "2222"]
    [conflict] = mary.conflicts
    assert conflict.field == ConflictField.SSN_LAST4
    assert {s.document_id for v in conflict.values for s in v.sources} == {"1040", "1008"}


def test_same_figure_from_two_documents_is_listed_once_with_both_sources():
    docs = [
        _doc("w2", DocumentType.W2, _person("John Homeowner", income=[_wages(117_040.19)])),
        _doc("1008", DocumentType.UNDERWRITING_SUMMARY, _person("John Homeowner", income=[_wages(117_040.19, None)])),
    ]

    [john] = build_records(docs)

    [wages] = john.income
    assert wages.payer == "ABC Technologies"
    assert [s.document_id for s in wages.sources] == ["w2", "1008"]


def test_full_year_year_to_date_is_that_years_figure():
    docs = [
        _doc("w2", DocumentType.W2, _person("John Homeowner", income=[_wages(121_790.00)])),
        _doc(
            "evoe",
            DocumentType.EMPLOYMENT_VERIFICATION,
            _person("John Homeowner", income=[_wages(121_790.00, basis=IncomeBasis.YEAR_TO_DATE)]),
        ),
    ]

    [john] = build_records(docs)

    [wages] = john.income
    assert wages.basis == IncomeBasis.PERIOD and len(wages.sources) == 2


def test_different_document_types_are_not_compared_but_the_same_type_is():
    w2_vs_evoe = [
        _doc("w2", DocumentType.W2, _person("John Homeowner", income=[_wages(117_040.19)])),
        _doc("evoe", DocumentType.EMPLOYMENT_VERIFICATION, _person("John Homeowner", income=[_wages(104_500.00)])),
    ]
    two_w2s = [
        _doc("w2a", DocumentType.W2, _person("John Homeowner", income=[_wages(117_040.19)])),
        _doc("w2b", DocumentType.W2, _person("John Homeowner", income=[_wages(117_400.19)])),
    ]

    assert build_records(w2_vs_evoe)[0].conflicts == []
    [conflict] = build_records(two_w2s)[0].conflicts
    assert conflict.field == ConflictField.INCOME
    assert [v.value for v in conflict.values] == ["117,040.19", "117,400.19"]


def test_residence_and_property_addresses_are_kept_apart():
    home = Address(value="175 13th Street, Washington, DC 20013", kind=AddressKind.RESIDENCE, source=REF)
    same_home = Address(value="175 13th street washington DC 20013", kind=AddressKind.RESIDENCE, source=REF)
    bought = Address(value="999 Test Place, Washington, DC 20013", kind=AddressKind.PROPERTY, source=REF)
    docs = [
        _doc("w2", DocumentType.W2, _person("John Homeowner", addresses=[home])),
        _doc("cd", DocumentType.CLOSING_DISCLOSURE, _person("John Homeowner", addresses=[same_home, bought])),
    ]

    [john] = build_records(docs)

    assert [len(a.sources) for a in john.residence_addresses] == [2]
    assert [a.value for a in john.property_addresses] == ["999 Test Place, Washington, DC 20013"]


def test_ids_are_stable_and_mentions_link_to_their_record():
    docs = [_doc("w2", DocumentType.W2, _person("John Homeowner"))]

    [john] = build_records(docs)

    assert john.id == borrower_id("john homeowner") == build_records(docs)[0].id
    assert mention_borrower_ids(docs) == {"w2-0": john.id}


def test_sources_carry_the_document_and_cited_text():
    [john] = build_records([_doc("w2", DocumentType.W2, _person("John Homeowner"))])

    [source] = john.name_sources
    assert (source.document_id, source.filename, source.document_type) == ("w2", "w2.pdf", DocumentType.W2)
    assert (source.page_nos, source.quote) == ([1], "w2 line")
