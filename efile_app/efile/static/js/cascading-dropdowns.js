/**
 * CascadingDropdowns - Handles smart form dropdown interactions
 * Features: Location-based recommendations, court-specific filtering, progressive form enablement
 */
class CascadingDropdowns {
    constructor() {
        this.dropdownMapping = {
            court: {
                next: "case_category",
                endpoint: "/api/dropdowns/case-categories/",
            },
            case_category: {
                next: "case_type",
                endpoint: "/api/dropdowns/case-types/",
            },
            case_type: {
                next: "party_type", // Case type is now the final dropdown on expert form
                endpoint: "/api/dropdowns/party-types",
            },
            party_type: {
                next: null,
                endpoint: null
            }
        };

        this.userProfile = null;
        this.selectedValues = {
            court: null,
            case_category: null,
            case_type: null,
            party_type: null,
        };
        // A new filing has no uploaded document yet, so the upload-data
        // response may not contain document classification guesses.
        this.guesses = {};
        this.optionalServicesLoaded = false;
        this.isAutomaticSelection = false; // Track if selection is automatic
    }

    async init() {
        // Load user profile first
        await this.loadUserProfile();
        await this.loadGuesses();

        // Load initial data for independent dropdowns with user context
        await this.loadCourtsWithUserContext();

        // Add event listeners
        document.addEventListener("change", (e) => {
            if (e.target.classList.contains("dropdown-field")) {
                this.handleDropdownChange(e.target);
            }
        });
    }

    async loadCourtsWithUserContext() {
        const params = {};
        const currentJurisdiction = apiUtils.getCurrentJurisdiction();

        // Set the jurisdiction parameter
        params.jurisdiction = currentJurisdiction;
        params.guessed_court = this.guesses?.court;

        // For Massachusetts, skip location-based filtering and show all courts
        if (currentJurisdiction === 'massachusetts') {
            await this.loadDropdownData("court", "/api/dropdowns/courts/", params);
            return;
        }

        // For other jurisdictions (like Illinois), use location-based recommendations
        if (this.userProfile) {
            // Pass user location info to courts API
            if (this.userProfile.preferred_county) {
                params.user_county = this.userProfile.preferred_county;
            }
            if (this.userProfile.zip_code) {
                params.user_zip = this.userProfile.zip_code;
            }
            // Add jurisdiction if available from profile
            if (this.userProfile.state) {
                const jurisdictionMap = {
                    IL: "illinois",
                    Illinois: "illinois",
                };
                const profileJurisdiction = jurisdictionMap[this.userProfile.state] || "illinois";
                // Only override if current jurisdiction matches profile
                if (currentJurisdiction === "illinois" || !currentJurisdiction) {
                    params.jurisdiction = profileJurisdiction;
                }
            }
        } else {
            console.warn("No user profile available for courts loading");
        }
        await this.loadDropdownData("court", "/api/dropdowns/courts/", params);
    }

    async loadUserProfile() {
        const statusElement = document.getElementById("userProfileStatus");

        try {
            if (statusElement) {
                statusElement.style.display = "block";
                statusElement.innerHTML =
                    '<i class="fas fa-spinner fa-spin"></i> Loading your information...';
            }

            const response = await this.makeRequest("/api/auth/profile/", {
                "jurisdiction": apiUtils.getCurrentJurisdiction()
            });

            if (response.success) {
                if (statusElement) {
                    statusElement.style.display = "none";
                }
                this.userProfile = response.data;
            } else {
                console.warn("❌ Failed to load user profile:", response.error);
                if (statusElement) {
                    statusElement.className = "alert alert-warning";
                    statusElement.innerHTML =
                        '<i class="fas fa-exclamation-triangle"></i> Could not load profile information. Using default settings.';
                    setTimeout(() => {
                        statusElement.style.display = "none";
                    }, 3000);
                }
            }
        } catch (error) {
            console.error("❌ Error loading user profile:", error);
            if (statusElement) {
                statusElement.className = "alert alert-warning";
                statusElement.innerHTML =
                    '<i class="fas fa-exclamation-triangle"></i> Could not load profile information. Using default settings.';
                setTimeout(() => {
                    statusElement.style.display = "none";
                }, 3000);
            }
        }
    }

