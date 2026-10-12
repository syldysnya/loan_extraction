from collections import defaultdict

from app.extraction.schema import DocumentType
from app.resolution.record import Conflict, ConflictField, RecordIncome, Source, SourcedValue

KEY_SEPARATOR = ", "
NO_PAYER = "-"
AMOUNT_FORMAT = "{:,.2f}"


def find_conflicts(ssn_last4: list[SourcedValue], income: list[RecordIncome]) -> list[Conflict]:
    """Disagreements across a person's documents. Flagged with every value and its sources, never resolved."""
    conflicts = []
    if len(ssn_last4) > 1:
        conflicts.append(Conflict(field=ConflictField.SSN_LAST4, key=ConflictField.SSN_LAST4, values=ssn_last4))
    conflicts.extend(_income_conflicts(income))
    return conflicts


def _income_conflicts(income: list[RecordIncome]) -> list[Conflict]:
    """Different amounts for the same kind, payer, basis and period, from the same type of document.

    Different document types can measure different things under the same kind (e.g. W-2 box 1 wages vs an
    employment verification's base pay), so they are not compared.
    """
    amounts: dict[str, dict[float, list[Source]]] = defaultdict(lambda: defaultdict(list))
    for figure in income:
        for source in figure.sources:
            amounts[_income_key(figure, source.document_type)][figure.amount].append(source)
    return [
        Conflict(
            field=ConflictField.INCOME,
            key=key,
            values=[SourcedValue(value=AMOUNT_FORMAT.format(a), sources=s) for a, s in sorted(by_amount.items())],
        )
        for key, by_amount in amounts.items()
        if len(by_amount) > 1
    ]


def _income_key(figure: RecordIncome, document_type: DocumentType | None) -> str:
    parts = [
        figure.kind,
        figure.payer or NO_PAYER,
        f"{figure.period_start}..{figure.period_end}",
        figure.basis,
        document_type or NO_PAYER,
    ]
    return KEY_SEPARATOR.join(parts)
