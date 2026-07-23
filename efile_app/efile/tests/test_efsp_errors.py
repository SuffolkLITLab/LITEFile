"""Tests for turning an EFSP rejection into a message a filer can act on.

The body in ``WRONG_FILING_TYPE`` is the real one the fee endpoint returned for a
document saved with no filing type, which reached the filer as "Filing
submission failed: API returned status 400".
"""

import json

import pytest

from efile.services.efsp_errors import describe_efsp_error

WRONG_FILING_TYPE = {
    "required_vars": [],
    "optional_vars": [
        {
            "name": "efile_case_subtype",
            "description": "subtype (not always present)",
            "datatype": "text",
            "currentVal": "",
            "choices": [],
        }
    ],
    "wrong_vars": [
        {
            "name": "al_court_bundle.elements[0].filing_type",
            "description": "What filing type is this??",
            "datatype": "choice",
            "currentVal": "",
            "choices": ["60384", "60409", "123566"],
        }
    ],
}


class FakeResponse:
    """Enough of requests.Response for the describer."""

    def __init__(self, status_code, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise json.JSONDecodeError("Expecting value", self.text, 0)
        return self._body


def test_wrong_var_names_the_field_and_the_document():
    message = describe_efsp_error(FakeResponse(400, WRONG_FILING_TYPE))

    assert "filing type" in message
    assert "document 1" in message
    assert "400" not in message


def test_optional_vars_are_not_reported_as_problems():
    """The same body lists an empty optional field; saying so would only confuse."""
    assert "subtype" not in describe_efsp_error(FakeResponse(400, WRONG_FILING_TYPE))


def test_a_wrong_value_is_quoted_rather_than_called_missing():
    body = {"wrong_vars": [{"name": "al_court_bundle.elements[1].filing_type", "currentVal": "99999"}]}

    message = describe_efsp_error(FakeResponse(400, body))

    assert "99999" in message
    assert "document 2" in message


def test_required_var_is_reported_as_missing():
    message = describe_efsp_error(FakeResponse(400, {"required_vars": [{"name": "efile_case_type"}]}))

    assert "no case type was given" in message


def test_several_problems_are_all_reported():
    body = {
        "wrong_vars": [
            {"name": "al_court_bundle.elements[0].filing_type", "currentVal": ""},
            {"name": "al_court_bundle.elements[1].filing_component", "currentVal": ""},
        ]
    }

    message = describe_efsp_error(FakeResponse(400, body))

    assert "filing type" in message
    assert "filing component" in message


def test_unmapped_field_name_is_still_readable():
    message = describe_efsp_error(FakeResponse(400, {"required_vars": [{"name": "lead_contact"}]}))

    assert "lead contact" in message


def test_plain_error_message_is_passed_through():
    body = {"error": "All required parties not covered by existing party types."}

    assert describe_efsp_error(FakeResponse(400, body)) == body["error"]


def test_validation_errors_are_appended_to_a_plain_message():
    body = {"error": "Rejected", "validation_errors": ["bad bundle"]}

    message = describe_efsp_error(FakeResponse(400, body))

    assert "Rejected" in message
    assert "bad bundle" in message


def test_non_json_body_falls_back_to_the_status_and_text():
    message = describe_efsp_error(FakeResponse(502, text="<html>Bad Gateway</html>"))

    assert "502" in message
    assert "Bad Gateway" in message


def test_empty_body_reports_only_the_status():
    assert "503" in describe_efsp_error(FakeResponse(503, text=""))


def test_unrecognised_json_shape_reports_the_status():
    assert "418" in describe_efsp_error(FakeResponse(418, {"something": "else"}))


@pytest.mark.parametrize("body", [["a list"], "a string", 42])
def test_non_object_json_does_not_raise(body):
    assert describe_efsp_error(FakeResponse(400, body))


def test_nameless_var_is_ignored_rather_than_described_as_blank():
    """A var with no name says nothing; the status line is more useful."""
    message = describe_efsp_error(FakeResponse(400, {"wrong_vars": [{"currentVal": ""}]}))

    assert "400" in message