    async loadGuesses() {
        try {
            const data = await apiUtils.getUploadData();
            this.guesses = data?.guesses || {};
        } catch (error) {
            // Guesses are optional and should never prevent a new filing from
            // using the cascading dropdowns.
            console.warn("Could not load upload guesses:", error);
            this.guesses = {};
        }
    }

    async loadDropdownData(fieldId, endpoint, params = {}) {
        const dropdown = document.getElementById(fieldId);

        if (!dropdown) {
            console.error(`Dropdown with ID '${fieldId}' not found in DOM`);
            return;
        }

        const loader = document.getElementById(`loading-${dropdown.dataset.level}`);

        try {
            this.showLoader(loader);
            this.clearDropdown(dropdown);

            const response = await this.makeRequest(endpoint, params);

            if (response.success) {
                // Check if we have valid data
                if (
                    response.data &&
                    Array.isArray(response.data) &&
                    response.data.length > 0
                ) {
                    this.populateDropdown(dropdown, response.data);
                    dropdown.parentElement.removeAttribute("hidden");
                    dropdown.disabled = false;
                    if (response.data.length == 1 && dropdown.id == "party_type") {
                        dropdown.parentElement.hidden = true;
                        dropdown.value = response.data[0].value || response.data[0].id;
                    }
                } else {
                    console.warn(`No data returned for ${fieldId}:`, response);
                    this.showError(dropdown, "No options available for this selection");
                }
            } else {
                console.error(`API error for ${fieldId}:`, response);
                this.showError(dropdown, response.error || "Failed to load options");
            }
        } catch (error) {
            console.error(`Error loading dropdown data for ${fieldId}:`, error);
            this.showError(dropdown, "Network error occurred");
        } finally {
            this.hideLoader(loader);
        }
    }

    async makeRequest(endpoint, params = {}) {
        return await apiUtils.get(endpoint, params);
    }

