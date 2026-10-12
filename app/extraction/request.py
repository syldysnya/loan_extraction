from app.extraction.llm import ImagePart, LLMRequest, Part, TextPart
from app.extraction.prompts import (
    LINE_TEMPLATE,
    NO_TEXT,
    OCR_PAGE_HEADER_TEMPLATE,
    PAGE_HEADER_TEMPLATE,
    build_system_prompt,
    build_user_prompt,
)
from app.parsing.types import Page

LINE_SEPARATOR = "\n"


def build_request(pages: list[Page], images: list[bytes], include_images: bool) -> LLMRequest:
    """User prompt, then per page: its numbered lines and its image (if the model accepts images)."""
    last_line_no = max((line.line_no for page in pages for line in page.lines), default=0)
    parts: list[Part] = [TextPart(build_user_prompt(page_count=len(pages), last_line_no=last_line_no))]
    for page, image in zip(pages, images, strict=True):
        parts.append(TextPart(_page_text(page)))
        if include_images:
            parts.append(ImagePart(image))
    return LLMRequest(system_prompt=build_system_prompt(), parts=parts)


def _page_text(page: Page) -> str:
    header = (OCR_PAGE_HEADER_TEMPLATE if page.ocr else PAGE_HEADER_TEMPLATE).format(page_no=page.page_no)
    lines = [LINE_TEMPLATE.format(line_no=ln.line_no, text=ln.text) for ln in page.lines] or [NO_TEXT]
    return LINE_SEPARATOR.join([header, *lines])
