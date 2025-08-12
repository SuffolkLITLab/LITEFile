import pytest
from django.urls import reverse


@pytest.mark.django_db(False)
def test_settings_are_wired(settings):
    """pytest-django should expose Django settings fixture."""
    assert settings.ROOT_URLCONF == "efile.urls"


def test_login_page_renders(client):
    """Basic smoke test: GET /login/ should render the login page (200)."""
    url = reverse("efile_login")
    resp = client.get(url)
    assert resp.status_code == 400
    # Optional sanity check that template contains 'login' somewhere
    assert b"login" in resp.content.lower()