    handleDropdownChange(dropdown) {
        // Upload guesses are optional. Keep the change handler safe even if a
        // stale/partial response or another caller clears the property.
        this.guesses = this.guesses || {};
        const fieldId = dropdown.id;
        const selectedValue = dropdown.value;
        const mapping = this.dropdownMapping[fieldId];

        // Only clear recommendation notices if the court dropdown is manually changed by user
        // Preserve notices for automatic selections and when other dropdowns change
        if (fieldId === "court" && !this.isAutomaticSelection) {
            this.clearAllRecommendationNotices();
        }

        // Reset the automatic selection flag after handling
        this.isAutomaticSelection = false;

        // Store the selected value
        this.selectedValues[fieldId] = selectedValue;

        // Reset all dependent dropdowns when this dropdown changes
        this.resetDependentDropdowns(fieldId);

        // Reset optional services flag when case type changes
        if (
            fieldId === "case_type" ||
            fieldId === "case_category" ||
            fieldId === "court"
        ) {
            this.optionalServicesLoaded = false;
        }

        if (mapping && selectedValue) {
            // Prepare parameters for the next dropdown
            let params = {};

            // Always add jurisdiction
            params.jurisdiction = apiUtils.getCurrentJurisdiction();

            // Add additional context parameters based on the field
            if (fieldId === "court") {
                // When court is selected, load case categories for that court
                params.court = selectedValue;
            } else if (fieldId === "case_category") {
                // Case category to case type
                params.parent = selectedValue; // Suffolk API expects parent parameter
                if (this.selectedValues.court) {
                    params.court = this.selectedValues.court;
                } else {
                    console.warn("No court selected when trying to load case types");
                    return;
                }
            } else if (fieldId === "case_type") {
                params.parent = selectedValue; // Suffolk API expects parent parameter for case_type
                params.case_type = selectedValue;
                if (this.selectedValues.court) {
                    params.court = this.selectedValues.court;
                } else {
                    console.warn("No court selected when trying to load filing types");
                    return;
                }

                // Add both existing_case and initial parameters for filing type endpoint
                const existingCase = sessionStorage.getItem('existing_case') || 'no';
                const isInitialFiling = existingCase === 'no';
                params.existing_case = existingCase; // Pass existing_case to Django API
                params.initial = isInitialFiling ? 'true' : 'false'; // Pass initial to Suffolk API
            }

            // Validate required parameters before making API call
            if (this.validateParameters(fieldId, params)) {
                // Load data for the next dropdown only if there is a next dropdown
                if (mapping.next && mapping.endpoint) {
                    params.guessed_case_category = this.guesses?.['case category'];
                    params.guessed_case_type = this.guesses?.['case type'];
                    params.only_required = true;
                    this.loadDropdownData(mapping.next, mapping.endpoint, params);
                }
            } else {
                console.warn(`Missing required parameters for ${fieldId}:`, params);
                return;
            }

            // Special handling for court selection
            if (fieldId === "court") {
                // Clear the user profile status indicator when court changes
                const statusElement = document.getElementById("userProfileStatus");
                if (statusElement) {
                    statusElement.style.display = "none";
                    statusElement.className = "alert alert-info"; // Reset to default class
                    statusElement.innerHTML =
                        '<i class="fas fa-user-check"></i> Loading your information...';
                }

                // Only clear recommendation notices and visual indicators if the user manually changed the court
                // We'll preserve these for auto-selections
                this.clearAllDropdownVisualIndicators();

                const caseCategoryDropdown = document.getElementById("case_category");
                if (caseCategoryDropdown) {
                    caseCategoryDropdown.disabled = false;
                    // Update placeholder text
                    const placeholder =
                        caseCategoryDropdown.querySelector('option[value=""]');
                    if (placeholder) {
                        placeholder.textContent = gettext("Select Case Category");
                    }
                }
            }

            // Trigger dynamic form sections when case type changes
            if (fieldId === "case_type") {
                this.triggerDynamicFormSections();
            }

            // Re-render dynamic form sections when court changes (if they already exist)
            // This ensures conditional requirements are re-evaluated
            if (fieldId === "court" && this.selectedValues.case_type) {
                this.triggerDynamicFormSections();
            }
        } else if (mapping) {
            // Clear and disable the next dropdown if no value selected
            const nextDropdown = document.getElementById(mapping.next);
            if (nextDropdown) {
                this.clearDropdown(nextDropdown);
                nextDropdown.disabled = true;
            }
        }

        // Clear dependent dropdowns
        // Only clear dependent dropdowns when the case_type changes.
        // This avoids removing dynamic form fields when other dropdowns (like filing_type)
        // are changed as part of cascading operations.
        if (fieldId === "case_type") {
            this.clearDependentDropdowns(fieldId);
        }
    }

    triggerDynamicFormSections() {
        // Check if dynamic form sections is available
        if (window.dynamicFormSections) {
            // Add a small delay to ensure the dropdown value is set
            setTimeout(() => {
                window.dynamicFormSections.handleCaseTypeChange();
            }, 100);
        } else {
            console.warn(
                "dynamicFormSections not available on window object, attempting manual trigger"
            );

            // Fallback: Try to trigger the case type change event manually
            setTimeout(() => {
                const caseTypeSelect = document.getElementById("case_type");
                if (caseTypeSelect && caseTypeSelect.value) {
                    const changeEvent = new Event("change", {
                        bubbles: true
                    });
                    caseTypeSelect.dispatchEvent(changeEvent);
                }

                // Also try to find and call the dynamic form sections directly
                if (window.DynamicFormSections) {
                    try {
                        const dynamicSections = new window.DynamicFormSections();
                        window.dynamicFormSections = dynamicSections;
                        setTimeout(() => {
                            dynamicSections.handleCaseTypeChange();
                        }, 200);
                    } catch (error) {
                        console.error("Failed to create DynamicFormSections:", error);
                    }
                }
            }, 200);
        }
    }

