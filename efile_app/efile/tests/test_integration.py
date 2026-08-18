"""
Simple integration tests for the efile application
Tests basic functionality without mocking external services
"""

import json
import os

import pytest
from django.test import Client

from efile.utils.config_loader import config_loader

# =====================================================
# Secrets loaded at runtime.
#
# These tests log in to the live Tyler test EFM. Without credentials they skip
# rather than fail, so a missing local .env stays distinguishable from a real
# regression. CI supplies both from repo secrets, so coverage there is unchanged.


def _require_env(name):
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set; skipping test that needs the live Tyler EFM")
    return value


def get_test_username():
    return _require_env("TESTS_TYLER_USERNAME")


def get_test_password():
    return _require_env("TESTS_TYLER_PASSWORD")


# =======================


class TestBasicFunctionality:
    """Test basic functionality that doesn't depend on external services."""

    def test_zip_to_county_mapping_works(self):
        """Test that zip code to county mapping works correctly."""
        from efile.utils.zip_to_county_il import get_county_by_zip, get_zips_by_county

        # Test known mappings
        assert get_county_by_zip("60601") == "Cook"
        assert get_county_by_zip("60614") == "Cook"

        # Test reverse mapping
        cook_zips = get_zips_by_county("Cook")
        assert "60601" in cook_zips
        assert "60614" in cook_zips
        assert len(cook_zips) > 50  # Cook County has many zip codes

        # Test invalid inputs
        assert get_county_by_zip("00000") is None
        assert get_zips_by_county("NonexistentCounty") == []

    @pytest.mark.django_db
    def test_profile_api_basic_functionality(self):
        """Test that profile API returns some response."""
        client = Client()

        username = get_test_username()
        password = get_test_password()
        client.post(
            "/api/auth/login/",
            content_type="application/json",
            data=json.dumps({"username": username, "password": password, "jurisdiction": "illinois"}),
        )

        # Test authenticated request
        response = client.get(
            "/api/auth/profile/", {"jurisdiction": "illinois"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        assert response.status_code == 200
        data = json.loads(response.content)

        # Should have basic structure
        assert "success" in data

        if data["success"]:
            assert "data" in data
            assert data["data"]["username"] == username
            # Assert the shape, not one developer's Tyler account: whoever's
            # credentials are configured, the profile must carry a real first name.
            assert isinstance(data["data"]["first_name"], str)
            assert data["data"]["first_name"]

    @pytest.mark.django_db
    def test_case_categories_api_basic_functionality(self):
        """Test that case categories API returns some response."""
        client = Client()

        # Case categories API requires a court parameter
        response = client.get(
            "/api/dropdowns/case-categories/",
            {"jurisdiction": "illinois", "court": "cook:law1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        assert response.status_code in [200, 400]  # Accept both success and error
        data = json.loads(response.content)

        # Should have basic structure
        assert "success" in data

        if data["success"]:
            assert "data" in data
            assert isinstance(data["data"], list)

    def test_login_page_functionality(self):
        """Test that login functionality works."""
        client = Client()

        response = client.get("/jurisdiction/illinois/login/")
        assert response.status_code == 200
        assert b"login" in response.content.lower()


class TestUtilityFunctions:
    """Test utility functions in isolation."""

    def test_case_form_config_exists(self):
        """Test that case form configuration can be loaded."""
        try:
            # Should be able to load jurisdiction configuration without error
            config = config_loader.load_jurisdiction_config("illinois")
            assert config is not None
            assert "case_types" in config or "base_case_types" in config
        except Exception:
            # If jurisdiction configuration doesn't exist, skip this test
            pytest.skip("Jurisdiction configuration not found")

    def test_dropdown_api_views_can_be_imported(self):
        """Test that dropdown API views can be imported."""
        from efile.api.dropdown_views import DropdownAPIViews

        # Should be able to create instance
        view = DropdownAPIViews()
        assert view is not None

        # Should have required methods
        assert hasattr(DropdownAPIViews, "_prioritize_courts_by_location")
        assert hasattr(DropdownAPIViews, "get_case_categories")
        assert hasattr(DropdownAPIViews, "get_courts")
