# Parsing: HLD

## Purpose

Turn any supported file into pages of text and images, so later steps never deal with file types.

## Flow

```mermaid
flowchart LR
    worker["Document worker"] -- "file bytes" --> detect["Detect MIME type"]
    detect --> registry{"registry[mime]"}
    registry --> pdf["PdfParser"]
    registry --> img["ImageParser"]
    pdf --> pages["pages: [{page_no, text | null, image_key}]"]
    img --> pages
    pages -- "text" --> db[("SQLite<br/>documents.pages")]
    pages -- "images" --> s3[("s3/pages/{document_id}/{page_no}.png")]
    s3 --> extract["Extraction"]
```

## Decisions

| Decision | Reason |
| --- | --- |
| Parser registry keyed by MIME type | A new file type is one new parser class. |
| One page shape for every file type | Extraction stays the same for PDFs, scans and images. |
| MIME type detected from bytes, not the extension | File names can't be trusted. |
| `text = null` when a page has no text layer | The scanned Title Report is read from its image. |
| Page images saved to local S3 | Easy to inspect what the LLM saw; parse and extract can be split later. |
| Unsupported or broken file raises an error | It retries, then goes to the DLQ like any failure. |
