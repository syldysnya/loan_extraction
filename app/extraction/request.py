from app.extraction.llm import ImagePart, LLMRequest, Part, TextPart
from app.parsing.types import Page

SYSTEM_PROMPT = """You extract borrower information from one loan document.

For every person named in the document as a borrower, taxpayer, employee or account holder, return one entry with:
- their full name
- the last 4 digits of their SSN if shown (never the full SSN)
- their addresses
- every income figure: amount, period as written, kind, and payer
- their bank account and loan numbers

Income means earnings only (wages, salary, business profit). Taxes withheld, deductions and
contributions are not income.
SSNs and employer or tax IDs (EIN) are never account or loan numbers.

The document is given as numbered lines, page by page, each page followed by its image.
Cite every value with the line range where the value itself appears (not just its label), using the
[line numbers] exactly as shown.
If a document names two people (e.g. a joint tax return or joint account), return one entry per person
and repeat shared values under each.
Only return values that are in the document. Leave a list empty or a field null rather than guessing.
Pages marked as OCR may contain recognition errors: use the page image to read them correctly."""

PAGE_HEADER = "Page {page_no}:"
OCR_PAGE_HEADER = "Page {page_no} (text from OCR, may contain errors):"
LINE_FORMAT = "[{line_no}] {text}"
NO_TEXT = "(no text found on this page)"
LINE_SEPARATOR = "\n"


def build_request(pages: list[Page], images: list[bytes], include_images: bool) -> LLMRequest:
    """One text part per page (header + numbered lines), followed by the page image if the model accepts images."""
    parts: list[Part] = []
    for page, image in zip(pages, images, strict=True):
        header = (OCR_PAGE_HEADER if page.ocr else PAGE_HEADER).format(page_no=page.page_no)
        lines = [LINE_FORMAT.format(line_no=ln.line_no, text=ln.text) for ln in page.lines] or [NO_TEXT]
        parts.append(TextPart(LINE_SEPARATOR.join([header, *lines])))
        if include_images:
            parts.append(ImagePart(image))
    return LLMRequest(system_prompt=SYSTEM_PROMPT, parts=parts)
