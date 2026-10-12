from app.parsing.parsers import ImageParser, PdfParser
from app.parsing.types import MimeType, Parser, UnsupportedFileType


class ParserRegistry:
    """Maps each MIME type to the parser that handles it."""

    def __init__(self, parsers: list[Parser]):
        self._by_mime: dict[MimeType, Parser] = {}
        for parser in parsers:
            for mime in parser.mime_types:
                if mime in self._by_mime:
                    raise ValueError(f"two parsers registered for {mime}")
                self._by_mime[mime] = parser

    def get(self, mime: MimeType) -> Parser:
        parser = self._by_mime.get(mime)
        if parser is None:
            raise UnsupportedFileType(f"no parser for {mime}")
        return parser


# A new file type is one new Parser added here.
REGISTRY = ParserRegistry([PdfParser(), ImageParser()])
