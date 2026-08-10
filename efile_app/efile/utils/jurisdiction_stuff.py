def get_jurisdiction_from_request(request):
    jurisdiction = request.GET.get("jurisdiction")
    if jurisdiction:
        return jurisdiction.lower()

    segments = request.path.split("/")
    if len(segments) >= 3 and segments[1] == "jurisdiction":
        return segments[2].lower()

    return request.session.get("jurisdiction")


def get_jurisdiction_token(request, jurisdiction):
    """Return the Tyler token for exactly one jurisdiction, if this session has it."""

    if not jurisdiction:
        return None
    auth_tokens = request.session.get("auth_tokens", {})
    return (
        auth_tokens.get(f"TYLER-TOKEN-{jurisdiction.upper()}")
        or auth_tokens.get(f"tyler_token_{jurisdiction}")
        or auth_tokens.get(f"tyler-token-{jurisdiction}")
    )


def has_jurisdiction_login(request, jurisdiction):
    """Whether the active Django and Tyler identities both belong to ``jurisdiction``."""

    user = getattr(request, "user", None)
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "tyler_jurisdiction", "").casefold() == jurisdiction.casefold()
        and get_jurisdiction_token(request, jurisdiction)
    )
