from pydantic import BaseModel, ValidationError


class DocumentMessage(BaseModel):
    """Queue message body: one document to process."""

    document_id: str

    @classmethod
    def parse(cls, body: str) -> "DocumentMessage | None":
        """Return the message, or None if the body is malformed."""
        try:
            return cls.model_validate_json(body)
        except ValidationError:
            return None
