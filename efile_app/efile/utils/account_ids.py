"""Stable local identifiers for jurisdiction-specific Tyler accounts."""

import hashlib


def jurisdiction_account_username(external_username: str, jurisdiction: str) -> str:
    """Return a non-sensitive, globally unique Django username for a Tyler account."""

    normalized_username = external_username.strip().casefold()
    normalized_jurisdiction = jurisdiction.strip().casefold()
    digest = hashlib.sha256(normalized_username.encode()).hexdigest()
    return f"{normalized_jurisdiction}:{digest}"