    async loadFormConfiguration() {
        // Since filing types are now handled on upload page, we can load form configuration
        // when we have case type selected
        if (
            !this.selectedValues.case_category ||
            !this.selectedValues.case_type
        ) {
            return;
        }

        try {
            // Load optional services from Suffolk API - this is the main feature users expect
            await this.loadOptionalServices();
        } catch (error) {
            console.error("Error loading form configuration:", error);
        }
    }

    async loadOptionalServices() {
        if (!this.selectedValues.court || !this.selectedValues.case_type) {
            console.warn("Missing required values for optional services");
            return;
        }

        // Prevent duplicate loading
        if (this.optionalServicesLoaded) {
            return;
        }

        this.optionalServicesLoaded = true; // Set flag immediately to prevent race conditions

        try {
            const params = {
                court: this.selectedValues.court,
                case_type_id: this.selectedValues.case_type,
                jurisdiction: "illinois",
            };

            // Use your Django API endpoint instead of direct Suffolk API call
            const response = await this.makeRequest(
                "/api/dropdowns/optional-services/",
                params
            );

            if (response.success && response.data) {
                this.updateOptionalServicesFromAPI(response.data);
            } else {
                console.warn(
                    "Optional services API failed:",
                    response.error || "No data"
                );
                // Fall back to showing default services
                this.showDefaultOptionalServices();
            }
        } catch (error) {
            console.error("Error loading optional services:", error);
            // Fall back to showing default services
            this.showDefaultOptionalServices();
        }
    }

