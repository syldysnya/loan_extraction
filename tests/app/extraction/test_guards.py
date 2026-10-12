import pytest

from app.extraction.guards import remove_ssn_like_accounts
from app.extraction.schema import Account, AccountKind, BorrowerMention, DocumentExtraction, DocumentType, SourceRef

REF = SourceRef(line_start=1, line_end=1)


def _extraction(*numbers: str, ssn_last4: str | None = None) -> DocumentExtraction:
    accounts = [Account(number=n, kind=AccountKind.BANK_ACCOUNT, source=REF) for n in numbers]
    mention = BorrowerMention(
        name="John", name_source=REF, ssn_last4=ssn_last4, ssn_source=REF, addresses=[], income=[], accounts=accounts
    )
    return DocumentExtraction(document_type=DocumentType.OTHER, borrowers=[mention])


def test_ssn_shaped_numbers_are_removed_and_reported():
    extraction = _extraction("999-40-5000", "123456789", "xxx-xx-5000", "2504EM060965")

    removed = remove_ssn_like_accounts(extraction)

    assert removed == ["borrowers.0.accounts.0", "borrowers.0.accounts.2"]
    assert [a.number for a in extraction.borrowers[0].accounts] == ["123456789", "2504EM060965"]


@pytest.mark.parametrize(
    ("given", "kept"),
    [("5000", "5000"), ("999-40-5000", "5000"), ("xxx-xx-5000", "5000"), ("50", None), (None, None)],
)
def test_ssn_last4_never_keeps_more_than_4_digits(given, kept):
    assert _extraction(ssn_last4=given).borrowers[0].ssn_last4 == kept
