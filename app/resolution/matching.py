import hashlib
import re

LAST_FIRST_SEPARATOR = ","
NOT_A_LETTER = re.compile(r"[^a-z\s]")
ID_LENGTH = 16


def person_key(name: str) -> str:
    """Normalize a name so spellings of the same person match.

    Lowercase, no punctuation, no single-letter tokens (middle initials), and "Last, First" as "First Last":
    "JOHN A. HOMEOWNER" and "Homeowner, John" both give "john homeowner".
    """
    if LAST_FIRST_SEPARATOR in name:
        last, first = name.split(LAST_FIRST_SEPARATOR, 1)
        name = f"{first} {last}"
    tokens = NOT_A_LETTER.sub(" ", name.lower()).split()
    return " ".join(t for t in tokens if len(t) > 1)


def borrower_id(key: str) -> str:
    """Stable ID: the same person keeps the same ID across rebuilds."""
    return hashlib.sha256(key.encode()).hexdigest()[:ID_LENGTH]