    updateOptionalServicesFromAPI(services) {
        // AGGRESSIVE CLEANUP - Remove ALL possible optional services containers
        // This includes containers with different class names and IDs that might exist
        const allPossibleSelectors = [
            "#optional-services-container",
            ".optional-services-container",
            '[data-created-by="cascading-dropdowns"]',
        ];

        allPossibleSelectors.forEach((selector) => {
            try {
                const containers = document.querySelectorAll(selector);
                containers.forEach((container) => {
                    const isTagged =
                        container.dataset &&
                        container.dataset.createdBy === "cascading-dropdowns";
                    const isNamed =
                        container.id === "optional-services-container" ||
                        container.classList.contains("optional-services-container");
                    if (isTagged || isNamed) {
                        container.remove();
                    }
                });
            } catch (e) {
                // Ignore selector errors
            }
        });

        // Also look for headings but only remove their nearest safe container (one we created)
        const headings = document.querySelectorAll("h5, h4, h3");
        headings.forEach((heading) => {
            if (
                heading.textContent &&
                heading.textContent.includes("Optional Services")
            ) {
                const container = heading.closest(
                    '#optional-services-container, .optional-services-container, [data-created-by="cascading-dropdowns"]'
                );
                if (container) {
                    container.remove();
                }
            }
        });

        // Wait a moment for DOM cleanup
        setTimeout(() => {
            // Create a fresh container
            let servicesContainer = null;

            // Try to find a specific placement location first
            const preferredLocations = [
                document.querySelector("#dynamicSections"), // Our main dynamic sections container
                document.querySelector('[data-section="filing-options"]'),
                document.querySelector("#filing-options"),
                document.querySelector(".filing-options"),
                document.querySelector(".form-section:last-child"),
                document.querySelector(".form-container"),
                document.querySelector("#expertForm"), // The main form
                document.querySelector("form"),
                document.querySelector(".container"),
                document.querySelector("main"),
                document.body,
            ];

            let formContainer = null;
            for (const location of preferredLocations) {
                if (location) {
                    formContainer = location;
                    break;
                }
            }

            if (formContainer) {
                // Reuse existing container if present to avoid duplicates
                const existing =
                    document.getElementById("optional-services-container") ||
                    document.querySelector('[data-created-by="cascading-dropdowns"]');
                if (existing) {
                    servicesContainer = existing;
                    // Clear previous content safely
                    servicesContainer.innerHTML = "";
                } else {
                    servicesContainer = document.createElement("div");
                    servicesContainer.id = "optional-services-container";
                    servicesContainer.className = "optional-services-container mt-4 mb-4";
                    servicesContainer.setAttribute(
                        "data-created-by",
                        "cascading-dropdowns"
                    );
                    servicesContainer.setAttribute("data-section", "optional-services");
                }

                // Try to insert before buttons if they exist, but do it safely
                const buttons = formContainer.querySelector(
                    '.form-actions, .button-group, [class*="button"], input[type="submit"], button[type="submit"]'
                );
                if (!formContainer.contains(servicesContainer)) {
                    if (buttons && buttons.parentNode === formContainer) {
                        try {
                            formContainer.insertBefore(servicesContainer, buttons);
                        } catch (error) {
                            console.warn(
                                "Could not insert before buttons, appending instead:",
                                error
                            );
                            formContainer.appendChild(servicesContainer);
                        }
                    } else {
                        formContainer.appendChild(servicesContainer);
                    }
                }
            } else {
                console.error(
                    "Could not find suitable container for optional services"
                );
                return;
            }

            if (!services || !Array.isArray(services) || services.length === 0) {
                servicesContainer.innerHTML =
                    '<p class="text-muted">No optional services available for this filing type.</p>';
                return;
            }

            // Create header
            const header = document.createElement("h3");
            header.textContent = gettext("Optional Services");
            header.className = "mb-3";
            servicesContainer.appendChild(header);

            // Create services list
            services.forEach((service, index) => {
                const serviceDiv = document.createElement("div");
                serviceDiv.className = "form-check mb-2";

                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.className = "form-check-input";
                checkbox.id = `service_${service.code || service.id || index}`;
                checkbox.name = "optional_services";
                checkbox.value = service.code || service.id || index;

                const label = document.createElement("label");
                label.className = "form-check-label";
                label.setAttribute("for", checkbox.id);

                // Build label text with name and fee if available
                let labelText =
                    service.name || service.text || service.label || "Unknown Service";
                if (service.fee && parseFloat(service.fee) > 0) {
                    labelText += ` ($${parseFloat(service.fee).toFixed(2)})`;
                }
                label.textContent = labelText;

                serviceDiv.appendChild(checkbox);
                serviceDiv.appendChild(label);

                // Add description if available
                if (service.description && service.description !== null) {
                    const description = document.createElement("small");
                    description.className = "form-text text-muted d-block ml-4";
                    description.textContent = service.description;
                    serviceDiv.appendChild(description);
                }

                servicesContainer.appendChild(serviceDiv);
            });

            // Make sure the container is visible
            servicesContainer.style.display = "block";
        }, 100); // Small delay to ensure cleanup completes
    }

    showDefaultOptionalServices() {
        // Show basic optional services if API fails

        let servicesContainer =
            document.querySelector(".optional-services-container") ||
            document.querySelector("#optional-services-container") ||
            document.querySelector(".services-container");

        if (!servicesContainer) {
            // Try to create one
            const formContainer =
                document.querySelector(".form-container") ||
                document.querySelector("#filing-form") ||
                document.querySelector("form") ||
                document.querySelector(".container") ||
                document.querySelector("main") ||
                document.body;

            if (formContainer) {
                servicesContainer = document.createElement("div");
                servicesContainer.id = "optional-services-container";
                servicesContainer.className = "optional-services-container mt-4";
                formContainer.appendChild(servicesContainer);
            }
        }

        if (!servicesContainer) {
            console.error(
                "Could not find or create container for default optional services"
            );
            return;
        }

        servicesContainer.innerHTML = `
            <h5 class="mb-3">Optional Services</h5>
            <div class="form-check mb-2">
                <input type="checkbox" class="form-check-input" id="service_expedited" name="optional_services" value="expedited">
                <label class="form-check-label" for="service_expedited">Expedited Processing</label>
            </div>
            <div class="form-check mb-2">
                <input type="checkbox" class="form-check-input" id="service_certified" name="optional_services" value="certified">
                <label class="form-check-label" for="service_certified">Certified Copy</label>
            </div>
        `;

        servicesContainer.style.display = "block";
    }

