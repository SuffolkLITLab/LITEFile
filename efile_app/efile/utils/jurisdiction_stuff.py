def get_jurisdiction_from_request(request):
    jurisdiction = request.GET.get("jurisdiction")
    if jurisdiction:
        return jurisdiction.lower()

    segments = request.path.split("/")
    if len(segments) >= 3 and segments[1] == "jurisdiction":
        return segments[2].lower()

    return None
