import pytest

from efile.utils.django_helpers import flush_cache_stay_logged_in

pytestmark = pytest.mark.django_db


def test_clearing_filing_state_preserves_authentication(client):
    session = client.session
    authentication = {
        "auth_tokens": {"TYLER-TOKEN-ILLINOIS": "token"},
        "user_email": "filer@example.com",
        "_auth_user_id": "42",
        "_auth_user_backend": "efile.authentication.SuffolkEFileBackend",
        "_auth_user_hash": "hash",
    }
    filing_state = {
        "case_data": {"court": "old"},
        "upload_data": {"files": []},
        "session_id": "old-session",
        "existing_case": "new",
        "filing_draft_id": 12,
        "last_submitted_filing_draft_id": 11,
        "jurisdiction": "illinois",
    }
    session.update(authentication | filing_state)
    original_session_key = session.session_key

    flush_cache_stay_logged_in(session)

    assert session.session_key == original_session_key
    assert {key: session[key] for key in authentication} == authentication
    assert not filing_state.keys() & session.keys()