    validateParameters(fieldId, params) {
        // Define required parameters for each field
        const requiredParams = {
            court: ["jurisdiction"],
            case_category: ["jurisdiction", "court"],
            case_type: ["jurisdiction", "parent"], // parent = category_id
        };

        const required = requiredParams[fieldId] || [];
        const missing = required.filter((param) => !params[param]);

        if (missing.length > 0) {
            console.error(`Missing required parameters for ${fieldId}:`, missing);
            return false;
        }

        return true;
    }

    clearDependentDropdowns(changedFieldId) {
        const dependencies = {
            court: ["case_category", "case_type"],
            case_category: ["case_type"],
            case_type: ["party_type"], // case_type is now the final dropdown on expert form
        };

        const toClear = dependencies[changedFieldId] || [];
        toClear.forEach((fieldId) => {
            const dropdown = document.getElementById(fieldId);
            if (dropdown && fieldId !== this.dropdownMapping[changedFieldId]?.next) {
                // Special handling for case_type - notify dynamic forms and preserve temporarily
                if (fieldId === "case_type") {
                    // Store the current value before clearing
                    const currentCaseTypeValue = dropdown.value;
                    const currentCaseTypeText =
                        dropdown.options[dropdown.selectedIndex]?.text || "";

                    // Notify dynamic forms that case_type is being cleared programmatically
                    if (window.dynamicFormSections) {
                        window.dynamicFormSections.currentCaseType = null;
                        // Don't hide sections immediately - let the restoration process handle it
                    }

                    // Clear the dropdown but keep the dynamic forms intact temporarily
                    this.clearDropdown(dropdown);
                    dropdown.disabled = true;

                    // If this was triggered by filing_type change and we have a case type,
                    // try to restore it after the dropdown gets repopulated
                    if (changedFieldId === "filing_type" && currentCaseTypeValue) {
                        setTimeout(() => {
                            // Check if dropdown got repopulated
                            if (dropdown.options.length > 1) {
                                const matchingOption = dropdown.querySelector(
                                    `option[value="${currentCaseTypeValue}"]`
                                );
                                if (matchingOption) {
                                    dropdown.value = currentCaseTypeValue;
                                    dropdown.disabled = false;
                                    this.selectedValues.case_type = currentCaseTypeValue;

                                    // Re-trigger dynamic form sections
                                    setTimeout(() => {
                                        if (window.dynamicFormSections) {
                                            window.dynamicFormSections.handleCaseTypeChange();
                                        }
                                    }, 100);
                                }
                            }
                        }, 1500); // Give more time for dropdown to repopulate
                    }
                } else {
                    // Regular clearing for other dropdowns
                    this.clearDropdown(dropdown);
                    dropdown.disabled = true;
                }
            }
        });
    }

