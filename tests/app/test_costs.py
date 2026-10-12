from app.costs import HEADER, format_costs
from app.db import ModelCost


def test_format_costs_has_header_and_one_row_per_model():
    text = format_costs([ModelCost("gpt-4o-mini", 3, 1, 3000, 0, 600, 0.00081)])

    header, row = text.splitlines()
    assert header.split()[0] == HEADER[0]
    assert row.split() == ["gpt-4o-mini", "3", "1", "3000", "0", "600", "0.000810"]
