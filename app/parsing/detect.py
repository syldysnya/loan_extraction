import filetype

from app.parsing.types import MimeType, UnsupportedFileType


def detect_mime(data: bytes) -> MimeType:
    """Detect the MIME type from the file's magic bytes, not its name."""
    kind = filetype.guess(data)
    if kind is None:
        raise UnsupportedFileType("unknown file type")
    try:
        return MimeType(kind.mime)
    except ValueError:
        raise UnsupportedFileType(f"unsupported file type: {kind.mime}") from None
