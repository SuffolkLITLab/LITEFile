# API Documentation

This directory contains the organized API endpoints for the Illinois eFile system.

## Structure

```
api/
├── __init__.py          # Package initialization
├── base.py              # Base classes and utilities
├── dropdown_views.py    # Cascading dropdown endpoints
├── auth_views.py        # Authentication endpoints  
├── filing_views.py      # Filing management endpoints
└── urls.py             # URL routing for all API endpoints
```

## Base Classes

### APIResponseMixin
Provides consistent response formatting for all API endpoints:
- `success_response(data, message=None)` - Returns successful responses
- `error_response(error_message, status_code=400)` - Returns error responses

### Helper Functions
- `get_auth_tokens(request)` - Retrieves auth tokens from session
- `validate_request(request, required_params)` - Validates required parameters

## Endpoint Categories

### Dropdown APIs (`/api/dropdowns/`)
Cascading dropdown functionality for form fields:
- `case-categories/` - Get case categories
- `case-types/` - Get case types (requires parent category)
- `filing-types/` - Get filing types (requires parent case type)
- `counties/` - Get counties
- `document-types/` - Get document types

### Authentication APIs (`/api/auth/`)
User authentication and session management:
- `login/` - User login
- `logout/` - User logout
- `profile/` - Get user profile
- `external/` - External Suffolk eFile API authentication

### Filing APIs (`/api/filings/`)
Filing creation and management:
- `filings/` - List user's filings (GET), Create new filing (POST)
- `filings/<id>/` - Get filing details
- `filings/<id>/update/` - Update filing
- `filings/<id>/delete/` - Delete filing

## Usage Examples

### Frontend JavaScript
```javascript
// Load dropdown data
const response = await fetch('/api/dropdowns/case-categories/');
const data = await response.json();

// Create filing
const response = await fetch('/api/filings/create/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
    },
    body: JSON.stringify(filingData)
});
```

### Django Views
```python
from efile.api.dropdown_views import get_case_categories
from efile.api.auth_views import external_auth
```

## Migration Notes

The API endpoints have been moved from individual view files to this organized structure:
- Old endpoints: `/api/get-case-categories/` → New: `/api/dropdowns/case-categories/`
- Legacy URLs are temporarily maintained for backward compatibility
- Frontend JavaScript has been updated to use new endpoint structure

## Future Enhancements

1. Replace mock data with actual Suffolk eFile API calls
2. Add proper authentication checks when external API is available
3. Implement caching for dropdown data
4. Add request rate limiting
5. Add API documentation generation (Django REST Framework)
