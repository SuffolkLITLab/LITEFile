def get_jurisdiction_from_request(request):
    jurisdiction = request.GET.get("jurisdiction")
    if jurisdiction:
        return jurisdiction.lower()

    segments = request.path.split("/")
    # TODO(brycew): okay, maybe it makes sense to add an extra segment to the path...
    if len(segments) >= 2 and segments[1] not in ["api", "options", "login", "register", "upload", "review"]:
        return segments[1].lower()

    return None
