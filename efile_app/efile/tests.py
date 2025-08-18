import pytest
import json
from unittest.mock import Mock, patch
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import Client
from django.http import JsonResponse


@pytest.mark.django_db(False)
def test_settings_are_wired(settings):
    """pytest-django should expose Django settings fixture."""
    assert settings.ROOT_URLCONF == "efile.urls"


def test_login_page_renders(client):
    """Basic smoke test: GET /login/ should render the login page (200)."""
    url = reverse("efile_login")
    resp = client.get(url)
    assert resp.status_code == 200
    # Optional sanity check that template contains 'login' somewhere
    assert b"login" in resp.content.lower()


# ============================================================================
# DROPDOWN API TESTS
# ============================================================================

class TestDropdownAPIs:
    """Test suite for dropdown API endpoints."""
    
    @pytest.fixture
    def api_client(self):
        """Create a client with AJAX headers."""
        client = Client()
        return client
    
    @pytest.fixture
    def user(self, db):
        """Create a test user."""
        return User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_courts_api_without_params(self, api_client):
        """Test courts API returns data without parameters."""
        with patch('efile.dropdown_views.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'courts': [
                    {'id': 'cook:law1', 'name': 'Cook County Law Division', 'jurisdiction': 'illinois'},
                    {'id': 'cook:dr1', 'name': 'Cook County Domestic Relations', 'jurisdiction': 'illinois'},
                ]
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            response = api_client.get('/api/dropdowns/courts/', 
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['success'] is True
            assert len(data['data']) >= 2
            assert any(court['value'] == 'cook:law1' for court in data['data'])
    
    def test_courts_api_with_user_location(self, api_client):
        """Test courts API prioritizes based on user location."""
        with patch('efile.dropdown_views.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'courts': [
                    {'id': 'cook:law1', 'name': 'Cook County Law Division', 'jurisdiction': 'illinois'},
                    {'id': 'will:law1', 'name': 'Will County Law Division', 'jurisdiction': 'illinois'},
                ]
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            response = api_client.get('/api/dropdowns/courts/', {
                'user_county': 'Cook',
                'user_zip': '60601'
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['success'] is True
            
            # Cook County courts should be marked as recommended
            cook_courts = [court for court in data['data'] if 'cook' in court['value'].lower()]
            assert len(cook_courts) > 0
            assert any(court.get('recommended') for court in cook_courts)
    
    def test_case_categories_api_with_court(self, api_client):
        """Test case categories API filters by court."""
        with patch('efile.dropdown_views.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'case_categories': [
                    {'id': 'civil', 'text': 'Civil Law'},
                    {'id': 'family', 'text': 'Family Law'},
                    {'id': 'probate', 'text': 'Probate'},
                ]
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            response = api_client.get('/api/dropdowns/case-categories/', {
                'court': 'cook:law1'
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['success'] is True
            assert len(data['data']) > 0
            
            # Should contain civil and family for law court
            category_texts = [cat['text'].lower() for cat in data['data']]
            assert any('civil' in text for text in category_texts)
    
    def test_case_categories_api_without_court_returns_error(self, api_client):
        """Test case categories API requires court parameter."""
        response = api_client.get('/api/dropdowns/case-categories/', 
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'court parameter is required' in data['error'].lower()
    
    def test_case_types_api(self, api_client):
        """Test case types API returns filtered data."""
        with patch('efile.dropdown_views.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'case_types': [
                    {'id': 'divorce', 'name': 'Divorce'},
                    {'id': 'custody', 'name': 'Child Custody'},
                ]
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            response = api_client.get('/api/dropdowns/case-types/', {
                'category': 'family',
                'court': 'cook:dr1'
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['success'] is True
            assert len(data['data']) > 0
    
    def test_api_handles_external_service_failure(self, api_client):
        """Test API gracefully handles external service failures."""
        with patch('efile.dropdown_views.requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")
            
            response = api_client.get('/api/dropdowns/courts/', 
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['success'] is False
            assert 'error fetching' in data['error'].lower()


# ============================================================================
# AUTH API TESTS  
# ============================================================================

class TestAuthAPIs:
    """Test suite for authentication API endpoints."""
    
    @pytest.fixture
    def user(self, db):
        """Create a test user with profile data."""
        return User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
    
    def test_profile_api_authenticated_user(self, client, user):
        """Test profile API returns user data when authenticated."""
        client.force_login(user)
        
        response = client.get('/api/auth/profile/', 
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['data']['username'] == 'testuser'
        assert data['data']['first_name'] == 'John'
        assert data['data']['email'] == 'test@example.com'
    
    def test_profile_api_with_zip_code_mapping(self, client, user):
        """Test profile API includes county mapping for zip code."""
        client.force_login(user)
        
        # Mock user has zip code 60601 (Chicago/Cook County)
        with patch('efile.api.auth_views._get_user_zip_code', return_value='60601'):
            response = client.get('/api/auth/profile/', 
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['data']['zip_code'] == '60601'
        assert data['data']['preferred_county'] == 'Cook'
    
    def test_profile_api_unauthenticated_user(self, client):
        """Test profile API handles unauthenticated users."""
        response = client.get('/api/auth/profile/', 
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'not authenticated' in data['error'].lower()


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

class TestZipToCountyMapping:
    """Test suite for Illinois zip-to-county mapping utility."""
    
    def test_get_county_by_zip_cook_county(self):
        """Test mapping for Cook County zip codes."""
        from efile.utils.zip_to_county_il import get_county_by_zip
        
        # Test major Chicago zip codes
        assert get_county_by_zip('60601') == 'Cook'  # Downtown Chicago
        assert get_county_by_zip('60614') == 'Cook'  # Lincoln Park
        assert get_county_by_zip('60611') == 'Cook'  # Near North Side
    
    def test_get_county_by_zip_other_counties(self):
        """Test mapping for other Illinois counties."""
        from efile.utils.zip_to_county_il import get_county_by_zip
        
        # Test some other counties with correct zip codes
        assert get_county_by_zip('61820') == 'Champaign'  # Champaign County
        assert get_county_by_zip('62701') == 'Sangamon'   # Springfield
        assert get_county_by_zip('61108') == 'Winnebago'  # Rockford
    
    def test_get_county_by_zip_invalid_zip(self):
        """Test handling of invalid zip codes."""
        from efile.utils.zip_to_county_il import get_county_by_zip
        
        assert get_county_by_zip('00000') is None
        assert get_county_by_zip('99999') is None
        assert get_county_by_zip('invalid') is None
        assert get_county_by_zip('') is None
        assert get_county_by_zip(None) is None
    
    def test_get_zip_codes_by_county(self):
        """Test reverse mapping from county to zip codes."""
        from efile.utils.zip_to_county_il import get_zips_by_county
        
        cook_zips = get_zips_by_county('Cook')
        assert len(cook_zips) > 50  # Cook County has many zip codes
        assert '60601' in cook_zips
        assert '60614' in cook_zips
        
        # Test another county
        champaign_zips = get_zips_by_county('Champaign')
        assert len(champaign_zips) > 0
        assert '61820' in champaign_zips
    
    def test_get_zip_codes_by_county_invalid(self):
        """Test handling of invalid county names."""
        from efile.utils.zip_to_county_il import get_zips_by_county
        
        assert get_zips_by_county('InvalidCounty') == []
        assert get_zips_by_county('') == []
        assert get_zips_by_county(None) == []


# ============================================================================
# DROPDOWN VIEW HELPER TESTS
# ============================================================================

class TestDropdownViewHelpers:
    """Test suite for dropdown view helper functions."""
    
    def test_prioritize_courts_by_location(self):
        """Test court prioritization based on user location."""
        from efile.api.dropdown_views import DropdownAPIViews
        
        view = DropdownAPIViews()
        courts = [
            {'id': 'cook:law1', 'name': 'Cook County Law', 'jurisdiction': 'illinois'},
            {'id': 'will:law1', 'name': 'Will County Law', 'jurisdiction': 'illinois'},
            {'id': 'dupage:law1', 'name': 'DuPage County Law', 'jurisdiction': 'illinois'},
        ]
        
        # Test Cook County user
        prioritized = view._prioritize_courts_by_location(courts, 'Cook', '60601')
        cook_courts = [c for c in prioritized if 'cook' in c['id']]
        assert len(cook_courts) > 0
        assert all(c.get('recommended') for c in cook_courts)
        
        # Cook County courts should be first
        first_court = prioritized[0]
        assert 'cook' in first_court['id']
    
    def test_filter_categories_by_court_law_division(self):
        """Test case category filtering for law division courts."""
        from efile.api.dropdown_views import DropdownAPIViews
        
        view = DropdownAPIViews()
        categories = [
            {'id': 'civil', 'text': 'Civil Law'},
            {'id': 'family', 'text': 'Family Law'},
            {'id': 'probate', 'text': 'Probate'},
            {'id': 'criminal', 'text': 'Criminal'},
        ]
        
        # Law division should get civil and miscellaneous
        filtered = view._filter_categories_by_court(categories, 'cook:law1')
        category_texts = [c['text'].lower() for c in filtered]
        
        assert any('civil' in text for text in category_texts)
        assert len(filtered) > 0
    
    def test_filter_categories_by_court_family_division(self):
        """Test case category filtering for domestic relations courts."""
        from efile.api.dropdown_views import DropdownAPIViews
        
        view = DropdownAPIViews()
        categories = [
            {'id': 'civil', 'text': 'Civil Law'},
            {'id': 'family', 'text': 'Family Law'},
            {'id': 'probate', 'text': 'Probate'},
        ]
        
        # DR division should get family categories
        filtered = view._filter_categories_by_court(categories, 'cook:dr1')
        category_texts = [c['text'].lower() for c in filtered]
        
        assert any('family' in text for text in category_texts)
    
    def test_filter_categories_by_court_fallback(self):
        """Test case category filtering fallback for unknown courts."""
        from efile.api.dropdown_views import DropdownAPIViews
        
        view = DropdownAPIViews()
        categories = [
            {'id': 'civil', 'text': 'Civil Law'},
            {'id': 'family', 'text': 'Family Law'},
        ]
        
        # Unknown court should return all categories
        filtered = view._filter_categories_by_court(categories, 'unknown:court1')
        assert len(filtered) == len(categories)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestExpertFormIntegration:
    """Integration tests for the complete expert form flow."""
    
    @pytest.fixture
    def authenticated_client(self, client, db):
        """Create an authenticated client."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com', 
            password='testpass123'
        )
        client.force_login(user)
        return client
    
    def test_expert_form_page_loads(self, authenticated_client):
        """Test that the expert form page loads correctly."""
        response = authenticated_client.get('/expert-form/')
        
        assert response.status_code == 200
        assert b'Case Details & Parties' in response.content
        assert b'cascading-dropdowns.js' in response.content
        assert b'form-validation.js' in response.content
    
    @patch('efile.dropdown_views.requests.get')
    def test_complete_dropdown_flow(self, mock_get, authenticated_client):
        """Test the complete dropdown cascade flow."""
        # Mock external API responses
        def mock_api_response(*args, **kwargs):
            url = args[0]
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            
            if 'courts' in url:
                mock_response.json.return_value = {
                    'courts': [{'id': 'cook:law1', 'name': 'Cook County Law', 'jurisdiction': 'illinois'}]
                }
            elif 'case_categories' in url:
                mock_response.json.return_value = {
                    'case_categories': [{'id': 'civil', 'text': 'Civil Law'}]
                }
            elif 'case_types' in url:
                mock_response.json.return_value = {
                    'case_types': [{'id': 'contract', 'name': 'Contract Dispute'}]
                }
            
            return mock_response
        
        mock_get.side_effect = mock_api_response
        
        # Test courts API
        response = authenticated_client.get('/api/dropdowns/courts/', 
                                          HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        
        # Test case categories API with court
        response = authenticated_client.get('/api/dropdowns/case-categories/', 
                                          {'court': 'cook:law1'},
                                          HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        
        # Test case types API with category
        response = authenticated_client.get('/api/dropdowns/case-types/', 
                                          {'category': 'civil', 'court': 'cook:law1'},
                                          HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
    
    def test_form_submission_validation(self, authenticated_client):
        """Test form submission with validation."""
        response = authenticated_client.post('/expert-form/', {
            'court': 'cook:law1',
            'case_category': 'civil',
            'case_type': 'contract',
            'filing_type': 'complaint',
            'document_type': 'motion',
            'petitioner_first_name': 'John',
            'petitioner_last_name': 'Doe',
            'new_first_name': 'Jane',
            'new_last_name': 'Smith',
        })
        
        # Should redirect or show success (depending on implementation)
        assert response.status_code in [200, 302]


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test suite for error handling scenarios."""
    
    def test_api_without_ajax_header(self, client):
        """Test API endpoints require AJAX headers."""
        response = client.get('/api/dropdowns/courts/')
        
        # Should return error or redirect (depending on implementation)
        assert response.status_code in [400, 403, 405]
    
    @patch('efile.dropdown_views.requests.get')
    def test_external_api_timeout(self, mock_get, client):
        """Test handling of external API timeouts."""
        mock_get.side_effect = Exception("Connection timeout")
        
        response = client.get('/api/dropdowns/courts/', 
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'error' in data
    
    def test_malformed_requests(self, client):
        """Test handling of malformed API requests."""
        # Test with invalid parameters
        response = client.get('/api/dropdowns/case-categories/', 
                            {'court': ''},  # Empty court parameter
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False
