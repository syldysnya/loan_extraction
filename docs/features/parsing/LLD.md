# Parsing: LLD

## Types (`app/parsing/types.py`)

```python
class MimeType(StrEnum):
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"

class BBox(BaseModel):    # normalized 0–1 of the page
    left: float
    top: float
    width: float
    height: float

class Line(BaseModel):
    line_no: int          # 1-based, unique across the whole document
    text: str
    bbox: BBox

@dataclass
class RawPage:            # parser output
    page_no: int
    lines: list[Line]     # empty if the page has no text at all
    ocr: bool             # True if the lines came from OCR
    image: bytes          # PNG

class Page(BaseModel):    # stored in documents.pages
    page_no: int
    lines: list[Line]
    ocr: bool
    image_key: str        # s3 key of the page image

class Parser(ABC):
    mime_types: ClassVar[tuple[MimeType, ...]]
    def parse(self, data: bytes) -> list[RawPage]: ...

class UnsupportedFileType(Exception): ...
```

Parsers are pure (bytes in, pages out). They don't touch S3 or the DB. A parser numbers lines across all its pages: page 2's first line continues after page 1's last.

## MIME detection

`detect_mime(data) -> MimeType` uses `filetype` (pure Python, reads the file's magic bytes). Unknown or unsupported types raise `UnsupportedFileType`.

## Registry

`ParserRegistry.get(mime) -> Parser` looks the type up in a map built from each parser's `mime_types`. A new file type means one new `Parser` subclass added in `build_registry`.

## Parsers

| Parser | Types | Lines from | Image |
| --- | --- | --- | --- |
| `PdfParser` | PDF | PyMuPDF native lines (`get_text("dict")`: blocks → lines, box = union of the line's spans). A page with no text lines goes to OCR. | Page rendered to PNG at `render_dpi` |
| `ImageParser` | PNG, JPEG | OCR | Image converted to PNG |

## OCR (`app/parsing/ocr.py`)

```python
class Ocr(ABC):
    def read(self, image: bytes) -> list[OcrLine]: ...   # OcrLine: text, bbox

class TesseractOcr(Ocr): ...
```

- `TesseractOcr` uses `pytesseract.image_to_data`, groups words by Tesseract's block/paragraph/line numbers, joins their text, and takes the union of their boxes. Boxes are normalized by the image size. Empty words are skipped.
- `PdfParser` renders a page for OCR at `ocr_dpi` (higher than `render_dpi`, since Tesseract is more accurate at 300 DPI).
- Requires the Tesseract binary: `brew install tesseract`.

## Worker step

`process_document`:

1. Reads the file from `s3/input/{batch_id}/{filename}`.
2. Detects the MIME type and picks the parser.
3. Writes each page image to `s3/pages/{document_id}/{page_no}.png`.
4. Saves `list[Page]` as JSON in `documents.pages`.

| Error | Action |
| --- | --- |
| `UnsupportedFileType` | Mark the document `failed`, delete the message, log it. A retry can't change the file type. |
| Any other error (e.g. a broken file) | Retry, then DLQ, as for any failure. |

A retry overwrites the same keys and column, so it's safe to repeat.

## Config (`conf/parsing/default.yaml`)

```yaml
_target_: app.parsing.registry.build_registry
render_dpi: 150
ocr_dpi: 300
```

## PRs

| PR | Scope | Tests |
| --- | --- | --- |
| 1. Parser contract ✅ | `MimeType`, `RawPage`, `Page`, `Parser`, `UnsupportedFileType`, `detect_mime`, registry | Detection of PDF/PNG/JPEG bytes; unknown bytes raise; registry lookup |
| 2. Parsers ✅ | `PdfParser`, `ImageParser`, registered | Text page, image-only page, PNG output, page count |
| 3. Worker wiring ✅ | S3 `get` + `page_key`, `documents.pages`, parse step in `process_document`, unsupported type fails immediately | Worker parses and stores pages; unsupported type → `failed`; broken file → DLQ; end to end on the corpus |
| 4. Lines, boxes and OCR | `BBox`, `Line`, lines replace `text`; `PdfParser` native lines; `Ocr` + `TesseractOcr`; OCR for pages with no text and for images; `ocr_dpi` | Line numbers continue across pages; boxes within 0–1; OCR reads a rendered text image; blank PDF page goes to OCR. End to end: every Title Report page has OCR lines. |
