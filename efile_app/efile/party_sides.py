"""The sides of a case, as a document itself establishes them.

A *side* is what an uploaded document can tell us about a person named on it:
they started the case, they are answering it, or the caption names them for
some other reason. There are only these three, they mean the same thing in
every state, and they are readable on the first extraction pass -- before the
filer has confirmed a court or a case type.

A *party type* is the other thing entirely: one code out of the list a given
court publishes for a given case type ("Plaintiff", "Petitioner/Wife",
"Guardian Ad Litem"), fetched live and different from court to court. Sides
map onto party types once the case type is known; see
``efile.services.people.apply_party_sides``.

This module holds only the vocabulary so that both ``efile.models`` and the
services that fill these fields in can import it.
"""

from enum import StrEnum


class PartySide(StrEnum):
    INITIATING = "initiating"
    RESPONDING = "responding"
    OTHER = "other"


# Deliberately says both words for each side: courts split about evenly on
# which one they use, and a filer should recognize whichever their own
# document printed.
PARTY_SIDE_LABELS: dict[str, str] = {
    PartySide.INITIATING: "Plaintiff or petitioner",
    PartySide.RESPONDING: "Defendant or respondent",
    PartySide.OTHER: "Someone else named in the case",
}

PARTY_SIDE_HELP: dict[str, str] = {
    PartySide.INITIATING: "The person or organization asking the court for something",
    PartySide.RESPONDING: "The person or organization being asked to respond",
    PartySide.OTHER: "A child, a guardian, or anyone else the case names",
}

PARTY_SIDE_CHOICES: tuple[tuple[str, str], ...] = tuple((side.value, PARTY_SIDE_LABELS[side]) for side in PartySide)

# Words that identify a side in a court's own party-type names. Matched
# against the names the court publishes, never against Tyler codes, which
# differ per court.
PARTY_SIDE_KEYWORDS: dict[str, tuple[str, ...]] = {
    PartySide.INITIATING: ("plaintiff", "petitioner", "complainant"),
    PartySide.RESPONDING: ("defendant", "respondent"),
    PartySide.OTHER: (),
}


def side_for_party_type_name(name: str) -> str:
    """Read a side back out of a court party-type name, or "" if it has none.

    Used for parties that were given a court party type before they were ever
    given a side -- a required-party placeholder, or a draft started before
    sides were recorded at all.
    """

    lowered = str(name or "").lower()
    for side, keywords in PARTY_SIDE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return str(side)
    return ""
