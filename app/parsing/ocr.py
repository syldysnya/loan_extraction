import io
from abc import ABC, abstractmethod
from collections import defaultdict

import pytesseract
from PIL import Image

from app.parsing.types import BBox, TextLine

# Keys of pytesseract.image_to_data's dict output.
_TEXT = "text"
_LEFT = "left"
_TOP = "top"
_WIDTH = "width"
_HEIGHT = "height"
_BLOCK = "block_num"
_PARAGRAPH = "par_num"
_LINE = "line_num"


class Ocr(ABC):
    @abstractmethod
    def read(self, image: bytes) -> list[TextLine]:
        """Read text lines, top to bottom, with boxes normalized to the image size."""


class TesseractOcr(Ocr):
    def read(self, image: bytes) -> list[TextLine]:
        img = Image.open(io.BytesIO(image))
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        # Tesseract reports words; group them into its lines (block, paragraph, line).
        words_by_line: dict[tuple[int, int, int], list[int]] = defaultdict(list)
        for i, text in enumerate(data[_TEXT]):
            if text.strip():
                words_by_line[(data[_BLOCK][i], data[_PARAGRAPH][i], data[_LINE][i])].append(i)

        lines = []
        for word_indexes in words_by_line.values():
            boxes = [
                BBox(
                    left=data[_LEFT][i] / img.width,
                    top=data[_TOP][i] / img.height,
                    width=data[_WIDTH][i] / img.width,
                    height=data[_HEIGHT][i] / img.height,
                )
                for i in word_indexes
            ]
            text = " ".join(data[_TEXT][i].strip() for i in word_indexes)
            lines.append(TextLine(text=text, bbox=BBox.union(boxes)))
        return lines
