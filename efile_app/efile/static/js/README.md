# Expert Form JavaScript Architecture

This document describes the modular JavaScript architecture for the expert form functionality with dynamic court-specific form rendering.

## File Structure

```
efile/static/js/
├── api-utils.js              # API communication utilities
├── cascading-dropdowns.js    # Smart dropdown functionality with location-based recommendations
├── form-validation.js        # Form validation and user feedback
├── dynamic-form-sections.js  # Dynamic form rendering with court-specific conditional logic
├── expert-form-main.js       # Main coordinator and initialization
└── README.md                # This documentation

efile/static/config/
├── base-case-types.yaml      # Base form configuration templates
└── states/
    └── illinois.yaml         # Illinois-specific court requirements and overrides
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
**Purpose**: Intelligent form dropdown behavior with location-based recommendations and persistent user notifications.

**Key Features**:
- User profile integration for location-based defaults
- Court-specific case category filtering
- Progressive form enablement (court → case category → case type, etc.)
- Auto-selection with persistent recommendation notices
- Smart placeholder management
- Court-specific form section triggering

**Dependencies**: 
- `api-utils.js` for API communication
- User profile API endpoint (`/api/auth/profile/`)
- Dynamic form sections integration

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

### 4. dynamic-form-sections.js
**Purpose**: Dynamic form rendering with court-specific conditional logic and automatic header management.

**Key Features**:
- YAML-based configuration system for form structures
- Court-specific field visibility and requirements (hidden_for_courts, required_for_courts)
- Dynamic section rendering with conditional logic
- Automatic header hiding when no sections are rendered
- Form data preservation during court changes
- Real-time form updates based on dropdown selections

**Dependencies**:
- `/api/form-config/` endpoint for court-specific configurations
- YAML configuration files (base-case-types.yaml, states/illinois.yaml)
- Integration with cascading dropdowns for court selection

**Global Access**: `window.DynamicFormSections`

### 5. expert-form-main.js
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
4. `dynamic-form-sections.js` - Independent, integrates with cascading dropdowns
5. `expert-form-main.js` - Coordinates all modules

## API Endpoints Used

- `/api/auth/profile/` - User profile and location data
- `/api/dropdowns/courts/` - Court listings with location prioritization
- `/api/dropdowns/case-categories/` - Case categories filtered by court
- `/api/dropdowns/case-types/` - Case types based on category
- `/api/dropdowns/filing-types/` - Filing types based on case type
- `/api/dropdowns/document-types/` - Document types for final selection
- `/api/form-config/` - Dynamic form configuration with court-specific conditional requirements

## Configuration System

### YAML-Based Form Configuration
The system uses a hierarchical YAML configuration structure:

**Base Configuration (`base-case-types.yaml`)**:
- Defines common form structures and field templates
- Provides conditional_requirements framework for court-specific modifications
- Sets default field types, validation rules, and column widths

**State-Specific Configuration (`states/illinois.yaml`)**:
- Extends base configuration with state-specific requirements
- Defines court-specific field modifications using arrays:
  - `hidden_for_courts: ["bond"]` - Hide sections for specific courts
  - `required_for_courts: ["cook:cd1"]` - Make sections required for specific courts
- Supports inheritance from base templates with custom overrides

### Court-Specific Conditional Logic
```yaml
# Example: Hide petitioner section for Bond County
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

## Configuration

### Location Intelligence
The system automatically prioritizes courts based on user location:
- User's zip code → county mapping
- County → court prioritization
- Auto-selection with persistent user notification
- Green recommendation notices positioned above dropdown labels
- Notices persist during automatic cascading operations

### Court-Specific Form Rendering
- Dynamic form sections based on court selection
- Conditional field visibility (hidden_for_courts, required_for_courts)
- Automatic header management (hides "Parties" header when no sections render)
- Real-time form updates when court selection changes
- Form data preservation during court transitions

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
- Court-specific configuration validation

## Usage Examples

### Accessing the Form Instance
```javascript
const formInstance = getExpertFormInstance();
const dropdowns = formInstance.getCascadingDropdowns();
const validation = formInstance.getFormValidation();
const dynamicSections = formInstance.getDynamicFormSections();
```

### Manual API Calls
```javascript
// Using the global API utility
const response = await apiUtils.get('/api/dropdowns/courts/', {
    user_county: 'Cook',
    jurisdiction: 'illinois'
});

// Get court-specific form configuration
const formConfig = await apiUtils.get('/api/form-config/', {
    case_type: 'name_change',
    court: 'cook:cd1'
});
```

### Custom Validation
```javascript
const validation = getExpertFormInstance().getFormValidation();
validation.showNotification('Custom message', 'success');
```

### Court-Specific Configuration Examples
```javascript
// Check if a section should show for current court
const dynamicSections = getExpertFormInstance().getDynamicFormSections();
const shouldShow = dynamicSections.shouldShowSection(sectionConfig, 'bond');

// Trigger form re-rendering after court change
dynamicSections.handleCaseTypeChange();
```

## Performance Considerations

- Scripts load asynchronously after DOM ready
- API requests are cached where appropriate
- Loading spinners prevent multiple simultaneous requests
- Manual draft saving prevents excessive storage operations
- Court-specific form configurations are cached to reduce API calls
- Dynamic form sections only re-render when necessary (court or case type changes)

## Security Features

- CSRF token automatic inclusion
- XSS prevention through proper DOM manipulation
- Input validation on both client and server
- Secure localStorage usage for draft data
- YAML configuration validation prevents injection attacks

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
- Court-specific configuration loading
- Dynamic form section rendering decisions

## Troubleshooting

### Debug Commands
```javascript
// Check current form configuration
console.log(getExpertFormInstance().getDynamicFormSections().config);

// Check court-specific modifications
console.log(window.CascadingDropdowns.selectedValues);

// View current form data
console.log(getExpertFormInstance().getFormValidation().collectFormData());
```