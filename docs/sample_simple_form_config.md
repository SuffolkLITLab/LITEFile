
### Hypothetical Flow Config

The Filing Flow config language follows these design principles:

**Core Design Principles:**
- **Human-readable & diff-able**: YAML format enables version control and non-technical review
- **Declarative over imperative**: Describe what data to collect, not how to collect it
- **Composable building blocks**: Form Blocks are referenced by type with configuration
- **Session-aware**: Data flows through `session` namespace for mapping and reuse
- **Mapping separation**: Clear distinction between data collection and EFSP payload construction
- **No arbitrary code execution**: Logic is constrained to predefined patterns (conditionals, mappings)
- **Progressive disclosure**: Steps can be conditional based on previous answers

**Key Concepts:**
- **Form Blocks**: Reusable components (person_name, address, etc.) with built-in validation
- **Session data**: Structured storage accessible across steps via `session.field_name`
- **Conditional logic**: Simple `when` conditions using session data
- **Mapping layer**: Transforms session data to EFSP payload format
- **Instructions**: Plain-language guidance at flow and step levels

```yaml
# Illinois Adult Name Change - Cook County Filing Flow
# NOTE: this is hypothetical and collects more data than necessary for the real e-filing since we merge data from 
# the Tyler profile.
# NOTE: to match the actual wireframes, this simple flow should've allowed for adult or child. We'd need a form
# block with options ("Filing for myself", "Filing for my child") and to add a dependency link to the filing_type_lookup.
# The lookup would have a value mapping config to get the correct filing type based on the selected option via lookup.
# We'd also need to add more configuration on the form block that collects the name, etc.
metadata:
  title: "Illinois Adult Name Change"
  jurisdiction_state: "IL"
  jurisdiction_county: "Cook County"
  jurisdiction_court: "*"
  case_type: "name_change.adult"
  description: "Guided interview for filing an adult name change petition in Cook County"
  version: "1.0"
  
# Flow-level configuration
flow:
  # The next few values would likely be the defaults, so we wouldn't need to specify them.
  progress_bar: true
  allow_back: true
  session_timeout: 3600  # 1 hour
  # Request pre-fills and pre-mappings and helpers (which are then used to populate the session)
  title: "Adult Name Change Petition"

# Sequential steps in the filing flow
steps:
  - id: pre_fill
    form_block:
      type: api_pre_fill
      description: "Pre-populate session with data using API calls"
      api_calls:
        - type: 'court_lookup'
          inputs:
            # We show qualified name w/ session, which is a reserved prefix. Logic would check the session for a variable value if we don't have an exact match in the case where the prefix is omitted.
            - name: "{{ session.jurisdiction_court }}"
          # By default, will output session.court.name and session.court.code
        - type: 'category_lookup'
          inputs:
            # Also takes implicit inputs of court.code from session
            - name: "Miscellaneous"
          # By default, will output session.category.name and session.category.code
        - type: 'case_type_lookup'
          inputs:
            # Also takes implicit inputs of category.code from session
            - name: "Adult Name Change"
        - type: 'filing_type_lookup'
          inputs:
            # Also takes implicit inputs of category.code from session
            - name: "Petition for Name Change"
              # Index is used to disambiguate if there are multiple options with the same name. Assume ordering is stable.
              index: 0
              # By default, will output session.filing_type.code and session.filing_type.text

  - id: intro
    title: "Adult Name Change Petition"
    instruction: |
    This interview will help you file a petition to change your name in {{ jurisdiction }}.
    
    **You will need:**
    - Your current legal name and address
    - The new name you want to use
    - A completed petition form (PDF)
  - id: user_login
    title: "Sign In"
    instruction: "Please sign in to your Illinois eFile account to continue."
    form_block:
      type: user_authentication
      # This block will know to collect username & password, make the API call to Tyler, and populate the session with the user profile. From the profile, we get fields like session.user.name.first, session.user.name.last, session.user.address.street, etc.
      outputs:
        # Example of manually mapping fields (not actually needed; only illustrative)
        - map: 
          src: session.user.name.first
          to: session.petitioner.name.first
        - map: 
          src: session.user.name.last
          to: session.petitioner.name.last
        - map: 
          src: session.user.address.street
          to: session.petitioner.address.street
  # This step is illustrative only to show how we might ask for info. In the real flow, we would solely rely on the user profile.
  - id: current_name
    title: "Your Current Legal Name"
    instruction: "Enter your name exactly as it appears on your birth certificate or other legal documents."
    form_block:
      type: person_name
      config:
        prefix: "session.petitioner"

  - id: current_address
    title: "Your Current Address"
    instruction: "Provide your current residential address."
    form_block:
      type: address
      config:
        validate_usps: true
        prefix: "session.petitioner.address"

  - id: new_name
    title: "Your Requested Name Sought"
    instruction: "Enter the name sought you want to legally use."
    form_block:
      type: person_name
      config:
        # This shows off mapping from a different input set to the component specific fields (in this case, first_name, last_name, etc.). Then we map after collecting output by appending the output prefix, so first_name -> session.name_sought.first_name, etc.
        input_prefix: "session.user.name"
        output_prefix: "session.name_sought"
        tooltip: "This will be your new legal name after the court approves your petition."

  - id: document_upload
    title: "Upload Your Documents"
    instruction: |
      Upload your petition and any supporting documents. All documents must be in PDF format and clearly legible.
      
      **Document Requirements:**
      - **Format:** All documents must be in PDF format with text that can be read clearly
      - **Size Limit:** Each document must be under 10MB
    form_blocks:
      - type: document_upload
        label: "Lead Document"
        config:
          name: "name_change_petition"
          required: true
          file_types: ["pdf"]
          validate_form_filled: true
          max_size_mb: 10
          tooltip: "Your main petition document - this is the primary filing for your case."
      
      - type: select
        label: "Filing Component"
        config:
          populate_via_api:
            - type: "document_type_lookup"
              filters:
                - type: "name_match"
                  - value: "Lead Document"
          # Show off read-only components. This is populated via API and not modifyable by the user.
          readonly: true
        # Default output would be session.document_type.name and session.document_type.code
      
      # Populated by an API call
      - type: select
        label: "Document Type"
        config:
          required: true
          populate_via_api:
            - type: "document_type_lookup"
              filters:
                - type: "name_match"
                  - value: "Confidential"
                  - value: "Non-Confidential"
          order_by:
            # Alternative could be ordering by code, for example.
            field: "name"
      
      # Example of a more generic, low-level component.
      - type: checkbox
        label: "Request certified copies when filed"
        config:
          default: false
          output: session.filing.request_certified_copies

  - id: review
    title: "Review Case Details"
    type: review_step
    instruction: "Verify the information below for your case. Please edit anything you believe to be incorrect."
    review_sections:
      - title: "Case Information"
        fields:
          - label: "Filing Type"
            value: "{{ session.filing_type.text }}"
            editable: true
            edit_step: "pre_fill"
          - label: "Court"
            value: "{{ session.court.name }}"
            editable: true
            edit_step: "pre_fill"
          - label: "Category"
            value: "{{ session.category.name }}"
            editable: true
            edit_step: "pre_fill"
      
      - title: "Current Legal Name"
        fields:
          - label: "First Name"
            value: "{{ session.petitioner.first_name }}"
            editable: true
            edit_step: "current_name"
          - label: "Last Name"
            value: "{{ session.petitioner.last_name }}"
            editable: true
            edit_step: "current_name"
      
      - title: "Requested New Name"
        fields:
          - label: "First Name"
            value: "{{ session.name_sought.first_name }}"
            editable: true
            edit_step: "new_name"
          - label: "Last Name"
            value: "{{ session.name_sought.last_name }}"
            editable: true
            edit_step: "new_name"
      
      - title: "Current Address"
        fields:
          - label: "Street Address"
            value: "{{ session.petitioner.address.street }}"
            editable: true
            edit_step: "current_address"
          - label: "Unit/Apt"
            value: "{{ session.petitioner.address.unit }}"
            editable: true
            edit_step: "current_address"
          - label: "City"
            value: "{{ session.petitioner.address.city }}"
            editable: true
            edit_step: "current_address"
          - label: "State"
            value: "{{ session.petitioner.address.state }}"
            editable: true
            edit_step: "current_address"
          - label: "ZIP Code"
            value: "{{ session.petitioner.address.zip }}"
            editable: true
            edit_step: "current_address"
      
      - title: "Documents for Filing"
        fields:
          - label: "Lead Document"
            value: "{{ session.name_change_petition.filename }}"
            editable: true
            edit_step: "document_upload"
          - label: "Document Type"
            value: "{{ session.document_type.name }}"
            editable: true
            edit_step: "document_upload"
          - label: "Request Certified Copies"
            value: "{{ session.filing.request_certified_copies | yesno:'Yes,No' }}"
            editable: true
            edit_step: "document_upload"

# Post-submission configuration
completion:
  title: "Petition Submitted Successfully"
  message: |
    Your name change petition has been submitted to {{ jurisdiction }}.
    
    **Next Steps:**
    1. You will receive a confirmation email with your case number
    2. The court will review your petition (typically 2-4 weeks)
    3. If approved, you will receive a court order
    4. You can then use the court order to update your identification documents
```

