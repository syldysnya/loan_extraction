import pytest

from app.parsing.detect import detect_mime
from app.parsing.types import MimeType, UnsupportedFileType

# Minimal headers ("magic bytes") for each type.
PDF = b"%PDF-1.7\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
ZIP = b"PK\x03\x04" + b"\x00" * 26


@pytest.mark.parametrize(("data", "mime"), [(PDF, MimeType.PDF), (PNG, MimeType.PNG), (JPEG, MimeType.JPEG)])
def test_detects_supported_types(data, mime):
    assert detect_mime(data) == mime


@pytest.mark.parametrize("data", [b"plain text", ZIP])
def test_unknown_or_unsupported_raises(data):
    with pytest.raises(UnsupportedFileType):
        detect_mime(data)
