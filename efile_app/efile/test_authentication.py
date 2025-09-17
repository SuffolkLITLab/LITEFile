"""
Unit tests for Django authentication middleware integration
"""

import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase

from efile.authentication import SuffolkEFileBackend
from efile.models import UserProfile


class AuthenticationMiddlewareTests(TestCase):
    """Test Django authentication middleware integration"""

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.backend = SuffolkEFileBackend()

        # Clean up any existing test users
        User.objects.filter(username="test@example.com").delete()
        User.objects.filter(username="existing@example.com").delete()

    def test_user_is_authenticated_property(self):
        """Test that User.is_authenticated works correctly"""
        # Create a user
        user = User.objects.create_user(username="test@example.com", email="test@example.com", password="testpass123")

        # Test is_authenticated property
        self.assertTrue(user.is_authenticated)
        self.assertFalse(user.is_anonymous)

        # Test with AnonymousUser
        from django.contrib.auth.models import AnonymousUser

        anon_user = AnonymousUser()
        self.assertFalse(anon_user.is_authenticated)
        self.assertTrue(anon_user.is_anonymous)

    def test_user_model_extensions(self):
        """Test that User model extensions work correctly"""
        user = User.objects.create_user(username="test@example.com", email="test@example.com", password="testpass123")

        # Create UserProfile
        UserProfile.objects.create(  # type: ignore[attr-defined]
            user=user,
            street_address="123 Test St",
            city="Test City",
            zip_code="12345",
            county="cook",
            tyler_token="test-token-123",
            suffolk_user_id="suffolk-123",
            firm_name="Test Firm",
            phone="555-1234",
        )

        # Test extended properties
        self.assertEqual(user.tyler_token, "test-token-123")
        self.assertEqual(user.preferred_county, "cook")
        self.assertTrue(user.has_suffolk_integration)
        self.assertEqual(user.address_line1, "123 Test St")
        self.assertEqual(user.city, "Test City")
        self.assertEqual(user.state, "IL")
        self.assertEqual(user.zip_code, "12345")
        self.assertEqual(user.phone, "555-1234")
        self.assertEqual(user.firm_name, "Test Firm")
        self.assertEqual(user.suffolk_user_id, "suffolk-123")

    def test_user_model_extensions_without_profile(self):
        """Test User model extensions when no UserProfile exists"""
        user = User.objects.create_user(username="test@example.com", email="test@example.com", password="testpass123")

        # Test properties with no profile (should return defaults)
        self.assertIsNone(user.tyler_token)
        self.assertEqual(user.preferred_county, "")
        self.assertFalse(user.has_suffolk_integration)
        self.assertEqual(user.address_line1, "")
        self.assertEqual(user.city, "")
        self.assertEqual(user.state, "")
        self.assertEqual(user.zip_code, "")
        self.assertEqual(user.phone, "")
        self.assertEqual(user.firm_name, "")
        self.assertEqual(user.suffolk_user_id, "")

    @patch("efile.authentication.requests.post")
    def test_suffolk_authentication_backend_success(self, mock_post):
        """Test Suffolk authentication backend successful authentication"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tokens": {"TYLER-TOKEN-ILLINOIS": "test-tyler-token", "TYLER-ID-illinois": "test-tyler-id"},
            "user": {"id": "suffolk-user-123", "firstName": "John", "lastName": "Doe", "email": "john.doe@example.com"},
            "firm": {"name": "Test Law Firm", "id": "firm-123"},
            "address": {"addressLine1": "123 Main St", "city": "Chicago", "zipCode": "60601"},
        }
        mock_post.return_value = mock_response

        # Create request
        request = self.factory.post("/login/")
        request.session = {}

        # Test authentication
        user = self.backend.authenticate(request, username="john.doe@example.com", password="testpass123")

        # Verify user was created
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "john.doe@example.com")
        self.assertEqual(user.email, "john.doe@example.com")
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")

        # Verify UserProfile was created with Suffolk data
        profile = user.userprofile
        self.assertEqual(profile.tyler_token, "test-tyler-token")
        self.assertEqual(profile.suffolk_user_id, "suffolk-user-123")
        self.assertEqual(profile.firm_name, "Test Law Firm")
        self.assertEqual(profile.street_address, "123 Main St")
        self.assertEqual(profile.city, "Chicago")
        self.assertEqual(profile.zip_code, "60601")
        # Verify county was set dynamically based on zip code
        self.assertEqual(profile.county, "cook")

    @patch("efile.authentication.requests.post")
    def test_suffolk_authentication_backend_failure(self, mock_post):
        """Test Suffolk authentication backend failed authentication"""
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        request = self.factory.post("/login/")
        request.session = {}

        # Test authentication failure
        user = self.backend.authenticate(request, username="invalid@example.com", password="wrongpass")

        self.assertIsNone(user)

    @patch("efile.authentication.requests.post")
    def test_suffolk_authentication_with_api_county(self, mock_post):
        """Test Suffolk authentication backend with county from API"""
        # Mock successful API response with county field
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tokens": {"TYLER-TOKEN-ILLINOIS": "test-tyler-token", "TYLER-ID-illinois": "test-tyler-id"},
            "user": {
                "id": "suffolk-user-456",
                "firstName": "Jane",
                "lastName": "Smith",
                "email": "jane.smith@example.com",
            },
            "firm": {"name": "Smith Law Office", "id": "firm-456"},
            "address": {
                "addressLine1": "456 State St",
                "city": "Springfield",
                "zipCode": "62701",
                "county": "Sangamon",  # API provides county directly
            },
        }
        mock_post.return_value = mock_response

        # Create request
        request = self.factory.post("/login/")
        request.session = {}

        # Test authentication
        user = self.backend.authenticate(request, username="jane.smith@example.com", password="testpass123")

        # Verify user was created
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "jane.smith@example.com")
        self.assertEqual(user.email, "jane.smith@example.com")
        self.assertEqual(user.first_name, "Jane")
        self.assertEqual(user.last_name, "Smith")

        # Verify UserProfile was created with Suffolk data
        profile = user.userprofile
        self.assertEqual(profile.tyler_token, "test-tyler-token")
        self.assertEqual(profile.suffolk_user_id, "suffolk-user-456")
        self.assertEqual(profile.firm_name, "Smith Law Office")
        self.assertEqual(profile.street_address, "456 State St")
        self.assertEqual(profile.city, "Springfield")
        self.assertEqual(profile.zip_code, "62701")
        # Verify county was set from API field (not zip lookup)
        self.assertEqual(profile.county, "sangamon")

    def test_suffolk_authentication_backend_existing_user(self):
        """Test authentication with existing user"""
        # Create existing user
        existing_user = User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
            password="oldpass",
            first_name="Old",
            last_name="Name",
        )

        with patch("efile.authentication.requests.post") as mock_post:
            # Mock successful API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "tokens": {
                    "TYLER-TOKEN-ILLINOIS": "new-tyler-token",
                },
                "user": {
                    "id": "suffolk-user-456",
                    "firstName": "Updated",
                    "lastName": "Name",
                    "email": "existing@example.com",
                },
            }
            mock_post.return_value = mock_response

            request = self.factory.post("/login/")
            request.session = {}

            # Test authentication with existing user
            user = self.backend.authenticate(request, username="existing@example.com", password="newpass")

            # Should return the same user object
            self.assertEqual(user.id, existing_user.id)
            self.assertEqual(user.username, "existing@example.com")

            # Profile should be created/updated
            profile = user.userprofile
            self.assertEqual(profile.tyler_token, "new-tyler-token")
            self.assertEqual(profile.suffolk_user_id, "suffolk-user-456")

    def test_login_api_endpoint_success(self):
        """Test login API endpoint with successful authentication"""
        with patch("efile.authentication.requests.post") as mock_post:
            # Mock successful API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "tokens": {
                    "TYLER-TOKEN-ILLINOIS": "api-tyler-token",
                }
            }
            mock_post.return_value = mock_response

            # Test login API
            response = self.client.post(
                "/api/auth/login/",
                data=json.dumps({"username": "api.test@example.com", "password": "testpass123"}),
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertTrue(data["data"]["is_authenticated"])
            self.assertEqual(data["data"]["username"], "api.test@example.com")
            self.assertEqual(data["data"]["email"], "api.test@example.com")

    def test_login_api_endpoint_failure(self):
        """Test login API endpoint with failed authentication"""
        with patch("efile.authentication.requests.post") as mock_post:
            # Mock failed API response
            mock_response = Mock()
            mock_response.status_code = 401
            mock_post.return_value = mock_response

            # Test login API
            response = self.client.post(
                "/api/auth/login/",
                data=json.dumps({"username": "invalid@example.com", "password": "wrongpass"}),
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 401)
            data = response.json()
            self.assertFalse(data["success"])

    def test_user_profile_api_authenticated(self):
        """Test user profile API with authenticated user"""
        # Create and login user
        user = User.objects.create_user(
            username="profile.test@example.com",
            email="profile.test@example.com",
            password="testpass123",
            first_name="Profile",
            last_name="Test",
        )

        # Create profile
        UserProfile.objects.create(  # type: ignore[attr-defined]
            user=user,
            street_address="456 Profile St",
            city="Profile City",
            zip_code="54321",
            county="dupage",
            phone="555-9876",
        )

        # Login user
        self.client.force_login(user)

        # Test profile API
        response = self.client.get("/api/auth/profile/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        user_data = data["data"]
        self.assertTrue(user_data["is_authenticated"])
        self.assertEqual(user_data["username"], "profile.test@example.com")
        self.assertEqual(user_data["first_name"], "Profile")
        self.assertEqual(user_data["last_name"], "Test")
        self.assertEqual(user_data["address"], "456 Profile St")
        self.assertEqual(user_data["city"], "Profile City")
        self.assertEqual(user_data["zip_code"], "54321")
        self.assertEqual(user_data["phone"], "555-9876")

    def test_user_profile_api_unauthenticated(self):
        """Test user profile API with unauthenticated user"""
        response = self.client.get("/api/auth/profile/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        user_data = data["data"]
        self.assertFalse(user_data["is_authenticated"])
        self.assertEqual(user_data["username"], "demo_user")
        self.assertEqual(user_data["first_name"], "Demo")
        self.assertEqual(user_data["last_name"], "User")

    def test_logout_api_endpoint(self):
        """Test logout API endpoint"""
        # Create and login user
        user = User.objects.create_user(
            username="logout.test@example.com", email="logout.test@example.com", password="testpass123"
        )
        self.client.force_login(user)

        # Verify user is logged in
        response = self.client.get("/api/auth/profile/")
        data = response.json()
        self.assertTrue(data["data"]["is_authenticated"])

        # Test logout
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify user is logged out
        response = self.client.get("/api/auth/profile/")
        data = response.json()
        self.assertFalse(data["data"]["is_authenticated"])

    def test_tyler_token_api_authenticated(self):
        """Test Tyler token API with authenticated user"""
        user = User.objects.create_user(
            username="tyler.test@example.com", email="tyler.test@example.com", password="testpass123"
        )

        # Create profile with Tyler token
        UserProfile.objects.create(  # type: ignore[attr-defined]
            user=user,
            street_address="789 Tyler St",
            city="Tyler City",
            zip_code="78901",
            county="cook",
            tyler_token="test-tyler-token-123",
        )

        self.client.force_login(user)

        # Test Tyler token API
        response = self.client.get("/api/auth/tyler-token/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        token_data = data["data"]
        self.assertTrue(token_data["is_authenticated"])
        self.assertEqual(token_data["tyler_token"], "test-tyler-token-123")
        self.assertEqual(token_data["state"], "illinois")

    def test_external_profile_api_authenticated(self):
        """Test external profile API with authenticated user"""
        user = User.objects.create_user(
            username="external.test@example.com", email="external.test@example.com", password="testpass123"
        )

        UserProfile.objects.create(  # type: ignore[attr-defined]
            user=user, street_address="321 External St", city="External City", zip_code="32109", county="kane"
        )

        self.client.force_login(user)

        # Test external profile API
        response = self.client.get("/api/auth/external-profile/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        profile_data = data["data"]
        self.assertEqual(profile_data["user_county"], "kane")
        self.assertIn("location_details", profile_data)
        self.assertIn("preferences", profile_data)

    def test_external_profile_api_unauthenticated(self):
        """Test external profile API with unauthenticated user"""
        response = self.client.get("/api/auth/external-profile/")

        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data["success"])

    def test_session_persistence(self):
        """Test that authentication persists across requests"""
        # Create user
        user = User.objects.create_user(
            username="session.test@example.com", email="session.test@example.com", password="testpass123"
        )

        # Login
        self.client.force_login(user)

        # Test multiple requests maintain authentication
        for _i in range(3):
            response = self.client.get("/api/auth/profile/")
            data = response.json()
            self.assertTrue(data["data"]["is_authenticated"])
            self.assertEqual(data["data"]["username"], "session.test@example.com")

    def test_concurrent_user_authentication(self):
        """Test that multiple users can be authenticated simultaneously"""
        # Create multiple users
        user1 = User.objects.create_user(
            username="user1@example.com", email="user1@example.com", password="testpass123"
        )
        user2 = User.objects.create_user(
            username="user2@example.com", email="user2@example.com", password="testpass123"
        )

        # Create separate clients for each user
        client1 = Client()
        client2 = Client()

        # Login each user
        client1.force_login(user1)
        client2.force_login(user2)

        # Test that each client maintains separate authentication
        response1 = client1.get("/api/auth/profile/")
        data1 = response1.json()
        self.assertTrue(data1["data"]["is_authenticated"])
        self.assertEqual(data1["data"]["username"], "user1@example.com")

        response2 = client2.get("/api/auth/profile/")
        data2 = response2.json()
        self.assertTrue(data2["data"]["is_authenticated"])
        self.assertEqual(data2["data"]["username"], "user2@example.com")


class AuthenticationBackendUnitTests(TestCase):
    """Unit tests specifically for the authentication backend"""

    def setUp(self):
        self.backend = SuffolkEFileBackend()
        self.factory = RequestFactory()

    def test_get_state_from_request_query_param(self):
        """Test extracting state from query parameters"""
        request = self.factory.get("/test/?state=california")
        state = self.backend._get_state_from_request(request)
        self.assertEqual(state, "california")

    def test_get_state_from_request_url_path(self):
        """Test extracting state from URL path"""
        request = self.factory.get("/jurisdictions/texas/some/path/")
        state = self.backend._get_state_from_request(request)
        self.assertEqual(state, "texas")

    def test_get_state_from_request_default(self):
        """Test default state when none specified"""
        request = self.factory.get("/test/")
        state = self.backend._get_state_from_request(request)
        self.assertEqual(state, "illinois")

    def test_get_user_by_id(self):
        """Test getting user by ID"""
        user = User.objects.create_user(
            username="getuser.test@example.com", email="getuser.test@example.com", password="testpass123"
        )

        # Test valid user ID
        retrieved_user = self.backend.get_user(user.id)
        self.assertEqual(retrieved_user, user)

        # Test invalid user ID
        invalid_user = self.backend.get_user(99999)
        self.assertIsNone(invalid_user)

    def test_extract_user_data(self):
        """Test extracting user data from API response"""
        auth_data = {"user": {"firstName": "Extract", "lastName": "Test", "email": "extract.test@example.com"}}

        user_data = self.backend._extract_user_data(auth_data, "extract.test@example.com", "illinois")

        self.assertEqual(user_data["first_name"], "Extract")
        self.assertEqual(user_data["last_name"], "Test")
        self.assertEqual(user_data["email"], "extract.test@example.com")

    def test_extract_user_data_alternative_format(self):
        """Test extracting user data from alternative API response format"""
        auth_data = {"user": {"first_name": "Alt", "last_name": "Format", "email": "alt.format@example.com"}}

        user_data = self.backend._extract_user_data(auth_data, "alt.format@example.com", "illinois")

        self.assertEqual(user_data["first_name"], "Alt")
        self.assertEqual(user_data["last_name"], "Format")
        self.assertEqual(user_data["email"], "alt.format@example.com")

    def test_update_user_county_from_zip(self):
        """Test updating existing user's county from zip code"""
        from efile.models import UserProfile, update_user_county_from_zip

        # Create user with profile but no county
        user = User.objects.create_user(
            username="county.test@example.com", email="county.test@example.com", password="testpass123"
        )
        profile, created = UserProfile.objects.get_or_create(user=user)  # type: ignore[attr-defined]
        profile.zip_code = "60601"  # Cook County zip
        profile.county = ""  # No county set
        profile.save()

        # Update county from zip
        updated = update_user_county_from_zip(user)
        self.assertTrue(updated)

        # Verify county was set
        profile.refresh_from_db()
        self.assertEqual(profile.county, "cook")  # Should match database format

        # Test with user that already has county
        profile.county = "Existing County"
        profile.save()

        updated = update_user_county_from_zip(user)
        self.assertFalse(updated)  # Should not update existing county

        profile.refresh_from_db()
        self.assertEqual(profile.county, "Existing County")  # Should remain unchanged