**Future Improvements:**
This is a first draft at what a simple form flow config might look like. The system currently supports a smaller set of components and features, with correspondingly appropriate configs. There are additional areas that should get explored before settling on a better 1.0 config format. Some ideas include:
- **Internationalization & Localization**: Extract all text fields into separate YAML files (similar to translation files) to support multiple languages and/or jurisdictions w/ custom text
- **Configuration Inheritance**: More complex inheritance and override patterns for similar forms (e.g., Name Change - Child vs Name Change - Adult). YAML itself supports basic inheritance, but there might be additional features that would be nice or good to demonstrate.
- **Common Variables**: Similar to the translation files, we might want to define reusable shared constants as a separate file/section and reference them rather than inlining the full set of values in form block configs (e.g. `case_filter_set`)
- **Conditional Logic**: Support for more complex conditional logic. We'd lean towards declarative over scripting, and scripting over a rules engine, but all are viable options worth considering. This is necessary to support more complex flows beyond the simple linear flow in the sample.
- **Theming System**: Support for layout modifications and CSS. This hasn't been explored much yet, with the focus on logical flow and functional components.
- **Configuration Validation**: Build linter/checker tools to validate language files and data flow consistency on review screens
- **Dynamic Configuration**: Enable dynamic reload, scheduled updates/rollouts, and dependency checking for live configuration changes
- **Configuration Authoring Tools**: Provide wizard tools, cloning capabilities, templates, preview flow testing, and review workflow for creating new form configurations. An integrated AI assistant can be viable, especially if we can define the schema/patterns/best practices for flow configs and feed that in as context.
- **Landing Page Routing**: Support direct flow entry, allowing mapping of landing page URLs to specific flows for streamlined user experience
- **API Versioning**: Implement versioning strategy for configuration format evolution and backward compatibility

** Conditional Logic Candidates:**
- **Simple Conditional Display**: Use `show_if` field with basic equality checks for straightforward visibility rules.
- **Expression-Based Conditions**: Support script-like expressions (e.g., `"session.court.name == 'Cook County'"`) for flexible logic.
- **Complex Rule Objects**: Define structured rules with conditions, actions, and validation messages for comprehensive business logic.
- **Script Blocks**: Allow embedded code snippets for maximum flexibility in custom validation and data transformation.
- **Named Rule Engine**: Create reusable rule definitions that can be referenced across multiple form steps for consistency.
- **Hybrid Approach**: Some combination of the options above, defaulting to simpler config w/ the ability to use more complex logic when needed.