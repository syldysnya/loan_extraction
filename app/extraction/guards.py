import re

from app.extraction.schema import DocumentExtraction

# The SSN's dashed shape, also masked (e.g. xxx-xx-5000). Bare 9-digit numbers are not matched:
# real account numbers look like that too (e.g. checking 123456789).
SSN_SHAPE = re.compile(r"^[\dXx*]{3}-[\dXx*]{2}-\d{4}$")
ACCOUNT_PATH = "borrowers.{b}.accounts.{a}"


def remove_ssn_like_accounts(extraction: DocumentExtraction) -> list[str]:
    """Drop account numbers shaped like an SSN, so a full SSN is never stored. Returns the removed paths."""
    removed = []
    for b, mention in enumerate(extraction.borrowers):
        kept = []
        for a, account in enumerate(mention.accounts):
            if SSN_SHAPE.match(account.number.strip()):
                removed.append(ACCOUNT_PATH.format(b=b, a=a))
            else:
                kept.append(account)
        mention.accounts = kept
    return removed
