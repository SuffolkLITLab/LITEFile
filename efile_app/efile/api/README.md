# API Documentation

This directory contains the organized API endpoints for the Illinois eFile system.

## Structure

```
api/
├── __init__.py              # Package initialization
├── base.py                  # Base classes and utilities
├── dropdown_views.py        # Cascading dropdown endpoints with location prioritization
├── auth_views.py            # Authentication endpoints  
├── filing_views.py          # Filing management endpoints
├── config_views.py          # Form configuration endpoints with court-specific logic
├── case_form_views.py       # YAML-based form configuration system
├── case_type_config.py      # Case type configuration mapping
├── suffolk_api_views.py     # Suffolk LIT Lab API integration
└── urls.py                  # URL routing for all API endpoints
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
Cascading dropdown functionality with location-based prioritization and court-specific filtering:
- `courts/` - Get courts with location-based prioritization (supports user_county parameter)
- `case-categories/` - Get case categories filtered by court
- `case-types/` - Get case types (requires parent category)
- `filing-types/` - Get filing types (requires parent case type)
- `document-types/` - Get document types
- `optional-services/` - Get optional services for case types
- `party-types/` - Get available party types

### Form Configuration APIs (`/api/`)
Dynamic form configuration with court-specific conditional requirements:
- `form-config/` - Get complete form configuration with court-specific modifications
- `case-type-config/` - Get case type configuration mapping and keywords

### Suffolk LIT Lab Integration (`/api/suffolk/`)
Integration with external Suffolk LIT Lab eFile API:
- `lookup-case/` - Case lookup functionality

### Authentication APIs (`/api/auth/`)
User authentication and session management with external API integration:
- `login/` - User login
- `logout/` - User logout
- `profile/` - Get user profile with location data
- `external/` - External Suffolk eFile API authentication
- `external-profile/` - Get external user profile
- `tyler-token/` - Tyler Technologies token management

### Payment APIs (`/api/`)
Payment account management:
- `payment-accounts/` - Get available payment accounts

### Filing APIs (`/api/filings/`)
Filing creation and management:
- `filings/` - List user's filings (GET), Create new filing (POST)
- `filings/<id>/` - Get filing details
- `filings/<id>/update/` - Update filing
- `filings/<id>/delete/` - Delete filing

## Usage Examples

### Frontend JavaScript
```javascript
// Load courts with location prioritization
const response = await fetch('/api/dropdowns/courts/?user_county=Cook&jurisdiction=illinois');
const courts = await response.json();

// Get court-specific form configuration
const configResponse = await fetch('/api/form-config/?case_type=name_change&court=cook:cd1');
const formConfig = await configResponse.json();

// Load case categories for specific court
const categoriesResponse = await fetch('/api/dropdowns/case-categories/?court=cook:cd1');
const categories = await categoriesResponse.json();

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
from efile.api.dropdown_views import DropdownAPIViews
from efile.api.config_views import ConfigAPIViews
from efile.api.auth_views import external_auth
```

### Court-Specific Configuration Examples
```javascript
// Form config response includes court-specific modifications
{
    "case_types": {
        "name_change": {
            "sections": {
                "parties": {
                    "fields": [
                        {
                            "section_title": "Petitioner",
                            "conditional_requirements": {
                                "hidden_for_courts": ["bond"],
                                "required_for_courts": ["cook:cd1"]
                            }
                        }
                    ]
                }
            }
        }
    }
}
```

## Migration Notes

The API endpoints have been expanded and reorganized for better functionality:
- **Enhanced**: `/api/dropdowns/courts/` now supports location-based prioritization
- **New**: `/api/form-config/` provides court-specific form configurations
- **New**: `/api/case-type-config/` for case type mapping and keyword matching
- **New**: `/api/suffolk/lookup-case/` for external API integration
- **Enhanced**: Authentication endpoints now support external API integration
- **New**: Payment account management endpoints
- Legacy URLs are temporarily maintained for backward compatibility
- Frontend JavaScript has been updated to use enhanced endpoint features

## Key Features

### Location-Based Court Prioritization
The `/api/dropdowns/courts/` endpoint supports intelligent court ordering:
```javascript
// Courts are automatically prioritized based on user's location
const response = await fetch('/api/dropdowns/courts/?user_county=Cook');
// Returns: Cook County courts first, then other courts
```

### Court-Specific Form Configuration
Dynamic form rendering based on court selection:
- YAML-based configuration system (base-case-types.yaml, states/illinois.yaml)
- Court-specific field visibility (`hidden_for_courts`, `required_for_courts`)
- Automatic configuration inheritance and overrides
- Real-time form updates based on court selection

### Case Type Intelligence
Smart case type matching and configuration:
- Keyword-based case type identification
- Automatic mapping from external API case type IDs to internal configurations
- Support for case type aliases and alternative names

## Configuration System

The API uses a hierarchical YAML configuration system:

### Base Configuration
```yaml
# base-case-types.yaml
base_case_types:
  name_change:
    keywords: ["name change", "name petition"]
    sections:
      parties:
        fields:
          - section_title: "Petitioner"
            conditional_requirements:
              hidden_for_courts: []
              required_for_courts: []
```

### State-Specific Overrides
```yaml
# states/illinois.yaml
court_specific_requirements:
  "bond":
    case_types:
      name_change:
        field_modifications:
          - field_group: "Petitioner"
            modifications:
              conditional_requirements:
                hidden_for_courts: ["bond"]
```

## Future Enhancements

1. **Enhanced Suffolk API Integration**
   - Real-time case status updates
   - Document submission tracking
   - Payment processing integration

2. **Advanced Configuration Features**
   - Dynamic field validation rules based on court requirements
   - Multi-language support for form labels
   - Custom field types for specialized court requirements

3. **Performance Optimizations**
   - Redis caching for dropdown data and form configurations
   - Request rate limiting and throttling
   - Optimized YAML configuration loading

4. **Security Enhancements**
   - Enhanced API authentication with JWT tokens
   - Field-level permissions based on user roles
   - Audit logging for all API operations

5. **Developer Experience**
   - OpenAPI/Swagger documentation generation
   - API versioning support
   - Comprehensive test coverage and documentation
