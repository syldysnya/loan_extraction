from pydantic import ValidationError

PATH_SEPARATOR = "."


class NonRetryableError(Exception):
    """A failure a retry can't fix: the worker fails the document at once.

    Messages must never contain document data, since they are stored and logged.
    """


def validation_errors(e: ValidationError) -> list[tuple[str, str]]:
    """(field path, message) per error. Pydantic keeps the invalid input separately, so messages hold no values."""
    return [(PATH_SEPARATOR.join(str(p) for p in err["loc"]), err["msg"]) for err in e.errors()]


def safe_error(e: BaseException) -> str:
    """Describe an error for `documents.error` and logs, without any values from the document.

    Validation errors would otherwise echo the invalid (extracted) values, so only field paths are kept.
    """
    name = type(e).__name__
    if isinstance(e, ValidationError):
        fields = ", ".join(f"{PATH_SEPARATOR.join(str(p) for p in err['loc'])} ({err['type']})" for err in e.errors())
        return f"{name}: {fields}"
    if isinstance(e, NonRetryableError):
        return f"{name}: {e}"
    return name
