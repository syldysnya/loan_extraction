from datetime import date

from app.extraction.income import mark_totals, remove_duplicate_income
from app.extraction.schema import (
    BorrowerMention,
    DocumentExtraction,
    DocumentType,
    IncomeBasis,
    IncomeEntry,
    IncomeKind,
    SourceRef,
)

REF = SourceRef(line_start=1, line_end=1)
Y2024 = (date(2024, 1, 1), date(2024, 12, 31))
Y2023 = (date(2023, 1, 1), date(2023, 12, 31))


def _income(amount: float, period: tuple[date, date], kind: IncomeKind = IncomeKind.WAGES) -> IncomeEntry:
    return IncomeEntry(
        amount=amount,
        kind=kind,
        basis=IncomeBasis.PERIOD,
        period_start=period[0],
        period_end=period[1],
        payer=None,
        joint=False,
        source=REF,
    )


def _extraction(*income: IncomeEntry) -> DocumentExtraction:
    mention = BorrowerMention(
        name="John", name_source=REF, ssn_last4=None, ssn_source=None, addresses=[], income=list(income), accounts=[]
    )
    return DocumentExtraction(document_type=DocumentType.OTHER, borrowers=[mention])


def _totals(extraction: DocumentExtraction) -> list[float]:
    return [i.amount for i in extraction.borrowers[0].income if i.kind == IncomeKind.TOTAL]


def test_1040_total_income_is_marked():
    # 1040 2024: wages 143,920 + Schedule C 28,341 = total income 172,261
    extraction = _extraction(
        _income(143_920, Y2024),
        _income(28_341, Y2024, IncomeKind.SELF_EMPLOYMENT),
        _income(172_261, Y2024, IncomeKind.OTHER),
    )

    assert mark_totals(extraction) == 1
    assert _totals(extraction) == [172_261]


def test_totals_are_per_period():
    # EVOE: base + other = total, for each year separately
    extraction = _extraction(
        _income(104_500, Y2024),
        _income(17_290, Y2024, IncomeKind.OTHER),
        _income(121_790, Y2024),
        _income(96_140, Y2023),
        _income(16_562, Y2023, IncomeKind.OTHER),
        _income(112_702, Y2023),
    )

    assert mark_totals(extraction) == 2
    assert _totals(extraction) == [121_790, 112_702]


def test_rounding_within_a_dollar_still_counts_as_total():
    extraction = _extraction(_income(100.40, Y2024), _income(200.40, Y2024), _income(300.00, Y2024))

    assert _totals_after(extraction) == [300.00]


def test_parts_without_a_total_are_left_alone():
    # Paystub: regular + commission, no stated total
    extraction = _extraction(_income(4_200, Y2024), _income(700, Y2024))

    assert mark_totals(extraction) == 0


def test_exact_duplicates_are_dropped_but_same_amount_in_another_period_is_kept():
    extraction = _extraction(_income(143_920, Y2024), _income(143_920, Y2024), _income(143_920, Y2023))

    assert remove_duplicate_income(extraction) == 1
    assert [(i.amount, i.period_start.year) for i in extraction.borrowers[0].income] == [
        (143_920, 2024),
        (143_920, 2023),
    ]


def _totals_after(extraction: DocumentExtraction) -> list[float]:
    mark_totals(extraction)
    return _totals(extraction)


def test_same_money_on_two_lines_with_different_kind_and_no_payer_is_one_figure():
    # 1040: Schedule C line 31 and Schedule 1 line 3 both show the business income
    schedule_c = _income(28_341, Y2024, IncomeKind.SELF_EMPLOYMENT).model_copy(update={"payer": "Disco LLC"})
    schedule_1 = _income(28_341, Y2024, IncomeKind.OTHER)
    extraction = _extraction(_income(143_920, Y2024), schedule_c, schedule_1, _income(172_261, Y2024))

    assert remove_duplicate_income(extraction) == 1
    assert mark_totals(extraction) == 1


def test_same_amount_from_different_payers_is_kept():
    extraction = _extraction(
        _income(50_000, Y2024).model_copy(update={"payer": "Employer A"}),
        _income(50_000, Y2024).model_copy(update={"payer": "Employer B"}),
    )

    assert remove_duplicate_income(extraction) == 0


def test_a_total_the_model_already_labelled_is_kept_and_not_counted_as_a_part():
    extraction = _extraction(
        _income(143_920, Y2024),
        _income(28_341, Y2024, IncomeKind.SELF_EMPLOYMENT),
        _income(172_261, Y2024, IncomeKind.TOTAL),
    )

    assert mark_totals(extraction) == 0  # nothing left for code to label
    assert _totals(extraction) == [172_261]