    populateDropdown(dropdown, options) {
        // Special handling for filing type search dropdown
        if (dropdown.id === 'filing_type' && window.filingTypeSearch) {
            window.filingTypeSearch.updateOptions(options);
            window.filingTypeSearch.enable();
            return;
        }

        const placeholder = dropdown.querySelector('option[value=""]').textContent;

        // Clear dropdown and remove any visual selection indicators
        dropdown.innerHTML = `<option value="">${placeholder}</option>`;
        dropdown.classList.remove("has-selection", "selected", "success");
        dropdown.removeAttribute("data-selected");
        dropdown.value = "";

        // Check if options is valid
        if (!options || !Array.isArray(options)) {
            console.warn("Invalid options data:", options);
            this.showError(dropdown, "No options available");
            return;
        }

        let recommendedOption = null;

        options.forEach((option) => {
            const optionElement = document.createElement("option");
            optionElement.value = option.value || option.id;
            optionElement.textContent = option.label || option.name || option.text;

            // Check if this is a recommended option
            if (
                option.recommended ||
                option.selected ||
                option.default
            ) {
                optionElement.style.fontWeight = "bold";
                recommendedOption = option.value || option.id;
            }

            dropdown.appendChild(optionElement);
        });

        // Auto-select recommended court and trigger change event
        if ((dropdown.id === "court" || dropdown.id === "case_category" || dropdown.id === "case_type") && recommendedOption) {
            this.isAutomaticSelection = true; // Mark as automatic selection
            dropdown.value = recommendedOption;
            if (dropdown.id === "court") {
                this.selectedValues.court = recommendedOption;
            }

            // Show a brief notification about the auto-selection
            this.showRecommendationNotice(dropdown, dropdown.id);

            // Trigger change event to load dependent dropdowns
            setTimeout(() => {
                dropdown.dispatchEvent(new Event("change", {
                    bubbles: true
                }));
            }, 500);
        }

        // Handle user's preferred county auto-selection (fallback)
        if (
            dropdown.id === "court" &&
            !recommendedOption &&
            this.userProfile &&
            this.userProfile.preferred_county
        ) {
            this.isAutomaticSelection = true; // Mark as automatic selection
            const preferredValue = this.userProfile.preferred_county;
            const preferredOption = dropdown.querySelector(
                `option[value="${preferredValue}"]`
            );
            if (preferredOption) {
                dropdown.value = preferredValue;
                this.selectedValues.court = preferredValue;

                // Show notice for this selection too
                this.showRecommendationNotice(dropdown, "court");

                // Trigger change event to load dependent dropdowns
                setTimeout(() => {
                    dropdown.dispatchEvent(new Event("change", {
                        bubbles: true
                    }));
                }, 500);
            }
        }
    }

    showRecommendationNotice(dropdown, type) {
        // Remove any existing recommendation notice for this dropdown first
        const existingNotice = dropdown.parentNode.querySelector('.recommendation-notice');
        if (existingNotice) {
            existingNotice.remove();
        }

        if (type === "court") {
            // Create a persistent notice to show the user why this option was selected
            const notice = document.createElement("div");
            notice.className = "alert alert-success recommendation-notice";
            notice.style.cssText =
                "position: relative; z-index: 1000; margin-top: 5px; margin-bottom: 10px; padding: 8px 12px; font-size: 0.875rem; border-radius: 4px;";
            notice.innerHTML = `<i class="fas fa-star"></i> We've pre-selected some choices based on your uploaded form.`;
            // Find the label for this dropdown to insert the notice above it
            const dropdownLabel = dropdown.parentNode.querySelector(`label[for="${dropdown.id}"]`);

            if (dropdownLabel) {
                // Insert the notice before the label (above the title)
                dropdownLabel.parentNode.insertBefore(notice, dropdownLabel);
            } else {
                // Fallback: insert before the dropdown if no label is found
                dropdown.parentNode.insertBefore(notice, dropdown);
            }
        }

        // The notice will now persist until the court dropdown changes or page reloads
        // No automatic removal timeout
    }

    clearAllRecommendationNotices() {
        // Remove all existing recommendation notices (green success alerts)
        const existingNotices = document.querySelectorAll(
            ".recommendation-notice, .alert.alert-success.recommendation-notice"
        );
        existingNotices.forEach((notice) => {
            if (notice.parentNode) {
                notice.parentNode.removeChild(notice);
            }
        });
    }

    clearAllDropdownVisualIndicators() {
        // Clear visual indicators from all dropdowns
        const allDropdowns = document.querySelectorAll(
            ".dropdown-field, select.form-select"
        );
        allDropdowns.forEach((dropdown) => {
            // Remove success/selection classes
            dropdown.classList.remove(
                "has-selection",
                "selected",
                "success",
                "is-valid"
            );
            dropdown.removeAttribute("data-selected");

            // Remove any checkmark or success icons that might be added via pseudo-elements
            const parent = dropdown.parentElement;
            if (parent) {
                parent.classList.remove(
                    "has-success",
                    "field-success",
                    "validation-success"
                );

                // Remove any success icons that might have been added
                const successIcons = parent.querySelectorAll(
                    ".fa-check, .fa-check-circle, .success-icon"
                );
                successIcons.forEach((icon) => icon.remove());
            }
        });
    }

