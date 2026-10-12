import pytest

from app.parsing.registry import ParserRegistry
from app.parsing.types import MimeType, Parser, RawPage, UnsupportedFileType


class FakeImageParser(Parser):
    mime_types = (MimeType.PNG, MimeType.JPEG)

    def parse(self, data: bytes) -> list[RawPage]:
        return [RawPage(page_no=1, text=None, image=data)]


def test_returns_parser_for_each_of_its_types():
    parser = FakeImageParser()
    registry = ParserRegistry([parser])

    assert registry.get(MimeType.PNG) is parser
    assert registry.get(MimeType.JPEG) is parser


def test_unregistered_type_raises():
    with pytest.raises(UnsupportedFileType):
        ParserRegistry([FakeImageParser()]).get(MimeType.PDF)


def test_two_parsers_for_one_type_raises():
    with pytest.raises(ValueError):
        ParserRegistry([FakeImageParser(), FakeImageParser()])
