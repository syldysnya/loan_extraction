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


@dataclass
class RawPage:
    """A page as returned by a parser."""

    page_no: int
    text: str | None  # None when the page has no text layer
    image: bytes  # PNG


class Page(BaseModel):
    """A page as stored in `documents.pages`."""

    page_no: int
    text: str | None
    image_key: str  # S3 key of the page image


class Parser(ABC):
    """Turns file bytes into pages. Pure: no S3 or DB access."""

    mime_types: ClassVar[tuple[MimeType, ...]]

    @abstractmethod
    def parse(self, data: bytes) -> list[RawPage]: ...
