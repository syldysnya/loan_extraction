from app.extraction.evidence import LineIndex
from app.extraction.schema import SourceRef
from app.parsing.types import BBox, Line, Page

BOX = BBox(left=0.1, top=0.2, width=0.3, height=0.05)


def _page(page_no: int, *lines: tuple[int, str]) -> Page:
    return Page(
        page_no=page_no,
        lines=[Line(line_no=n, text=t, bbox=BOX) for n, t in lines],
        ocr=False,
        image_key=f"pages/doc/{page_no}.png",
    )


PAGES = [_page(1, (1, "Name: John"), (2, "SSN: xxx-xx-5000")), _page(2, (3, "Account: 123"))]


def test_resolve_quote_and_locations_across_pages():
    evidence = LineIndex(PAGES).resolve(SourceRef(line_start=2, line_end=3))

    assert evidence.quote == "SSN: xxx-xx-5000\nAccount: 123"
    assert evidence.page_nos == [1, 2]
    assert [loc.bbox for loc in evidence.locations] == [BOX, BOX]


def test_last_line_no():
    assert LineIndex(PAGES).last_line_no == 3
    assert LineIndex([]).last_line_no == 0
