from pydantic import BaseModel, ValidationError

from app.errors import safe_error
from app.parsing.types import UnsupportedFileType


class Income(BaseModel):
    amount: float


def test_validation_error_keeps_field_path_not_value():
    try:
        Income.model_validate({"amount": "John Homeowner"})
    except ValidationError as e:
        message = safe_error(e)

    assert message == "ValidationError: amount (float_parsing)"


def test_non_retryable_error_keeps_its_safe_message():
    assert safe_error(UnsupportedFileType("unknown file type")) == "UnsupportedFileType: unknown file type"


def test_other_errors_only_keep_the_type():
    assert safe_error(RuntimeError("secret value John Homeowner")) == "RuntimeError"
