# Parsing: LLD

## Types (`app/parsing/`)

```python
class MimeType(StrEnum):
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"

@dataclass
class RawPage:            # parser output
    page_no: int
    text: str | None      # None when the page has no text layer
    image: bytes          # PNG

class Page(BaseModel):    # stored in documents.pages
    page_no: int
    text: str | None
    image_key: str        # s3 key of the page image

class Parser(ABC):
    mime_types: ClassVar[tuple[MimeType, ...]]
    def parse(self, data: bytes) -> list[RawPage]: ...

class UnsupportedFileType(Exception): ...
```

Parsers are pure (bytes in, pages out). They don't touch S3 or the DB.

## MIME detection

`detect_mime(data) -> MimeType` uses `filetype` (pure Python, reads the file's magic bytes). Unknown or unsupported types raise `UnsupportedFileType`.

## Registry

`get_parser(mime) -> Parser` looks the type up in a map built from each parser's `mime_types`. A new file type means one new `Parser` subclass added to that list.

## Parsers

| Parser | Types | Output |
| --- | --- | --- |
| `PdfParser` | PDF | One page per PDF page: text layer (`None` if empty) and the page rendered to PNG at `render_dpi` |
| `ImageParser` | PNG, JPEG | One page: `text = None`, image converted to PNG |

Both use PyMuPDF (text extraction and rendering in one library).

## Worker step

`process_document` now:

1. Reads the file from `s3/input/{batch_id}/{filename}`.
2. Detects the MIME type and picks the parser.
3. Writes each page image to `s3/pages/{document_id}/{page_no}.png`.
4. Saves `list[Page]` as JSON in `documents.pages`.

| Error | Action |
| --- | --- |
| `UnsupportedFileType` | Mark the document `failed`, delete the message, log it. A retry can't change the file type. |
| Any other error (e.g. a broken file) | Retry, then DLQ, as for any failure. |

A retry overwrites the same keys and column, so it's safe to repeat.

## Changes to existing code

- `LocalS3`: add `get(key) -> bytes`, and `page_key(document_id, page_no)`. `put` sends a file event only for `input/` keys.
- `documents`: add a `pages` column (JSON text, nullable).
- Worker: gets the S3 client too.
- Config: `parsing.render_dpi: 150`.
- Dependencies: `pymupdf`, `filetype`.

## PRs

| PR | Scope | Tests |
| --- | --- | --- |
| 1. Parser contract | `MimeType`, `RawPage`, `Page`, `Parser`, `UnsupportedFileType`, `detect_mime`, registry | Detection of PDF/PNG/JPEG bytes; unknown bytes raise; registry lookup |
| 2. Parsers | `PdfParser`, `ImageParser`, registered | Text page, image-only page, PNG output, page count |
| 3. Worker wiring | S3 `get` + `page_key`, `documents.pages`, parse step in `process_document`, unsupported type fails immediately | Worker parses and stores pages; unsupported type → `failed` with no retry; broken file goes to the DLQ; end to end on the corpus (Title Report pages have `text = None`) |
