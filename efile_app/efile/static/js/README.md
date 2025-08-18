# Expert Form JavaScript Architecture

This document describes the modular JavaScript architecture for the expert form functionality.

## File Structure

```
efile/static/js/
├── api-utils.js          # API communication utilities
├── cascading-dropdowns.js # Smart dropdown functionality
├── form-validation.js    # Form validation and user feedback
├── expert-form-main.js   # Main coordinator and initialization
└── README.md            # This documentation
```

## Module Overview

### 1. api-utils.js
**Purpose**: Centralized API communication with error handling and CSRF protection.

**Key Features**:
- Automatic CSRF token handling
- Request timeout management
- Standardized error handling
- URL building with parameters
- Convenient HTTP verb methods (get, post, put, etc.)

**Global Access**: `window.apiUtils`

### 2. cascading-dropdowns.js
**Purpose**: Intelligent form dropdown behavior with location-based recommendations.

**Key Features**:
- User profile integration for location-based defaults
- Court-specific case category filtering
- Progressive form enablement (court → case category → case type, etc.)
- Auto-selection with user notifications
- Smart placeholder management

**Dependencies**: 
- `api-utils.js` for API communication
- User profile API endpoint (`/api/auth/profile/`)

**Global Access**: `window.CascadingDropdowns`

### 3. form-validation.js
**Purpose**: Real-time form validation with enhanced user experience.

**Key Features**:
- Real-time field validation with visual feedback
- Draft saving to localStorage
- Enhanced error messaging and notifications
- Form data collection and restoration
- Accessibility-friendly error handling

**Global Access**: `window.FormValidation`

### 4. expert-form-main.js
**Purpose**: Main coordinator that initializes and manages all form components.

**Key Features**:
- Component initialization and coordination
- Draft restoration from previous sessions
- Global instance management
- Error handling and recovery

**Global Access**: 
- `window.ExpertForm` (class)
- `window.getExpertFormInstance()` (active instance)

## Loading Order

The scripts must be loaded in this specific order due to dependencies:

1. `api-utils.js` - Provides `apiUtils` global
2. `cascading-dropdowns.js` - Uses `apiUtils`
3. `form-validation.js` - Independent
4. `expert-form-main.js` - Coordinates all modules

## API Endpoints Used

- `/api/auth/profile/` - User profile and location data
- `/api/dropdowns/courts/` - Court listings with location prioritization
- `/api/dropdowns/case-categories/` - Case categories filtered by court
- `/api/dropdowns/case-types/` - Case types based on category
- `/api/dropdowns/filing-types/` - Filing types based on case type
- `/api/dropdowns/document-types/` - Document types for final selection
- `/api/form-config/` - Dynamic form configuration based on selections

## Configuration

### Location Intelligence
The system automatically prioritizes courts based on user location:
- User's zip code → county mapping
- County → court prioritization
- Auto-selection with user notification

### Draft Saving
- Manual save only via "Save Draft" button (auto-save removed)
- User-controlled draft creation for better user experience
- Restoration on page reload (24-hour expiry)
- localStorage backup for reliability
- Visual feedback when saving drafts

### Error Handling
- Network timeouts (30 seconds)
- API error translation to user-friendly messages
- Graceful degradation when APIs are unavailable
- Console logging for debugging

## Usage Examples

### Accessing the Form Instance
```javascript
const formInstance = getExpertFormInstance();
const dropdowns = formInstance.getCascadingDropdowns();
const validation = formInstance.getFormValidation();
```

### Manual API Calls
```javascript
// Using the global API utility
const response = await apiUtils.get('/api/dropdowns/courts/', {
    user_county: 'Cook',
    jurisdiction: 'illinois'
});
```

### Custom Validation
```javascript
const validation = getExpertFormInstance().getFormValidation();
validation.showNotification('Custom message', 'success');
```

## Performance Considerations

- Scripts load asynchronously after DOM ready
- API requests are cached where appropriate
- Loading spinners prevent multiple simultaneous requests
- Manual draft saving prevents excessive storage operations

## Security Features

- CSRF token automatic inclusion
- XSS prevention through proper DOM manipulation
- Input validation on both client and server
- Secure localStorage usage for draft data

## Debugging

Enable console logging by setting:
```javascript
window.debugFormModules = true;
```

This will provide detailed logging for:
- API requests and responses
- Form state changes
- Validation events
- Draft save operations (manual only)