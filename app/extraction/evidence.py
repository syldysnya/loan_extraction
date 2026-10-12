from dataclasses import dataclass

from app.extraction.schema import SourceRef
from app.parsing.types import BBox, Line, Page

LINE_SEPARATOR = "\n"


@dataclass
class Location:
    page_no: int
    bbox: BBox


@dataclass
class Evidence:
    """What a citation points to, looked up from the document itself."""

    quote: str
    locations: list[Location]  # one per cited line

    @property
    def page_nos(self) -> list[int]:
        return sorted({loc.page_no for loc in self.locations})


class LineIndex:
    """Finds lines by their document-wide number."""

    def __init__(self, pages: list[Page]):
        self._lines: dict[int, tuple[int, Line]] = {
            line.line_no: (page.page_no, line) for page in pages for line in page.lines
        }

    @property
    def last_line_no(self) -> int:
        return max(self._lines, default=0)

    def resolve(self, ref: SourceRef) -> Evidence:
        cited = [self._lines[n] for n in range(ref.line_start, ref.line_end + 1)]
        return Evidence(
            quote=LINE_SEPARATOR.join(line.text for _, line in cited),
            locations=[Location(page_no, line.bbox) for page_no, line in cited],
        )
