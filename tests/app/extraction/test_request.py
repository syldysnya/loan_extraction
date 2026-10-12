from app.extraction.llm import ImagePart, TextPart
from app.extraction.request import NO_TEXT, SYSTEM_PROMPT, build_request
from app.parsing.types import BBox, Line, Page

BOX = BBox(left=0, top=0, width=1, height=0.1)
PAGES = [
    Page(page_no=1, lines=[Line(line_no=1, text="W-2 2024", bbox=BOX)], ocr=False, image_key="p1"),
    Page(page_no=2, lines=[], ocr=True, image_key="p2"),
]


def test_numbered_lines_then_image_per_page():
    request = build_request(PAGES, [b"img1", b"img2"], include_images=True)

    assert request.system_prompt == SYSTEM_PROMPT
    text1, image1, text2, image2 = request.parts
    assert isinstance(text1, TextPart) and text1.text == "Page 1:\n[1] W-2 2024"
    assert isinstance(image1, ImagePart) and image1.png == b"img1"
    assert isinstance(text2, TextPart) and "OCR" in text2.text and NO_TEXT in text2.text
    assert isinstance(image2, ImagePart)


def test_images_left_out_when_model_has_no_image_input():
    request = build_request(PAGES, [b"img1", b"img2"], include_images=False)

    assert all(isinstance(p, TextPart) for p in request.parts)
