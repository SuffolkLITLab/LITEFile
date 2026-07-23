"""Shared fixtures for the Python suite."""

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def stand_in_document_disabled_by_default():
    """Run every test in the production-shaped configuration.

    EFSP_TEST_DOCUMENT_URL is a local-development affordance -- compose sets it by
    default so fee quotes work against LocalStack uploads -- but pytest-django
    forces DEBUG=False, and "stand-in URL set, DEBUG off" is precisely what
    substitute_test_document_urls refuses to run under. Without this fixture the
    suite would pass in CI and fail on a developer's machine, for any test that
    exercises a filing path.

    Tests that want the substitution opt into it with override_settings, so the
    dependency is visible in the test that relies on it.
    """
    with override_settings(EFSP_TEST_DOCUMENT_URL=""):
        yield
