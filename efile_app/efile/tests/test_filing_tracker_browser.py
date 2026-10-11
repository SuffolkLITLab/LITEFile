"""End-to-end checks for the filing status detail screen with synthetic court data."""

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from django.test import RequestFactory

from efile.models import FilingDraft
from efile.services.submission_notifications import submission_email_fields
from efile.tests.test_filing_history import accepted_detail, rejected_detail
from efile.utils.config_loader import config_loader


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_filing_tracker_browser(live_server, client, django_user_model):
    app = Path(__file__).resolve().parents[2]
    if not shutil.which("node") or not (app / "node_modules/@playwright/test").exists():
        pytest.skip("Install the browser test dependencies to run the filing tracker browser check.")

    user = django_user_model.objects.create_user(
        username="tracker-browser", email="tracker@example.test", tyler_jurisdiction="illinois"
    )

    accepted = accepted_detail()
    accepted["filingLeadDocument"][0]["documentRendition"][0]["documentRenditionMetadata"]["documentAttachment"][1][
        "binaryLocationURI"
    ]["value"] = "https://example.test/stamped.pdf"
    returned = rejected_detail()
    failed = copy.deepcopy(accepted)
    failed["filingStatus"] = {"filingStatusCode": "failed", "statusDescriptionText": []}
    payloads = {"accepted-1": accepted, "returned-1": returned, "failed-1": failed}
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        court_code="kane",
        status=FilingDraft.Status.SUBMITTED,
        submission_response={"filing_ids": list(payloads)},
    )

    # Exercise proxy-owned notification rendering in test configuration only.
    # This builds synthetic email text and never delivers it to an email service.
    host = urlsplit(live_server.url).netloc
    email_request = RequestFactory().get("/", HTTP_HOST=host)
    notification_config = copy.deepcopy(config_loader.load_jurisdiction_config("illinois"))
    notification_config["submission_notifications"]["enabled"] = True
    email_fields = submission_email_fields(email_request, draft, "illinois", notification_config)
    email_contents = email_fields["email_confirmation_contents"]
    assert f"/submissions/{draft.public_id}/" in email_contents

    fetched_filing_ids = []

    def monkeypatch_payloads(_request, _jurisdiction, _court, filing_id):
        fetched_filing_ids.append(filing_id)
        return copy.deepcopy(payloads[filing_id])

    def synthetic_auth(request, username, password, jurisdiction):
        assert username == user.email
        assert password == "synthetic-password"
        assert jurisdiction == "illinois"
        request.session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "synthetic-token"}
        user.backend = "efile.authentication.SuffolkEFileBackend"
        return user

    with (
        patch("efile.views.my_cases.fetch_filing_detail", side_effect=monkeypatch_payloads),
        patch("efile.views.my_cases.court_names", return_value={"kane": "Kane County"}),
        patch("efile.services.filings.list_filing_data", return_value=[]),
        patch("efile.views.login.authenticate", side_effect=synthetic_auth),
        patch("requests.post") as post,
    ):
        config = {"base": live_server.url, "emailContents": email_contents}
        result = subprocess.run(
            ["node", str(app / "tests/filing-tracker-browser.js")],
            env={**os.environ, "FILING_TRACKER_BROWSER_CONFIG": json.dumps(config)},
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        post.assert_not_called()

    assert result.returncode == 0, result.stdout + result.stderr
    assert fetched_filing_ids == ["returned-1", "accepted-1", "returned-1", "failed-1", "accepted-1"]
