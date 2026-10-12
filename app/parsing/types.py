from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel


class MimeType(StrEnum):
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"


class UnsupportedFileType(Exception):
    pass


class BBox(BaseModel):
    """A box normalized to 0–1 of the page size."""

    left: float
    top: float
    width: float
    height: float

    @classmethod
    def union(cls, boxes: list["BBox"]) -> "BBox":
        left = min(b.left for b in boxes)
        top = min(b.top for b in boxes)
        right = max(b.left + b.width for b in boxes)
        bottom = max(b.top + b.height for b in boxes)
        return cls(left=left, top=top, width=right - left, height=bottom - top)


@dataclass
class TextLine:
    """A line read from a page, before it gets its document-wide number."""

    text: str
    bbox: BBox


class Line(BaseModel):
    line_no: int  # 1-based, unique across the whole document
    text: str
    bbox: BBox


@dataclass
class RawPage:
    """A page as returned by a parser."""

    page_no: int
    lines: list[Line]  # empty if the page has no text at all
    ocr: bool  # True if the lines came from OCR
    image: bytes  # PNG


class Page(BaseModel):
    """A page as stored in `documents.pages`."""

    page_no: int
    lines: list[Line]
    ocr: bool
    image_key: str  # S3 key of the page image


class LineNumbering:
    """Numbers lines across all pages of a document: page 2 continues after page 1."""

    def __init__(self) -> None:
        self._next = 1

    def number(self, text_lines: list[TextLine]) -> list[Line]:
        lines = [Line(line_no=self._next + i, text=t.text, bbox=t.bbox) for i, t in enumerate(text_lines)]
        self._next += len(lines)
        return lines


class Parser(ABC):
    """Turns file bytes into pages. Pure: no S3 or DB access."""

    mime_types: ClassVar[tuple[MimeType, ...]]

    @abstractmethod
    def parse(self, data: bytes) -> list[RawPage]: ...