    resetDependentDropdowns(changedFieldId) {
        // Define the hierarchy of dependent dropdowns
        const hierarchy = [
            "court",
            "case_category",
            "case_type",
            "party_type",
            "filing_type",
            "document_type",
        ];

        // Find the index of the changed field in the hierarchy
        const changedIndex = hierarchy.indexOf(changedFieldId);

        if (changedIndex === -1) return; // Field not in hierarchy

        // Reset all dropdowns that come after the changed field in the hierarchy
        for (let i = changedIndex + 1; i < hierarchy.length; i++) {
            const fieldToReset = hierarchy[i];
            const dropdown = document.getElementById(fieldToReset);

            if (dropdown) {
                // Clear the dropdown
                this.clearDropdown(dropdown);

                // Reset the stored value
                this.selectedValues[fieldToReset] = null;
            }
        }

        // Also clear dynamic form sections when case_type is reset
        if (changedIndex <= hierarchy.indexOf("case_type")) {
            const dynamicSectionsContainer =
                document.getElementById("dynamic-sections");
            if (dynamicSectionsContainer) {
                dynamicSectionsContainer.innerHTML = "";
            }
        }
    }

    clearDropdown(dropdown) {
        // Special handling for filing type search dropdown
        if (dropdown.id === 'filing_type' && window.filingTypeSearch) {
            window.filingTypeSearch.reset();
            window.filingTypeSearch.disable();
            return;
        }

        let placeholder =
            dropdown.querySelector('option[value=""]')?.textContent ||
            "Please select...";

        // Special handling for case category when no court is selected
        if (dropdown.id === "case_category" && !this.selectedValues.court) {
            placeholder = "First select a court";
            dropdown.disabled = true;
        } else if (dropdown.id === "case_category" && this.selectedValues.court) {
            placeholder = "Select Case Category";
            dropdown.disabled = false;
        }

        // Clear all options and reset to placeholder
        dropdown.innerHTML = `<option value="">${placeholder}</option>`;

        // Remove any visual indicators or classes that might show selection state
        dropdown.classList.remove("has-selection", "selected", "success");
        dropdown.removeAttribute("data-selected");

        // Reset dropdown value explicitly to ensure no selection state
        dropdown.value = "";
    }

    showLoader(loader) {
        if (loader) loader.style.display = "block";
    }

    hideLoader(loader) {
        if (loader) loader.style.display = "none";
    }

    showError(dropdown, message) {
        dropdown.innerHTML = `<option value="">Error: ${message}</option>`;
        dropdown.disabled = false;
    }

    enableDropdown(fieldId) {
        const dropdown = document.getElementById(fieldId);
        if (dropdown) {
            dropdown.disabled = false;
        }
    }

    /**
     * Clear all dropdowns and reset their state
     */
    clearAllDropdowns() {
        const dropdownFields = ['court', 'case_category', 'case_type', 'filing_type', 'document_type'];

        dropdownFields.forEach(fieldId => {
            const dropdown = document.getElementById(fieldId);
            if (dropdown) {
                this.clearDropdown(dropdown);
                if (fieldId !== 'court') {
                    dropdown.disabled = true;
                }
            }

            // Reset selected values
            this.selectedValues[fieldId] = null;
        });

        // Hide dynamic sections
        const dynamicSections = document.getElementById('dynamicSections');
        if (dynamicSections) {
            dynamicSections.style.display = 'none';
            dynamicSections.innerHTML = '';
        }
    }
}

// Export for module use or make globally available
if (typeof module !== "undefined" && module.exports) {
    module.exports = CascadingDropdowns;
} else {
    window.CascadingDropdowns = CascadingDropdowns;
}
