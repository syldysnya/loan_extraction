"""Deterministic clean-up of extracted income: the model is not fully reliable at it."""

from collections import defaultdict
from datetime import date

from app.extraction.schema import DocumentExtraction, IncomeEntry, IncomeKind

# Amounts on documents are rounded to cents or dollars; a stated total may differ from its parts by rounding.
TOTAL_TOLERANCE_USD = 1.0
MIN_PARTS_FOR_TOTAL = 2  # a "total" of one part is just a duplicate


def remove_duplicate_income(extraction: DocumentExtraction) -> int:
    """Drop figures a document repeats, returning how many were dropped.

    A figure repeats an earlier one for the same person when amount, basis, period and joint flag match, and the
    payers match or one is missing. Documents often show the same money twice (e.g. Schedule C line 31 and
    Schedule 1 line 3 on a 1040), sometimes with a different kind or no payer.
    """
    dropped = 0
    for mention in extraction.borrowers:
        kept: list[IncomeEntry] = []
        for entry in mention.income:
            if any(_same_figure(entry, k) for k in kept):
                dropped += 1
            else:
                kept.append(entry)
        mention.income = kept
    return dropped


def _same_figure(a: IncomeEntry, b: IncomeEntry) -> bool:
    payers_agree = a.payer is None or b.payer is None or a.payer == b.payer
    return (
        a.amount == b.amount
        and a.basis == b.basis
        and a.period_start == b.period_start
        and a.period_end == b.period_end
        and a.joint == b.joint
        and payers_agree
    )


def mark_totals(extraction: DocumentExtraction) -> int:
    """Set kind `total` on figures equal to the sum of a person's other figures for the same period.

    A safety net for totals the model didn't label: it is asked to use `total` itself. Returns how many it set.
    """
    marked = 0
    for mention in extraction.borrowers:
        by_period: dict[tuple[date, date], list[IncomeEntry]] = defaultdict(list)
        for entry in mention.income:
            by_period[(entry.period_start, entry.period_end)].append(entry)
        for entries in by_period.values():
            # Largest first: a total is never smaller than its parts.
            for candidate in sorted(entries, key=lambda e: e.amount, reverse=True):
                if candidate.kind == IncomeKind.TOTAL:
                    continue
                parts = [e for e in entries if e is not candidate and e.kind != IncomeKind.TOTAL]
                if len(parts) >= MIN_PARTS_FOR_TOTAL and abs(candidate.amount - sum(p.amount for p in parts)) <= (
                    TOTAL_TOLERANCE_USD
                ):
                    candidate.kind = IncomeKind.TOTAL
                    marked += 1
    return marked
