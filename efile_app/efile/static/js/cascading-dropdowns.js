/**
 * CascadingDropdowns - Handles smart form dropdown interactions
 * Features: Location-based recommendations, court-specific filtering, progressive form enablement
 */
class CascadingDropdowns {
    constructor() {
        this.dropdownMapping = {
            'court': { next: 'case_category', endpoint: '/api/dropdowns/case-categories/' },
            'case_category': { next: 'case_type', endpoint: '/api/dropdowns/case-types/' },
            'case_type': { next: 'filing_type', endpoint: '/api/dropdowns/filing-types/' },
            'filing_type': { next: 'document_type', endpoint: '/api/dropdowns/document-types/' }
        };
        
        this.userProfile = null;
        this.selectedValues = {
            court: null,
            case_category: null,
            case_type: null,
            filing_type: null,
            document_type: null
        };
        this.optionalServicesLoaded = false;
        
        this.init();
    }

    async init() {
        // Load user profile first
        await this.loadUserProfile();
        
        // Load initial data for independent dropdowns with user context
        this.loadCourtsWithUserContext();
        
        // Add event listeners
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('dropdown-field')) {
                this.handleDropdownChange(e.target);
            }
        });
    }

    async loadCourtsWithUserContext() {
        console.log('=== Loading courts with user context ===');
        const params = {};
        if (this.userProfile) {
            console.log('User profile available for courts loading:', this.userProfile);
            // Pass user location info to courts API
            if (this.userProfile.preferred_county) {
                params.user_county = this.userProfile.preferred_county;
                console.log('Adding user_county:', this.userProfile.preferred_county);
            }
            if (this.userProfile.zip_code) {
                params.user_zip = this.userProfile.zip_code;
                console.log('Adding user_zip:', this.userProfile.zip_code);
            }
            // Add jurisdiction if available
            if (this.userProfile.state) {
                const jurisdictionMap = {
                    'IL': 'illinois',
                    'Illinois': 'illinois'
                };
                params.jurisdiction = jurisdictionMap[this.userProfile.state] || 'illinois';
                console.log('Adding jurisdiction from state:', this.userProfile.state, '->', params.jurisdiction);
            }
        } else {
            console.log('No user profile available for courts loading');
        }
        
        // Always set default jurisdiction if not provided
        if (!params.jurisdiction) {
            params.jurisdiction = 'illinois';
            console.log('Setting default jurisdiction: illinois');
        }
        
        console.log('Final courts API params:', params);
        await this.loadDropdownData('court', '/api/dropdowns/courts/', params);
        console.log('=== Courts loading completed ===');
    }

    async loadUserProfile() {
        console.log('=== Loading user profile ===');
        const statusElement = document.getElementById('userProfileStatus');
        
        try {
            if (statusElement) {
                statusElement.style.display = 'block';
                statusElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading your information...';
            }
            
            const response = await this.makeRequest('/api/auth/profile/');
            console.log('User profile API response:', response);
            
            if (response.success) {
                if (statusElement) {
                    statusElement.style.display = 'none';
                }
                this.userProfile = response.data;
                console.log('✅ User profile loaded successfully:', this.userProfile);
                console.log('User preferred county:', this.userProfile.preferred_county);
                console.log('User ZIP code:', this.userProfile.zip_code);
                console.log('User state:', this.userProfile.state);
            } else {
                console.warn('❌ Failed to load user profile:', response.error);
                if (statusElement) {
                    statusElement.className = 'alert alert-warning';
                    statusElement.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Could not load profile information. Using default settings.';
                    setTimeout(() => {
                        statusElement.style.display = 'none';
                    }, 3000);
                }
            }
        } catch (error) {
            console.error('❌ Error loading user profile:', error);
            if (statusElement) {
                statusElement.className = 'alert alert-warning';
                statusElement.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Could not load profile information. Using default settings.';
                setTimeout(() => {
                    statusElement.style.display = 'none';
                }, 3000);
            }
        }
        
        console.log('=== User profile loading completed ===');
    }

    async fetchExternalUserInfo() {
        // Optional method to fetch additional user info from external APIs
        try {
            const response = await this.makeRequest('/api/auth/external-profile/');
            if (response.success) {
                this.userProfile = { ...this.userProfile, ...response.data };
                console.log('External user info loaded:', response.data);
            }
        } catch (error) {
            console.warn('Could not fetch external user info:', error);
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
            console.log(`Loading dropdown data for ${fieldId}:`, { endpoint, params });
            this.showLoader(loader);
            this.clearDropdown(dropdown);
            
            const response = await this.makeRequest(endpoint, params);
            
            if (response.success) {
                console.log(`Dropdown data for ${fieldId}:`, response);
                
                // Check if we have valid data
                if (response.data && Array.isArray(response.data) && response.data.length > 0) {
                    this.populateDropdown(dropdown, response.data);
                    dropdown.disabled = false;
                } else {
                    console.warn(`No data returned for ${fieldId}:`, response);
                    this.showError(dropdown, 'No options available for this selection');
                }
            } else {
                console.error(`API error for ${fieldId}:`, response);
                this.showError(dropdown, response.error || 'Failed to load options');
            }
        } catch (error) {
            console.error(`Error loading dropdown data for ${fieldId}:`, error);
            this.showError(dropdown, 'Network error occurred');
        } finally {
            this.hideLoader(loader);
        }
    }

    async makeRequest(endpoint, params = {}) {
        return await apiUtils.get(endpoint, params);
    }

    handleDropdownChange(dropdown) {
        const fieldId = dropdown.id;
        const selectedValue = dropdown.value;
        const mapping = this.dropdownMapping[fieldId];
        
        console.log(`=== Dropdown change: ${fieldId} = ${selectedValue} ===`);
        console.log('Current selected values:', this.selectedValues);
        
        // Store the selected value
        this.selectedValues[fieldId] = selectedValue;
        console.log('Updated selected values:', this.selectedValues);
        
        // Reset optional services flag when filing type changes
        if (fieldId === 'filing_type' || fieldId === 'case_type' || fieldId === 'case_category' || fieldId === 'court') {
            this.optionalServicesLoaded = false;
        }
        
        if (mapping && selectedValue) {
            // Prepare parameters for the next dropdown
            let params = {};
            
            // Always add jurisdiction
            params.jurisdiction = 'illinois';
            
            // Add additional context parameters based on the field
            if (fieldId === 'court') {
                // When court is selected, load case categories for that court
                params.court = selectedValue;
                console.log(`Loading ${mapping.next} for court: ${selectedValue}`);
            } else if (fieldId === 'case_category') {
                // Case category to case type
                params.parent = selectedValue;  // Suffolk API expects parent parameter
                if (this.selectedValues.court) {
                    params.court = this.selectedValues.court;
                    console.log(`Loading ${mapping.next} for case_category: ${selectedValue}, court: ${this.selectedValues.court}`);
                } else {
                    console.warn('No court selected when trying to load case types');
                    return;
                }
            } else if (fieldId === 'case_type') {
                params.parent = selectedValue;  // Suffolk API expects parent parameter for case_type
                if (this.selectedValues.court) {
                    params.court = this.selectedValues.court;
                    console.log(`Loading ${mapping.next} for case_type: ${selectedValue}, court: ${this.selectedValues.court}`);
                } else {
                    console.warn('No court selected when trying to load filing types');
                    return;
                }
            } else if (fieldId === 'filing_type') {
                params.parent = selectedValue;  // Suffolk API expects parent parameter for filing_type
                if (this.selectedValues.court) {
                    params.court = this.selectedValues.court;
                    console.log(`Loading ${mapping.next} for filing_type: ${selectedValue}, court: ${this.selectedValues.court}`);
                } else {
                    console.warn('No court selected when trying to load document types');
                    return;
                }
            }
            
            console.log(`Loading next dropdown ${mapping.next} with params:`, params);
            
            // Validate required parameters before making API call
            if (this.validateParameters(fieldId, params)) {
                // Load data for the next dropdown
                this.loadDropdownData(mapping.next, mapping.endpoint, params);
            } else {
                console.warn(`Missing required parameters for ${fieldId}:`, params);
                return;
            }
            
            // Special handling for court selection
            if (fieldId === 'court') {
                const caseCategoryDropdown = document.getElementById('case_category');
                if (caseCategoryDropdown) {
                    caseCategoryDropdown.disabled = false;
                    // Update placeholder text
                    const placeholder = caseCategoryDropdown.querySelector('option[value=""]');
                    if (placeholder) {
                        placeholder.textContent = 'Select Case Category';
                    }
                }
            }
            
            // Handle special case for when filing type is selected - update parties and services
            // But only if we have all required values (prevent premature API calls)
            if (fieldId === 'filing_type' && this.selectedValues.court) {
                this.loadFormConfiguration();
            }
            
            // Trigger dynamic form sections when case type changes
            if (fieldId === 'case_type') {
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
        if (fieldId === 'case_type') {
            this.clearDependentDropdowns(fieldId);
        } else {
            console.log(`Skipping clearing dependent dropdowns for ${fieldId}`);
        }
    }

    triggerDynamicFormSections() {
        console.log('=== triggerDynamicFormSections called ===');
        
        // Check if dynamic form sections is available
        if (window.dynamicFormSections) {
            console.log('Found dynamicFormSections, triggering handleCaseTypeChange');
            // Add a small delay to ensure the dropdown value is set
            setTimeout(() => {
                window.dynamicFormSections.handleCaseTypeChange();
            }, 100);
        } else {
            console.warn('dynamicFormSections not available on window object, attempting manual trigger');
            
            // Fallback: Try to trigger the case type change event manually
            setTimeout(() => {
                const caseTypeSelect = document.getElementById('case_type');
                if (caseTypeSelect && caseTypeSelect.value) {
                    console.log('Manually triggering case type change event');
                    const changeEvent = new Event('change', { bubbles: true });
                    caseTypeSelect.dispatchEvent(changeEvent);
                }
                
                // Also try to find and call the dynamic form sections directly
                if (window.DynamicFormSections) {
                    console.log('Attempting to create DynamicFormSections instance');
                    try {
                        const dynamicSections = new window.DynamicFormSections();
                        window.dynamicFormSections = dynamicSections;
                        setTimeout(() => {
                            dynamicSections.handleCaseTypeChange();
                        }, 200);
                    } catch (error) {
                        console.error('Failed to create DynamicFormSections:', error);
                    }
                }
            }, 200);
        }
    }

    async loadFormConfiguration() {
        console.log('=== loadFormConfiguration called ===');
        console.log('Current selected values:', this.selectedValues);
        
        if (!this.selectedValues.case_category || !this.selectedValues.case_type || !this.selectedValues.filing_type) {
            console.log('Missing required values for form configuration:', {
                case_category: this.selectedValues.case_category,
                case_type: this.selectedValues.case_type,
                filing_type: this.selectedValues.filing_type
            });
            return;
        }

        try {
            // Load optional services from Suffolk API - this is the main feature users expect
            console.log('Loading optional services...');
            await this.loadOptionalServices();

            // Skip the form-config API call that's causing 400 error
            // The dynamic form sections handle case-specific configuration
            console.log('Form configuration loading completed (using dynamic sections instead of form-config API)');
        } catch (error) {
            console.error('Error loading form configuration:', error);
        }
    }

    async loadOptionalServices() {
        console.log('=== loadOptionalServices called ===');
        console.log('Court:', this.selectedValues.court);
        console.log('Filing type:', this.selectedValues.filing_type);
        console.log('Already loaded flag:', this.optionalServicesLoaded);
        
        if (!this.selectedValues.court || !this.selectedValues.filing_type) {
            console.warn('Missing required values for optional services');
            return;
        }

        // Prevent duplicate loading
        if (this.optionalServicesLoaded) {
            console.log('Optional services already loaded, skipping');
            return;
        }

        console.log('Setting optionalServicesLoaded flag to true');
        this.optionalServicesLoaded = true; // Set flag immediately to prevent race conditions

        try {
            const params = {
                court: this.selectedValues.court,
                filing_type_id: this.selectedValues.filing_type,
                jurisdiction: 'illinois'
            };
            
            console.log('Loading optional services with params:', params);

            // Use your Django API endpoint instead of direct Suffolk API call
            const response = await this.makeRequest('/api/dropdowns/optional-services/', params);

            if (response.success && response.data) {
                console.log('Optional services loaded successfully:', response.data);
                this.updateOptionalServicesFromAPI(response.data);
            } else {
                console.warn('Optional services API failed:', response.error || 'No data');
                // Fall back to showing default services
                this.showDefaultOptionalServices();
            }
        } catch (error) {
            console.error('Error loading optional services:', error);
            // Fall back to showing default services
            this.showDefaultOptionalServices();
        }
        
        console.log('=== loadOptionalServices completed ===');
    }

    updateOptionalServicesFromAPI(services) {
        console.log('Updating optional services from API:', services);
        
        // AGGRESSIVE CLEANUP - Remove ALL possible optional services containers
        // This includes containers with different class names and IDs that might exist
        const allPossibleSelectors = [
            '#optional-services-container',
            '.optional-services-container',
            '[data-created-by="cascading-dropdowns"]'
        ];
        
        allPossibleSelectors.forEach(selector => {
            try {
                const containers = document.querySelectorAll(selector);
                containers.forEach(container => {
                    const isTagged = container.dataset && container.dataset.createdBy === 'cascading-dropdowns';
                    const isNamed = container.id === 'optional-services-container' || container.classList.contains('optional-services-container');
                    if (isTagged || isNamed) {
                        console.log('Removing existing optional services container (safe):', selector, container.id || container.className);
                        container.remove();
                    }
                });
            } catch (e) {
                // Ignore selector errors
            }
        });
        
        // Also look for headings but only remove their nearest safe container (one we created)
        const headings = document.querySelectorAll('h5, h4, h3');
        headings.forEach(heading => {
            if (heading.textContent && heading.textContent.includes('Optional Services')) {
                const container = heading.closest('#optional-services-container, .optional-services-container, [data-created-by="cascading-dropdowns"]');
                if (container) {
                    console.log('Removing container with Optional Services heading (safe):', container.id || container.className);
                    container.remove();
                }
            }
        });
        
        // Wait a moment for DOM cleanup
        setTimeout(() => {
            // Create a fresh container
            let servicesContainer = null;
            
            console.log('Creating new optional services container');
            
            // Try to find a specific placement location first
            const preferredLocations = [
                document.querySelector('#dynamicSections'), // Our main dynamic sections container
                document.querySelector('[data-section="filing-options"]'),
                document.querySelector('#filing-options'),
                document.querySelector('.filing-options'),
                document.querySelector('.form-section:last-child'),
                document.querySelector('.form-container'),
                document.querySelector('#expertForm'), // The main form
                document.querySelector('form'),
                document.querySelector('.container'),
                document.querySelector('main'),
                document.body
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
                const existing = document.getElementById('optional-services-container') || document.querySelector('[data-created-by="cascading-dropdowns"]');
                if (existing) {
                    servicesContainer = existing;
                    // Clear previous content safely
                    servicesContainer.innerHTML = '';
                    console.log('Reusing existing optional services container to avoid duplicate');
                } else {
                    servicesContainer = document.createElement('div');
                    servicesContainer.id = 'optional-services-container';
                    servicesContainer.className = 'optional-services-container mt-4 mb-4';
                    servicesContainer.setAttribute('data-created-by', 'cascading-dropdowns');
                    servicesContainer.setAttribute('data-section', 'optional-services');
                }
                 
                 // Try to insert before buttons if they exist, but do it safely
                 const buttons = formContainer.querySelector('.form-actions, .button-group, [class*="button"], input[type="submit"], button[type="submit"]');
                 if (!formContainer.contains(servicesContainer)) {
                    if (buttons && buttons.parentNode === formContainer) {
                        try {
                            formContainer.insertBefore(servicesContainer, buttons);
                            console.log('Inserted optional services container before buttons');
                        } catch (error) {
                            console.warn('Could not insert before buttons, appending instead:', error);
                            formContainer.appendChild(servicesContainer);
                            console.log('Appended optional services container to form');
                        }
                    } else {
                        formContainer.appendChild(servicesContainer);
                        console.log('Appended optional services container to form');
                    }
                 } else {
                    console.log('Optional services container already present inside form container; reused in place');
                 }
             } else {
                 console.error('Could not find suitable container for optional services');
                 return;
             }

            if (!services || !Array.isArray(services) || services.length === 0) {
                servicesContainer.innerHTML = '<p class="text-muted">No optional services available for this filing type.</p>';
                return;
            }

            // Create header
            const header = document.createElement('h3');
            header.textContent = 'Optional Services';
            header.className = 'mb-3';
            servicesContainer.appendChild(header);

            // Create services list
            services.forEach((service, index) => {
                console.log(`Processing service ${index}:`, service);
                
                const serviceDiv = document.createElement('div');
                serviceDiv.className = 'form-check mb-2';

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'form-check-input';
                checkbox.id = `service_${service.code || service.id || index}`;
                checkbox.name = 'optional_services';
                checkbox.value = service.code || service.id || index;

                const label = document.createElement('label');
                label.className = 'form-check-label';
                label.setAttribute('for', checkbox.id);
                
                // Build label text with name and fee if available
                let labelText = service.name || service.text || service.label || 'Unknown Service';
                if (service.fee && parseFloat(service.fee) > 0) {
                    labelText += ` ($${parseFloat(service.fee).toFixed(2)})`;
                }
                label.textContent = labelText;

                serviceDiv.appendChild(checkbox);
                serviceDiv.appendChild(label);
                
                // Add description if available
                if (service.description && service.description !== null) {
                    const description = document.createElement('small');
                    description.className = 'form-text text-muted d-block ml-4';
                    description.textContent = service.description;
                    serviceDiv.appendChild(description);
                }

                servicesContainer.appendChild(serviceDiv);
            });
            
            console.log(`Successfully rendered ${services.length} optional services in container:`, servicesContainer.id);
            
            // Make sure the container is visible
            servicesContainer.style.display = 'block';
        }, 100); // Small delay to ensure cleanup completes
    }

    showDefaultOptionalServices() {
        // Show basic optional services if API fails
        console.log('Showing default optional services');
        
        let servicesContainer = document.querySelector('.optional-services-container') ||
                               document.querySelector('#optional-services-container') ||
                               document.querySelector('.services-container');
        
        if (!servicesContainer) {
            // Try to create one
            const formContainer = document.querySelector('.form-container') ||
                                document.querySelector('#filing-form') ||
                                document.querySelector('form') ||
                                document.querySelector('.container') ||
                                document.querySelector('main') ||
                                document.body;
            
            if (formContainer) {
                servicesContainer = document.createElement('div');
                servicesContainer.id = 'optional-services-container';
                servicesContainer.className = 'optional-services-container mt-4';
                formContainer.appendChild(servicesContainer);
            }
        }
        
        if (!servicesContainer) {
            console.error('Could not find or create container for default optional services');
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
        
        servicesContainer.style.display = 'block';
    }

    updateFormStructure(config) {
        // Update required parties
        if (config.required_parties) {
            this.updateRequiredParties(config.required_parties);
        }
        
        // Update optional services
        if (config.optional_services) {
            this.updateOptionalServices(config.optional_services);
        }
        
        console.log('Form structure updated:', config);
    }

    updateRequiredParties(parties) {
        // This would dynamically update the parties section based on configuration
        console.log('Required parties configuration:', parties);
        
        // Example: Show/hide party sections based on configuration
        const partySections = document.querySelectorAll('.party-section');
        partySections.forEach(section => {
            section.style.display = 'block'; // Show all for now
        });
    }

    updateOptionalServices(services) {
        // This is the legacy method - now we prefer updateOptionalServicesFromAPI
        console.log('Legacy optional services configuration called:', services);
        
        // Don't load optional services again if we already loaded them from the API
        // This prevents duplicate rendering
        if (this.optionalServicesLoaded) {
            console.log('Optional services already loaded from API, skipping legacy method');
            return;
        }
        
        // Fallback to legacy approach only if API method hasn't been used
        const serviceCheckboxes = document.querySelectorAll('input[name="optional_services"]');
        if (serviceCheckboxes.length === 0) {
            // No services rendered yet, try API method
            if (this.selectedValues.filing_type) {
                this.loadOptionalServices();
                return;
            }
        }
        
        // Legacy checkbox management
        serviceCheckboxes.forEach(checkbox => {
            const serviceConfig = services.find(s => s.id === checkbox.value);
            if (serviceConfig) {
                checkbox.parentElement.style.display = 'block';
                // Update label with fee information if available
                const label = checkbox.parentElement.querySelector('label');
                if (label && serviceConfig.fee) {
                    label.textContent = `${serviceConfig.name} ($${serviceConfig.fee})`;
                }
            } else {
                checkbox.parentElement.style.display = 'none';
            }
        });
    }

    validateParameters(fieldId, params) {
        // Define required parameters for each field
        const requiredParams = {
            'court': ['jurisdiction'],
            'case_category': ['jurisdiction', 'court'],
            'case_type': ['jurisdiction', 'parent'],  // parent = category_id
            'filing_type': ['jurisdiction', 'parent'], // parent = case_type_id  
            'document_type': ['jurisdiction', 'parent'] // parent = filing_type_id
        };

        const required = requiredParams[fieldId] || [];
        const missing = required.filter(param => !params[param]);

        if (missing.length > 0) {
            console.error(`Missing required parameters for ${fieldId}:`, missing);
            return false;
        }

        return true;
    }

    clearDependentDropdowns(changedFieldId) {
        const dependencies = {
            'court': ['case_category', 'case_type', 'filing_type', 'document_type'],
            'case_category': ['case_type', 'filing_type', 'document_type'],
            'case_type': ['filing_type', 'document_type'],
            'filing_type': ['document_type'] // Don't clear case_type when filing_type changes - preserve for dynamic forms
        };
        
        const toClear = dependencies[changedFieldId] || [];
        toClear.forEach(fieldId => {
            const dropdown = document.getElementById(fieldId);
            if (dropdown && fieldId !== this.dropdownMapping[changedFieldId]?.next) {
                console.log(`Clearing dependent dropdown: ${fieldId} due to ${changedFieldId} change`);
                
                // Special handling for case_type - notify dynamic forms and preserve temporarily
                if (fieldId === 'case_type') {
                    // Store the current value before clearing
                    const currentCaseTypeValue = dropdown.value;
                    const currentCaseTypeText = dropdown.options[dropdown.selectedIndex]?.text || '';
                    
                    console.log('Preserving case_type for dynamic forms:', {
                        value: currentCaseTypeValue,
                        text: currentCaseTypeText
                    });
                    
                    // Notify dynamic forms that case_type is being cleared programmatically
                    if (window.dynamicFormSections) {
                        console.log('Notifying dynamic forms that case_type is being cleared programmatically');
                        window.dynamicFormSections.currentCaseType = null;
                        // Don't hide sections immediately - let the restoration process handle it
                    }
                    
                    // Clear the dropdown but keep the dynamic forms intact temporarily
                    this.clearDropdown(dropdown);
                    dropdown.disabled = true;
                    
                    // If this was triggered by filing_type change and we have a case type,
                    // try to restore it after the dropdown gets repopulated
                    if (changedFieldId === 'filing_type' && currentCaseTypeValue) {
                        console.log('Planning to restore case_type after filing_type cascade completes');
                        setTimeout(() => {
                            // Check if dropdown got repopulated
                            if (dropdown.options.length > 1) {
                                const matchingOption = dropdown.querySelector(`option[value="${currentCaseTypeValue}"]`);
                                if (matchingOption) {
                                    console.log('Restoring case_type after filing_type change:', currentCaseTypeValue);
                                    dropdown.value = currentCaseTypeValue;
                                    dropdown.disabled = false;
                                    this.selectedValues.case_type = currentCaseTypeValue;
                                    
                                    // Re-trigger dynamic form sections
                                    setTimeout(() => {
                                        if (window.dynamicFormSections) {
                                            console.log('Re-triggering dynamic form sections after case_type restoration');
                                            window.dynamicFormSections.handleCaseTypeChange();
                                        }
                                    }, 100);
                                } else {
                                    console.log('case_type option no longer available after filing_type change');
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
        console.log('=== Populating dropdown:', dropdown.id, 'with', options?.length, 'options ===');
        const placeholder = dropdown.querySelector('option[value=""]').textContent;
        dropdown.innerHTML = `<option value="">${placeholder}</option>`;
        
        // Check if options is valid
        if (!options || !Array.isArray(options)) {
            console.warn('Invalid options data:', options);
            this.showError(dropdown, 'No options available');
            return;
        }
        
        let recommendedOption = null;
        let selectedCount = 0;
        
        options.forEach(option => {
            const optionElement = document.createElement('option');
            optionElement.value = option.value || option.id;
            optionElement.textContent = option.label || option.name || option.text;
            
            // Check if this is a recommended option
            if (option.recommended || option.selected || option.default || option.isSelected) {
                optionElement.style.fontWeight = 'bold';
                recommendedOption = option.value || option.id;
                selectedCount++;
                console.log(`Found recommended option: ${optionElement.textContent} (${recommendedOption})`);
            }
            
            dropdown.appendChild(optionElement);
        });

        console.log(`Populated ${dropdown.id} with ${options.length} options, ${selectedCount} recommended`);

        // Auto-select recommended court and trigger change event
        if (dropdown.id === 'court' && recommendedOption) {
            console.log(`Auto-selecting recommended court: ${recommendedOption}`);
            dropdown.value = recommendedOption;
            this.selectedValues.court = recommendedOption;
            
            // Show a brief notification about the auto-selection
            this.showRecommendationNotice(dropdown, 'court');
            
            // Trigger change event to load dependent dropdowns
            setTimeout(() => {
                console.log('Triggering change event for auto-selected court');
                dropdown.dispatchEvent(new Event('change', { bubbles: true }));
            }, 500);
        }

        // Handle user's preferred county auto-selection (fallback)
        if (dropdown.id === 'court' && !recommendedOption && this.userProfile && this.userProfile.preferred_county) {
            const preferredValue = this.userProfile.preferred_county;
            const preferredOption = dropdown.querySelector(`option[value="${preferredValue}"]`);
            if (preferredOption) {
                console.log(`Auto-selecting user's preferred county: ${preferredValue}`);
                dropdown.value = preferredValue;
                this.selectedValues.court = preferredValue;
                
                // Trigger change event to load dependent dropdowns
                setTimeout(() => {
                    console.log('Triggering change event for preferred county');
                    dropdown.dispatchEvent(new Event('change', { bubbles: true }));
                }, 500);
            }
        }
    }

    showRecommendationNotice(dropdown, type) {
        // Create a temporary notice to show the user why this option was selected
        const notice = document.createElement('div');
        notice.className = 'alert alert-success recommendation-notice';
        notice.style.cssText = 'position: absolute; z-index: 1000; margin-top: 5px; padding: 8px 12px; font-size: 0.875rem; border-radius: 4px;';
        notice.innerHTML = `<i class="fas fa-star"></i> We've pre-selected the ${type} for your area based on your location.`;
        
        // Insert the notice after the dropdown
        dropdown.parentNode.insertBefore(notice, dropdown.nextSibling);
        
        // Remove the notice after 4 seconds
        setTimeout(() => {
            if (notice.parentNode) {
                notice.parentNode.removeChild(notice);
            }
        }, 4000);
    }

    clearDropdown(dropdown) {
        let placeholder = dropdown.querySelector('option[value=""]')?.textContent || 'Please select...';
        
        // Special handling for case category when no court is selected
        if (dropdown.id === 'case_category' && !this.selectedValues.court) {
            placeholder = 'First select a court';
            dropdown.disabled = true;
        } else if (dropdown.id === 'case_category' && this.selectedValues.court) {
            placeholder = 'Select Case Category';
            dropdown.disabled = false;
        }
        
        dropdown.innerHTML = `<option value="">${placeholder}</option>`;
    }

    showLoader(loader) {
        if (loader) loader.style.display = 'block';
    }

    hideLoader(loader) {
        if (loader) loader.style.display = 'none';
    }

    showError(dropdown, message) {
        dropdown.innerHTML = `<option value="">Error: ${message}</option>`;
        dropdown.disabled = false;
    }
}

// Export for module use or make globally available
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CascadingDropdowns;
} else {
    window.CascadingDropdowns = CascadingDropdowns;
}
