from django.contrib.auth import logout

from efile.utils.jurisdiction_stuff import get_jurisdiction_from_request


class JurisdictionSessionMiddleware:
    """End an authenticated session before it can cross a jurisdiction boundary."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        jurisdiction = get_jurisdiction_from_request(request)
        user = getattr(request, "user", None)
        account_jurisdiction = getattr(user, "tyler_jurisdiction", "")
        if (
            jurisdiction
            and getattr(user, "is_authenticated", False)
            and account_jurisdiction
            and account_jurisdiction.casefold() != jurisdiction.casefold()
        ):
            logout(request)

        return self.get_response(request)


class NoCacheHTMLMiddleware:
    """Stop browsers from reusing a stale rendered page without asking the server first.

    Django's views send no Cache-Control at all, which leaves the browser free to
    apply its own heuristic freshness and serve an old page byte-for-byte on a plain
    reload -- no request even reaches the server. That's the same failure mode
    WHITENOISE_MAX_AGE=0 (settings_dev.py) fixes for static JS/CSS, but it was still
    open for the HTML itself: a template change (e.g. a <select> replaced with radio
    inputs) could sit invisible until the user did a hard refresh.

    Runs after WhiteNoise in MIDDLEWARE, so it never touches the responses WhiteNoise
    already serves (and already marks with its own Cache-Control) -- only the actual
    Django view responses, which is exactly what has no header set today. These pages
    also carry per-session case data, so not caching them is correct beyond just
    dev convenience.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "Cache-Control" not in response:
            response["Cache-Control"] = "no-store"
        return response
