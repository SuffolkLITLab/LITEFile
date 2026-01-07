class DynamicFormSections {
  constructor() {
    // We create parties/services containers dynamically inside #dynamicSections
    this.caseInfoContainer = null; // will be created when needed
    this.partiesContainer = null; // will be created when needed
    this.partiesHeader = null; // will be created when needed
    this.servicesContainer = null; // will be created when needed
    this.dynamicSections = document.getElementById("dynamicSections");
    this.currentCaseType = null;
    this.config = null;
    this.preservedFormData = null;
    this.preservedCaseType = null;

    //this.init();
  }

  async init() {
    // Load configuration from server
    await this.loadConfiguration();

    // Load any existing case data from the session
    await this.loadExistingCaseData();

    // Listen for case type changes to trigger form section updates
    const caseTypeSelect = document.getElementById("case_type");
    if (caseTypeSelect) {
      caseTypeSelect.addEventListener("change", () => {
        this.handleCaseTypeChange();
      });

      // Also listen for when the dropdown is cleared/reset
      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.type === "childList" || mutation.type === "attributes") {
            // Check if dropdown was cleared
            if (
              caseTypeSelect.value === "" &&
              this.dynamicSections &&
              this.dynamicSections.style.display === "block"
            ) {
              this.hideDynamicSections();
            }
          }
        });
      });
      observer.observe(caseTypeSelect, {
        childList: true,
        attributes: true,
        attributeFilter: ["value"],
      });
    }

    // Listen for existing case changes to show/hide case information
    const existingCaseSelect = document.getElementById("existing_case");
    if (existingCaseSelect) {
      existingCaseSelect.addEventListener("change", () => {
        this.handleExistingCaseChange();
      });
    }

    // Listen for court changes to reload configuration with court-specific modifications
    const courtSelect = document.getElementById("court");
    if (courtSelect) {
      courtSelect.addEventListener("change", () => {
        // If we have a case type selected, reload the configuration and re-render
        if (caseTypeSelect && caseTypeSelect.value) {
          this.handleCaseTypeChange();
        }
      });
    }
  }

  async loadConfiguration() {
    try {
      // Get current court selection to include in the request
      const courtDropdown = document.getElementById("court");
      const caseTypeDropdown = document.getElementById("case_type");
      const court = courtDropdown ? courtDropdown.value : "";
      const caseTypeValue = caseTypeDropdown ? caseTypeDropdown.value : "";
      const caseTypeText =
        caseTypeDropdown && caseTypeDropdown.selectedIndex >= 0
          ? caseTypeDropdown.options[caseTypeDropdown.selectedIndex].text
          : "";

      // Only make API call if we have a case type (required parameter)
      if (!caseTypeValue || !caseTypeText) {
        this.config = this.getDefaultConfig();
        return;
      }

      // Use form-config endpoint which applies court-specific modifications
      let url = "/api/form-config/";
      const params = new URLSearchParams();

      params.append("case_type", caseTypeText); // Use text for keyword matching
      if (court) {
        params.append("court", court);
      }
      params.append("jurisdiction", "illinois"); // Default to Illinois

      url += "?" + params.toString();

      const response = await fetch(url);
      const result = await response.json();

      if (result.success && result.data) {
        // Transform the response to match the expected config structure
        this.config = {
          case_types: {},
          base_case_types: {},
        };

        // If we have sections, create a case type config structure
        if (
          result.data.sections &&
          Object.keys(result.data.sections).length > 0
        ) {
          // Determine if this is a base case type by checking common patterns
          const isBaseType =
            result.data.case_type_name &&
            (result.data.case_type_name.toLowerCase().includes("eviction") ||
              result.data.case_type_name
                .toLowerCase()
                .includes("repossession") ||
              result.data.case_type_name.toLowerCase().includes("restoration"));

          const caseConfig = {
            keywords: this.extractKeywordsFromCaseType(
              result.data.case_type_name
            ),
            sections: result.data.sections,
            description: result.data.description || "",
            validation_rules: result.data.validation_rules || [],
          };

          // Put eviction/repossession types in base_case_types, others in case_types
          if (isBaseType) {
            this.config.base_case_types.eviction_repossession = caseConfig;
          } else {
            this.config.case_types[
              result.data.case_type_name || "name_change"
            ] = caseConfig;
          }
        } else {
          // Also load the static base configuration to ensure we have eviction config
          await this.loadStaticBaseConfiguration();
        }
      } else {
        console.error(
          "Failed to load configuration:",
          result.error || "Unknown error"
        );
        this.config = this.getDefaultConfig();
        // Fallback: load static base configuration
        await this.loadStaticBaseConfiguration();
      }
    } catch (error) {
      console.error("Error loading configuration:", error);
      this.config = this.getDefaultConfig();
      // Fallback: load static base configuration
      await this.loadStaticBaseConfiguration();
    }
  }

  // Helper method to extract keywords from case type name
  extractKeywordsFromCaseType(caseTypeName) {
    if (!caseTypeName) return [];
    const name = caseTypeName.toLowerCase();
    if (name.includes("eviction") || name.includes("repossession")) {
      return ["eviction", "repossession", "restoration"];
    }
    if (name.includes("name") && name.includes("change")) {
      return ["name change", "name petition", "change of name"];
    }
    return [caseTypeName.toLowerCase()];
  }

  // Load static base configuration as fallback
  async loadStaticBaseConfiguration() {
    try {
      // Try to load the static base-case-types.yaml configuration
      const response = await fetch("/static/config/base-case-types.yaml");
      if (response.ok) {
        const yamlText = await response.text();
        // This is a simplified YAML parser - in production you'd want a proper YAML library
        // For now, just ensure we have the base case types available
        this.config.base_case_types = this.config.base_case_types || {};
      }
    } catch (error) {
      console.warn("Could not load static base configuration:", error);
    }
  }

  async loadExistingCaseData() {
    try {
      // Check if there's an API endpoint to retrieve saved case data
      const response = await fetch("/api/get-case-data/", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const result = await response.json();
        if (
          result.success &&
          result.data &&
          Object.keys(result.data).length > 0
        ) {
          this.restorationData = result.data;

          // Also make it available for form validation system
          if (window.formValidation) {
            window.formValidation.restorationData = result.data;
          }
        }
      }
    } catch (error) {
      console.warn("Could not load existing case data:", error);
      // This is not a critical error, continue without saved data
    }
  }

  getDefaultConfig() {
    // Fallback configuration if server config fails
    return {
      case_types: {
        name_change: {
          keywords: ["name change"],
          sections: {
            parties: {
              title: "Required parties",
              fields: [
                {
                  section_title: "Petitioner",
                  required: true,
                  fields: [
                    {
                      name: "petitioner_first_name",
                      label: "First Name",
                      type: "text",
                      required: true,
                      column_width: "col-md-6",
                    },
                    {
                      name: "petitioner_last_name",
                      label: "Last Name",
                      type: "text",
                      required: true,
                      column_width: "col-md-6",
                    },
                  ],
                },
              ],
            },
          },
        },
      },
      base_case_types: {},
    };
  }

  async handleCaseTypeChange() {
    const caseTypeSelect = document.getElementById("case_type");

    if (!caseTypeSelect) {
      return;
    }

    const caseTypeText =
      caseTypeSelect.options[caseTypeSelect.selectedIndex]?.text || "";
    const caseTypeValue = caseTypeSelect.value;

    // Don't hide sections immediately if the dropdown is being cleared - give time for restoration
    if (!caseTypeValue) {
      // Check if this is a temporary clearing (cascading dropdown coordination)
      const isBeingCleared =
        caseTypeSelect.disabled ||
        window.cascadingDropdowns?.optionalServicesLoaded === false;

      if (isBeingCleared) {
        // Set a timeout to check again later
        setTimeout(() => {
          if (!caseTypeSelect.value && caseTypeSelect.options.length <= 1) {
            this.hideDynamicSections();
          } else if (caseTypeSelect.value) {
            this.handleCaseTypeChange();
          }
        }, 1000); // Wait 1 second for cascading system to restore values
        return;
      } else {
        this.hideDynamicSections();
        return;
      }
    }

    // Reload configuration with current court and case type to get court-specific modifications
    await this.loadConfiguration();

    if (!this.config) {
      return;
    }

    const caseTypeConfig = this.findCaseTypeConfig(caseTypeText);

    if (caseTypeConfig) {
      this.currentCaseType = caseTypeValue; // Track the current case type
      //this.renderCaseTypeForm(caseTypeConfig);
      //this.showDynamicSections();
    } else {
      //this.hideDynamicSections();
    }
  }

  handleExistingCaseChange() {
    const existingCaseSelect = document.getElementById("existing_case");
    if (!existingCaseSelect) {
      return;
    }

    const existingCaseValue = existingCaseSelect.value;
    
    // Show/hide case information section based on existing case selection
    if (this.caseInfoContainer) {
      if (existingCaseValue === "yes") {
        // Show case information section
        this.caseInfoContainer.style.display = "block";
        // Also show the header if it exists
        const caseInfoHeader = this.caseInfoContainer.previousElementSibling;
        if (caseInfoHeader && caseInfoHeader.tagName === "H3") {
          caseInfoHeader.style.display = "block";
        }
      } else {
        // Hide case information section
        this.caseInfoContainer.style.display = "none";
        // Also hide the header if it exists
        const caseInfoHeader = this.caseInfoContainer.previousElementSibling;
        if (caseInfoHeader && caseInfoHeader.tagName === "H3") {
          caseInfoHeader.style.display = "none";
        }
      }
    }
  }

  findCaseTypeConfig(caseTypeText) {
    const lowerCaseText = caseTypeText.toLowerCase();

    // Also try to match by dropdown value if text matching fails
    const caseTypeSelect = document.getElementById("case_type");
    const caseTypeValue = caseTypeSelect ? caseTypeSelect.value : "";

    // Search both case_types and base_case_types sections
    const caseTypeSources = [
      this.config.case_types || {},
      this.config.base_case_types || {},
    ];

    for (const caseTypes of caseTypeSources) {
      for (const [configKey, caseConfig] of Object.entries(caseTypes)) {
        const keywords = caseConfig.keywords || [];

        // Method 1: Check if any keyword matches the case type text
        const matchingKeyword = keywords.find((keyword) => {
          const lowerKeyword = keyword.toLowerCase();
          const matches = lowerCaseText.includes(lowerKeyword);
          return matches;
        });

        if (matchingKeyword) {
          return caseConfig;
        }

        // Method 2: Direct config key matching (fallback)
        if (
          configKey === "name_change" &&
          (lowerCaseText.includes("name") ||
            lowerCaseText.includes("change") ||
            caseTypeValue.toLowerCase().includes("name"))
        ) {
          return caseConfig;
        }

        // Method 3: Check for eviction case type
        if (
          configKey === "eviction_repossession" &&
          (lowerCaseText.includes("eviction") ||
            lowerCaseText.includes("repossession") ||
            lowerCaseText.includes("restoration"))
        ) {
          return caseConfig;
        }
      }
    }

    // Method 4: If no match found, try some common patterns
    if (lowerCaseText.includes("name") && lowerCaseText.includes("change")) {
      if (this.config.case_types && this.config.case_types.name_change) {
        return this.config.case_types.name_change;
      }
      if (
        this.config.base_case_types &&
        this.config.base_case_types.name_change
      ) {
        return this.config.base_case_types.name_change;
      }
    }

    return null;
  }

  renderCaseTypeForm(caseTypeConfig) {
    this.preserveCurrentState();

    const sections = caseTypeConfig.sections || {};

    // Render case information section (should come first)
    if (sections.case_information) {
      this.renderSection("case_information", sections.case_information);
    }

    // Render parties section
    if (sections.parties) {
      this.renderSection("parties", sections.parties);
    }

    // Render services section
    if (sections.services) {
      this.renderSection("services", sections.services);
    }

    // Restore preserved state after rendering
    this.restorePreservedState();

    // Load party type dropdowns after all sections are rendered
    //this.loadPartyTypeDropdowns();

    // Update form validation after rendering
    this.updateFormValidation();

    // Check if there's restoration data from form validation that needs to be applied
    if (this.restorationData) {
      //setTimeout(() => {
        this.populateRenderedFields(this.restorationData);
        this.restorationData = null; // Clear after use
      //}, 50);
    }

    // Notify form validation system that dynamic fields have been rendered
    setTimeout(() => {
      if (window.formValidation && window.formValidation.restorationData) {
        window.formValidation.populateDynamicFields(
          window.formValidation.restorationData
        );
      }
      
      // Check existing case selection to show/hide case information appropriately
      this.handleExistingCaseChange();
    }, 100);
  }

  renderSection(sectionType, sectionConfig) {
    // Ensure containers exist inside the dynamicSections wrapper
    if (!this.dynamicSections) {
      return;
    }

    if (sectionType === "case_information") {
      if (!this.caseInfoContainer) {
        // Create header and container for case information
        const header = document.createElement("h3");
        header.className = "subsection-header";
        header.textContent = sectionConfig.title || "Case Information";

        const containerDiv = document.createElement("div");
        containerDiv.id = "caseInfoContainer";

        this.dynamicSections.appendChild(header);
        this.dynamicSections.appendChild(containerDiv);
        this.caseInfoContainer = containerDiv;

        // Initially hide case information section - only show when existing_case = "yes"
        header.style.display = "none";
        containerDiv.style.display = "none";
      }
    } else if (sectionType === "parties") {
      if (!this.partiesContainer) {
        // Create header and container for parties
        const header = document.createElement("h3");
        header.className = "subsection-header";
        header.textContent = sectionConfig.title || "Required Parties";

        const containerDiv = document.createElement("div");
        containerDiv.id = "partiesContainer";

        this.dynamicSections.appendChild(header);
        this.dynamicSections.appendChild(containerDiv);
        this.partiesContainer = containerDiv;
        this.partiesHeader = header; // Store reference to header for visibility control
      }
    } else if (sectionType === "services") {
      if (!this.servicesContainer) {
        const containerDiv = document.createElement("div");
        containerDiv.id = "servicesContainer";
        this.dynamicSections.appendChild(containerDiv);
        this.servicesContainer = containerDiv;
      }
    }

    const container =
      sectionType === "case_information"
        ? this.caseInfoContainer
        : sectionType === "parties"
        ? this.partiesContainer
        : this.servicesContainer;

    let html = "";

    if (sectionType === "case_information") {
      html = this.renderCaseInformationSection(sectionConfig);
    } else if (sectionType === "parties") {
      html = this.renderPartiesSection(sectionConfig);
    } else if (sectionType === "services") {
      html = this.renderServicesSection(sectionConfig);
    }

    container.innerHTML = html;

    // Special handling for parties section - hide header if no content
    if (sectionType === "parties" && this.partiesHeader) {
      if (html.trim() === "") {
        // No parties sections were rendered, hide the header
        this.partiesHeader.style.display = "none";
      } else {
        // There is content, show the header
        this.partiesHeader.style.display = "block";
      }
    }

    // Note: loadPartyTypeDropdowns() and updateFormValidation() are called 
    // once after all sections are rendered in renderCaseTypeForm()
  }

  renderCaseInformationSection(sectionConfig) {
    // Case information has the same nested structure as parties: section_title -> fields
    const sectionGroups = sectionConfig.fields || [];

    let html = "";

    // Iterate through each section group (like "Case Details")
    sectionGroups.forEach((sectionGroup) => {
      if (sectionGroup.section_title) {
        // Check if this section should be required
        const isRequired = sectionGroup.required || false;
        const requiredIndicator = isRequired
          ? '<span class="required">*</span>'
          : "";
        const optionalIndicator = !isRequired
          ? '<span class="optional">(Optional)</span>'
          : "";

        html += `<div class="party-section">
                    <div class="party-title">${sectionGroup.section_title} ${requiredIndicator} ${optionalIndicator}</div>`;

        if (sectionGroup.fields && sectionGroup.fields.length > 0) {
          html += '<div class="row mb-3">';

          // Render each field in this section
          sectionGroup.fields.forEach((field) => {
            if (field && field.name && field.type) {
              // Update field requirement based on section requirement
              const updatedField = {
                ...field,
                required: field.required && isRequired,
              };
              html += this.renderField(updatedField);
            } else {
              console.warn("⚠️ Invalid field structure:", field);
            }
          });

          html += "</div>";
        }

        html += "</div>";
      }
    });

    return html;
  }

  renderPartiesSection(sectionConfig) {
    const fields = sectionConfig.fields || [];
    let html = "";

    fields.forEach((partyGroup) => {
      if (partyGroup.section_title) {
        // Check if this section should be shown based on current court selection
        const shouldShow = this.shouldShowSection(partyGroup);

        // Skip rendering this section entirely if it shouldn't be shown
        if (!shouldShow) {
          return;
        }

        // Check if this section should be required based on current court selection
        const isRequired = this.evaluateConditionalRequirement(partyGroup);
        const requiredIndicator = isRequired
          ? '<span class="required">*</span>'
          : "";

        // Add optional indicator if not required
        const optionalIndicator = !isRequired
          ? '<span class="optional">(Optional)</span>'
          : "";

        html += `<div class="party-section">
                    <div class="party-title">${partyGroup.section_title} ${requiredIndicator} ${optionalIndicator}</div>`;

        if (partyGroup.fields && partyGroup.fields.length > 0) {
          html += '<div class="row mb-3">';

          partyGroup.fields.forEach((field) => {
            // Update field requirement based on section requirement
            const updatedField = {
              ...field,
              required: field.required && isRequired,
            };
            html += this.renderField(updatedField);
          });

          html += "</div>";
        }

        html += "</div>";
      }
    });

    return html;
  }

  shouldShowSection(partyGroup) {
    // If no conditional requirements defined, show by default
    if (!partyGroup.conditional_requirements) {
      return true;
    }

    // Get current court selection
    const courtDropdown = document.getElementById("court");
    const selectedCourt = courtDropdown ? courtDropdown.value : null;

    if (!selectedCourt) {
      // No court selected yet, show by default
      return true;
    }

    const conditionalReqs = partyGroup.conditional_requirements;

    // Check if current court is in hidden_for_courts list
    if (
      conditionalReqs.hidden_for_courts &&
      conditionalReqs.hidden_for_courts.includes(selectedCourt)
    ) {
      return false;
    }

    // Check if current court is in required_for_courts list (should show)
    if (
      conditionalReqs.required_for_courts &&
      conditionalReqs.required_for_courts.includes(selectedCourt)
    ) {
      return true;
    }

    // Check if current court is in optional_for_courts list (should show but optional)
    if (
      conditionalReqs.optional_for_courts &&
      conditionalReqs.optional_for_courts.includes(selectedCourt)
    ) {
      return true;
    }

    // Check county-based requirements (extract county from court code)
    if (
      conditionalReqs.required_for_counties ||
      conditionalReqs.optional_for_counties
    ) {
      const county = this.extractCountyFromCourt(selectedCourt);

      if (
        conditionalReqs.required_for_counties &&
        conditionalReqs.required_for_counties.includes(county)
      ) {
        return true;
      }

      if (
        conditionalReqs.optional_for_counties &&
        conditionalReqs.optional_for_counties.includes(county)
      ) {
        return true;
      }
    }

    // For "Name Sought" section, hide by default for all other courts
    if (
      partyGroup.section_title &&
      partyGroup.section_title.toLowerCase().includes("name sought")
    ) {
      return false;
    }

    // If we have conditional requirements but the current court isn't explicitly listed,
    // default to showing for "Petitioner" and hiding for other sections
    if (
      partyGroup.section_title &&
      partyGroup.section_title.toLowerCase().includes("petitioner")
    ) {
      return true; // Show Petitioner by default unless explicitly hidden
    }

    // For all other sections with conditional requirements, hide by default
    return false;
  }

  evaluateConditionalRequirement(partyGroup) {
    // If no conditional requirements defined, use default required value
    if (!partyGroup.conditional_requirements) {
      return partyGroup.required || false;
    }

    // Get current court selection
    const courtDropdown = document.getElementById("court");
    const selectedCourt = courtDropdown ? courtDropdown.value : null;

    if (!selectedCourt) {
      // No court selected yet, default to base required value
      return partyGroup.required || false;
    }

    const conditionalReqs = partyGroup.conditional_requirements;

    // Check if current court is in required_for_courts list
    if (
      conditionalReqs.required_for_courts &&
      conditionalReqs.required_for_courts.includes(selectedCourt)
    ) {
      return true;
    }

    // Check if current court is in optional_for_courts list
    if (
      conditionalReqs.optional_for_courts &&
      conditionalReqs.optional_for_courts.includes(selectedCourt)
    ) {
      return false;
    }

    // Check county-based requirements (extract county from court code)
    if (
      conditionalReqs.required_for_counties ||
      conditionalReqs.optional_for_counties
    ) {
      const county = this.extractCountyFromCourt(selectedCourt);

      if (
        conditionalReqs.required_for_counties &&
        conditionalReqs.required_for_counties.includes(county)
      ) {
        return true;
      }

      if (
        conditionalReqs.optional_for_counties &&
        conditionalReqs.optional_for_counties.includes(county)
      ) {
        return false;
      }
    }

    // Default to base required value if no specific rules match
    return partyGroup.required || false;
  }

  extractCountyFromCourt(courtCode) {
    // Handle court codes like "cook:cd1" -> "cook"
    if (courtCode.includes(":")) {
      return courtCode.split(":")[0];
    }

    // Handle direct county codes like "dupage", "kane"
    return courtCode.toLowerCase();
  }

  renderServicesSection(sectionConfig) {
    const fields = sectionConfig.fields || [];
    let html = '<div class="checkbox-group">';

    fields.forEach((field) => {
      if (field.type === "checkbox") {
        html += `
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" 
                               id="${field.name}" 
                               name="${field.group || "services"}" 
                               value="${field.value || field.name}">
                        <label class="form-check-label" for="${field.name}">
                            ${field.label}
                        </label>
                    </div>`;
      }
    });

    html += "</div>";
    return html;
  }

  renderField(field) {
    if (!field || typeof field !== "object") {
      return '<div class="col-12"><p class="text-danger">Error: Invalid field configuration</p></div>';
    }

    const columnClass = field.column_width || "col-12";
    const requiredAttr = field.required ? "required" : "";
    const placeholderAttr = field.placeholder
      ? `placeholder="${field.placeholder}"`
      : "";
    const fieldId = field.name || "unknown";
    const fieldName = field.name || "unknown";

    let inputHtml = "";

    switch (field.type) {
      case "text":
        inputHtml = `<input type="text" class="form-control" id="${fieldId}" name="${fieldName}" ${placeholderAttr} ${requiredAttr}>`;
        break;

      case "textarea":
        inputHtml = `<textarea class="form-control" id="${fieldId}" name="${fieldName}" rows="3" ${requiredAttr}></textarea>`;
        break;

      case "number":
        const minAttr = field.min ? `min="${field.min}"` : "";
        const maxAttr = field.max ? `max="${field.max}"` : "";
        const stepAttr = field.step ? `step="${field.step}"` : "";
        inputHtml = `<input type="number" class="form-control" id="${fieldId}" name="${fieldName}" ${minAttr} ${maxAttr} ${stepAttr} ${requiredAttr}>`;
        break;

      case "email":
        inputHtml = `<input type="email" class="form-control" id="${fieldId}" name="${fieldName}" ${requiredAttr}>`;
        break;

      case "tel":
        inputHtml = `<input type="tel" class="form-control" id="${fieldId}" name="${fieldName}" ${requiredAttr}>`;
        break;

      case "party_type_dropdown":
        // Create a dropdown for party types that will be populated via API
        inputHtml = `
                    <select class="form-select party-type-dropdown" 
                            id="${fieldId}" 
                            name="${fieldName}" 
                            data-api-endpoint="${
                              field.api_endpoint ||
                              "/api/dropdowns/party-types/"
                            }"
                            ${requiredAttr}>
                        <option value="">Select PParty Type</option>
                    </select>
                    <div class="loading-spinner" id="loading-${fieldId}" style="display: none;">
                        <i class="fas fa-spinner fa-spin"></i> Loading party types...
                    </div>`;
        break;

      default:
        inputHtml = `<input type="text" class="form-control" id="${fieldId}" name="${fieldName}" ${requiredAttr}>`;
    }

    const helpText = field.help_text
      ? `<div class="form-text">${field.help_text}</div>`
      : "";
    const fieldLabel = field.label || field.name || "Field";

    return `
            <div class="${columnClass}">
                <label for="${fieldId}" class="form-label">${fieldLabel}</label>
                ${inputHtml}
                ${helpText}
            </div>`;
  }

  async loadPartyTypeDropdowns() {
    // Find all party type dropdowns in the rendered sections
    const partyTypeDropdowns = document.querySelectorAll(
      ".party-type-dropdown"
    );

    if (partyTypeDropdowns.length === 0) {
      return;
    }

    partyTypeDropdowns.forEach(async (dropdown) => {
      const fieldId = dropdown.id;
      const apiEndpoint =
        dropdown.dataset.apiEndpoint || "/api/dropdowns/party-types/";
      let defaultValue = dropdown.dataset.defaultValue || "";

      // Check for saved case data first (highest priority)
      if (
        window.formValidation &&
        window.formValidation.restorationData &&
        window.formValidation.restorationData[fieldId]
      ) {
        defaultValue = window.formValidation.restorationData[fieldId];
      }
      // Check for restoration data from preserved form state
      else if (this.restorationData && this.restorationData[fieldId]) {
        defaultValue = this.restorationData[fieldId];
      }
      // Check for preserved form data
      else if (this.preservedFormData && this.preservedFormData[fieldId]) {
        defaultValue = this.preservedFormData[fieldId];
      }

      // Show loading spinner
      const loadingSpinner = document.getElementById(`loading-${fieldId}`);
      if (loadingSpinner) {
        loadingSpinner.style.display = "block";
      }

      try {
        // Get current form values for court and case_type
        const courtSelect = document.getElementById("court");
        const caseTypeSelect = document.getElementById("case_type");

        const court = courtSelect ? courtSelect.value : "";
        const caseType = caseTypeSelect ? caseTypeSelect.value : "";

        if (!court || !caseType) {
          if (loadingSpinner) loadingSpinner.style.display = "none";
          return;
        }

        // Build API URL with parameters
        const url = new URL(apiEndpoint, window.location.origin);
        url.searchParams.append("court", court);
        url.searchParams.append("case_type", caseType);

        const response = await fetch(url);
        const result = await response.json();

        if (result.success && result.data && result.data.party_types) {
          const partyTypes = result.data.party_types;

          // Clear existing options except the first one
          dropdown.innerHTML = '<option value="">Select Party Type</option>';

          // If no saved data, try to find intelligent default from API response
          if (!defaultValue) {
            // Find the parent section title
            const partySection = dropdown.closest(".party-section");
            if (partySection) {
              const titleElement = partySection.querySelector(".party-title");
              if (titleElement) {
                const sectionTitle = titleElement.textContent
                  .toLowerCase()
                  .replace(/\s*\*\s*$/, "")
                  .replace(/\s*\(optional\)\s*$/i, "")
                  .trim();

                // Find party type that matches the section title
                const matchingPartyType = partyTypes.find((partyType) => {
                  const partyName = partyType.name.toLowerCase();
                  return (
                    partyName.includes(sectionTitle) ||
                    sectionTitle.includes(partyName.split(" ")[0]) ||
                    (sectionTitle === "name sought" &&
                      partyName.includes("name")) ||
                    (sectionTitle === "petitioner" &&
                      partyName.includes("petitioner")) ||
                    (sectionTitle === "defendant" &&
                      partyName.includes("defendant")) ||
                    (sectionTitle === "plaintiff" &&
                      partyName.includes("plaintiff")) ||
                    (sectionTitle === "respondent" &&
                      partyName.includes("respondent"))
                  );
                });

                if (matchingPartyType) {
                  defaultValue = matchingPartyType.code;
                }
              }
            }
          }

          // Add all party type options
          let addedCount = 0;
          partyTypes.forEach((partyType) => {
            const option = document.createElement("option");
            option.value = partyType.code;
            option.textContent = partyType.name;
            // Set as selected if this is the default value
            if (partyType.code === defaultValue) {
              option.selected = true;
            }

            dropdown.appendChild(option);
            addedCount++;
          });
        } else {
          console.error(
            "Failed to load party types:",
            result.error || "Unknown error",
            result
          );

          // Add error option
          dropdown.innerHTML =
            '<option value="">Error loading party types</option>';
        }
      } catch (error) {
        console.error(`Error loading party types for ${fieldId}:`, error);

        // Add error option
        dropdown.innerHTML =
          '<option value="">Error loading party types</option>';
      } finally {
        // Hide loading spinner
        if (loadingSpinner) {
          loadingSpinner.style.display = "none";
        }
      }
    });
  }

  showDynamicSections() {
    if (this.dynamicSections) {
      this.dynamicSections.style.display = "block";

      // Also verify content was rendered
      const partiesContent = this.partiesContainer
        ? this.partiesContainer.innerHTML.trim()
        : "";
      const servicesContent = this.servicesContainer
        ? this.servicesContainer.innerHTML.trim()
        : "";

      if (partiesContent.length === 0 && servicesContent.length === 0) {
        console.warn("Dynamic sections shown but no content rendered!");
      }
    } else {
    }
  }

  hideDynamicSections() {
    if (this.dynamicSections) {
      this.dynamicSections.style.display = "none";
    } else {
    }

    // Add a timeout to prevent immediate clearing race conditions
    setTimeout(() => {
      this.clearContainers();
    }, 50);
  }

  // Add a method to preserve current form state during dropdown changes
  preserveCurrentState() {
    if (this.currentCaseType) {
      const currentConfig = this.findCaseTypeConfig(this.currentCaseType);
      if (currentConfig) {
        // Store current form values
        const formData = {};
        const dynamicFields = this.getAllDynamicFieldNames();
        dynamicFields.forEach((fieldName) => {
          const field = document.querySelector(`[name="${fieldName}"]`);
          if (field) {
            if (field.type === "checkbox") {
              formData[fieldName] = field.checked;
            } else {
              formData[fieldName] = field.value;
            }
          }
        });
        this.preservedFormData = formData;
        this.preservedCaseType = this.currentCaseType;
      }
    }
  }

  // Method to restore preserved state
  restorePreservedState() {
    if (
      this.preservedFormData &&
      this.preservedCaseType === this.currentCaseType
    ) {
      setTimeout(() => {
        Object.keys(this.preservedFormData).forEach((fieldName) => {
          const field = document.querySelector(`[name="${fieldName}"]`);
          if (field) {
            if (field.type === "checkbox") {
              field.checked = this.preservedFormData[fieldName];
            } else {
              field.value = this.preservedFormData[fieldName];
            }
          }
        });
        // Clear preserved data after restoration
        this.preservedFormData = null;
        this.preservedCaseType = null;
      }, 100);
    }
  }

  clearContainers() {
    if (this.caseInfoContainer) {
      this.caseInfoContainer.innerHTML = "";
    }
    if (this.partiesContainer) {
      this.partiesContainer.innerHTML = "";
    }
    if (this.partiesHeader) {
      this.partiesHeader.style.display = "none";
    }
    if (this.servicesContainer) {
      this.servicesContainer.innerHTML = "";
    }
  }

  updateFormValidation() {
    // Re-initialize form validation to include dynamically added fields
    if (window.FormValidation && window.formValidation) {
      // Find all required fields in the form
      const form = document.querySelector("#expertForm");
      if (form) {
        window.formValidation.requiredFields =
          form.querySelectorAll("[required]");

        // Populate dynamic fields if restoration data is available
        if (window.formValidation.restorationData) {
          setTimeout(() => {
            this.populateRenderedFields(window.formValidation.restorationData);
          }, 100);
        }
      }
    }
  }

  populateRenderedFields(data) {
    // Get all dynamic fields that were just rendered
    const dynamicFields = this.getAllDynamicFieldNames();

    let fieldsPopulated = 0;

    console.log("%o", data);
    dynamicFields.forEach((key) => {
      console.log("key: %s", key);
      if (data[key]) {
        const field = document.querySelector(`[name="${key}"]`);
        if (field) {
          if (field.type === "checkbox") {
            field.checked = Array.isArray(data[key])
              ? data[key].includes(field.value)
              : data[key] === field.value;
          } else if (field.classList.contains("party-type-dropdown")) {
            // For party type dropdowns, we may need to wait for options to load
            const setDropdownValue = () => {
              // Check if the option exists
              const option = field.querySelector(
                `option[value="${data[key]}"]`
              );
              if (option) {
                field.value = data[key];

                // Add visual validation feedback after successful population
                field.classList.remove("is-invalid");
                field.classList.add("is-valid");
              } else if (field.options.length <= 1) {
                // Options haven't loaded yet, wait a bit longer
                setTimeout(setDropdownValue, 500);
              }
            };
            setDropdownValue();
          } else {
            field.value = data[key];
          }
          fieldsPopulated++;

          // Add visual validation feedback (but not for dropdowns until they're populated)
          if (
            field.value &&
            field.value.trim() &&
            !field.classList.contains("party-type-dropdown")
          ) {
            field.classList.remove("is-invalid");
            field.classList.add("is-valid");
          }
        }
      }
    });

    return fieldsPopulated;
  }

  getAllDynamicFieldNames() {
    // Get all field names from currently rendered dynamic content
    const allFields = [];

    if (this.caseInfoContainer) {
      const fields = this.caseInfoContainer.querySelectorAll("[name]");
      fields.forEach((field) => allFields.push(field.name));
    }

    if (this.partiesContainer) {
      const fields = this.partiesContainer.querySelectorAll("[name]");
      fields.forEach((field) => allFields.push(field.name));
    }

    if (this.servicesContainer) {
      const fields = this.servicesContainer.querySelectorAll("[name]");
      fields.forEach((field) => allFields.push(field.name));
    }

    return [...new Set(allFields)]; // Remove duplicates
  }

  // Method to be called from form validation when restoration data is available
  restoreDynamicFieldData(data) {
    if (!data || Object.keys(data).length === 0) {
      return;
    }

    // Store the data for later restoration
    this.restorationData = data;

    // If dynamic sections are already visible, populate immediately
    if (
      this.dynamicSections &&
      this.dynamicSections.style.display === "block"
    ) {
      this.populateRenderedFields(data);
    }
  }
}

// Initialize when DOM is loaded
function initializeDynamicFormSections() {
  if (!window.dynamicFormSections) {
    window.dynamicFormSections = new DynamicFormSections();
  }
}

// Try multiple initialization approaches
if (document.readyState === "loading") {
  // DOM is still loading
  document.addEventListener("DOMContentLoaded", initializeDynamicFormSections);
} else {
  // DOM is already loaded
  initializeDynamicFormSections();
}

// Also make the class available globally for manual instantiation
window.DynamicFormSections = DynamicFormSections;

// Export for use in other modules
if (typeof module !== "undefined" && module.exports) {
  module.exports = DynamicFormSections;
}
