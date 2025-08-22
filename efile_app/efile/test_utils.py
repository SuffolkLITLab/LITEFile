# Test utilities and fixtures for the efile application

import json
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client


class MockResponse:
    """Mock response object for testing API calls."""

    def __init__(self, json_data, status_code=200, ok=True):
        self.json_data = json_data
        self.status_code = status_code
        self.ok = ok

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if not self.ok:
            raise Exception(f"HTTP {self.status_code}")


@pytest.fixture
def mock_court_api_response():
    """Mock response for Suffolk LIT Lab courts API."""
    return MockResponse(
        {
            "courts": [
                {
                    "id": "cook:law1",
                    "name": "Cook County Circuit Court - Law Division",
                    "jurisdiction": "illinois",
                    "address": "50 W Washington St, Chicago, IL 60602",
                },
                {
                    "id": "cook:dr1",
                    "name": "Cook County Circuit Court - Domestic Relations",
                    "jurisdiction": "illinois",
                    "address": "50 W Washington St, Chicago, IL 60602",
                },
                {
                    "id": "cook:pr1",
                    "name": "Cook County Circuit Court - Probate",
                    "jurisdiction": "illinois",
                    "address": "50 W Washington St, Chicago, IL 60602",
                },
                {
                    "id": "will:law1",
                    "name": "Will County Circuit Court - Law Division",
                    "jurisdiction": "illinois",
                    "address": "14 W Jefferson St, Joliet, IL 60432",
                },
            ]
        }
    )


@pytest.fixture
def mock_case_categories_response():
    """Mock response for case categories API."""
    return MockResponse(
        {
            "case_categories": [
                {"id": "civil", "text": "Civil Law"},
                {"id": "family", "text": "Family Law"},
                {"id": "probate", "text": "Probate"},
                {"id": "misc", "text": "Miscellaneous"},
            ]
        }
    )


@pytest.fixture
def mock_case_types_response():
    """Mock response for case types API."""
    return MockResponse(
        {
            "case_types": [
                {"id": "divorce", "name": "Divorce"},
                {"id": "custody", "name": "Child Custody"},
                {"id": "support", "name": "Child Support"},
                {"id": "contract", "name": "Contract Dispute"},
                {"id": "tort", "name": "Personal Injury"},
            ]
        }
    )


@pytest.fixture
def authenticated_user(db):
    """Create and return an authenticated user."""
    user = User.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123", first_name="Test", last_name="User"
    )
    return user


@pytest.fixture
def api_client():
    """Create a Django test client with proper headers for API requests."""
    client = Client()
    client.defaults["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
    client.defaults["HTTP_CONTENT_TYPE"] = "application/json"
    return client


@pytest.fixture
def authenticated_api_client(api_client, authenticated_user):
    """Create an authenticated API client."""
    api_client.force_login(authenticated_user)
    return api_client


class APITestMixin:
    """Mixin class providing common API testing utilities."""

    def assert_api_success(self, response, expected_data_length=None):
        """Assert that an API response indicates success."""
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "data" in data

        if expected_data_length is not None:
            assert len(data["data"]) == expected_data_length

        return data

    def assert_api_error(self, response, expected_error_message=None):
        """Assert that an API response indicates an error."""
        assert response.status_code == 200  # Our APIs return 200 with error flags
        data = json.loads(response.content)
        assert data["success"] is False
        assert "error" in data

        if expected_error_message:
            assert expected_error_message.lower() in data["error"].lower()

        return data

    def mock_external_api(self, api_response):
        """Context manager for mocking external API calls."""
        return patch("requests.get", return_value=api_response)


@pytest.fixture
def api_test_mixin():
    """Provide APITestMixin for test classes."""
    return APITestMixin()


# Sample test data for consistent testing
SAMPLE_ZIP_CODES = {
    "cook_county": ["60601", "60614", "60611", "60612"],
    "will_county": ["60432", "60403", "60435"],
    "dupage_county": ["60515", "60516", "60521"],
}

SAMPLE_COURT_CODES = {
    "cook_law": "cook:law1",
    "cook_family": "cook:dr1",
    "cook_probate": "cook:pr1",
    "will_law": "will:law1",
}

SAMPLE_CASE_CATEGORIES = [
    {"id": "civil", "text": "Civil Law"},
    {"id": "family", "text": "Family Law"},
    {"id": "probate", "text": "Probate"},
    {"id": "criminal", "text": "Criminal"},
]


def create_mock_form_data(**kwargs):
    """Create mock form data for testing form submissions."""
    default_data = {
        "court": "cook:law1",
        "case_category": "civil",
        "case_type": "contract",
        "filing_type": "complaint",
        "document_type": "motion",
        "petitioner_first_name": "John",
        "petitioner_last_name": "Doe",
        "new_first_name": "Jane",
        "new_last_name": "Smith",
    }
    default_data.update(kwargs)
    return default_data


def create_mock_user_profile(**kwargs):
    """Create mock user profile data for testing."""
    default_profile = {
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "zip_code": "60601",
        "preferred_county": "Cook",
        "state": "IL",
    }
    default_profile.update(kwargs)
    return default_profile
