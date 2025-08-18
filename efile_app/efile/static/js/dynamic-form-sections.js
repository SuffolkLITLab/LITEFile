class DynamicFormSections {
    constructor() {
        // We create parties/services containers dynamically inside #dynamicSections
        this.partiesContainer = null; // will be created when needed
        this.servicesContainer = null; // will be created when needed
        this.dynamicSections = document.getElementById('dynamicSections');
        this.currentCaseType = null;
        this.config = null;
        this.preservedFormData = null;
        this.preservedCaseType = null;
        
        this.init();
    }

    async init() {
        // Load configuration from server
        await this.loadConfiguration();
        
        // Listen for case type changes to trigger form section updates
        const caseTypeSelect = document.getElementById('case_type');
        if (caseTypeSelect) {
            console.log('=== Adding event listener to case_type dropdown ===');
            caseTypeSelect.addEventListener('change', () => {
                console.log('case_type change event triggered from addEventListener');
                this.handleCaseTypeChange();
            });
            
            // Also listen for when the dropdown is cleared/reset
            const observer = new MutationObserver((mutations) => {
                mutations.forEach(mutation => {
                    if (mutation.type === 'childList' || mutation.type === 'attributes') {
                        console.log('case_type dropdown DOM changed:', mutation.type);
                        // Check if dropdown was cleared
                        if (caseTypeSelect.value === '' && this.dynamicSections && this.dynamicSections.style.display === 'block') {
                            console.log('case_type was cleared, hiding dynamic sections');
                            this.hideDynamicSections();
                        }
                    }
                });
            });
            observer.observe(caseTypeSelect, { 
                childList: true, 
                attributes: true, 
                attributeFilter: ['value'] 
            });
        } else {
            console.log('case_type dropdown not found in DOM');
        }
    }

    async loadConfiguration() {
        try {
            const response = await fetch('/api/case-type-config/');
            const result = await response.json();
            
            if (result.success) {
                this.config = result.config;
                console.log('Loaded case type configuration:', this.config);
            } else {
                console.error('Failed to load configuration:', result.error);
                this.config = this.getDefaultConfig();
            }
        } catch (error) {
            console.error('Error loading configuration:', error);
            this.config = this.getDefaultConfig();
        }
    }

    getDefaultConfig() {
        // Fallback configuration if server config fails
        return {
            case_types: {
                name_change: {
                    keywords: ['name change'],
                    sections: {
                        parties: {
                            title: 'Required Parties',
                            fields: [
                                {
                                    section_title: 'Petitioner',
                                    required: true,
                                    fields: [
                                        {
                                            name: 'petitioner_first_name',
                                            label: 'First Name',
                                            type: 'text',
                                            required: true,
                                            column_width: 'col-md-6'
                                        },
                                        {
                                            name: 'petitioner_last_name',
                                            label: 'Last Name',
                                            type: 'text',
                                            required: true,
                                            column_width: 'col-md-6'
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            }
        };
    }

    handleCaseTypeChange() {
        console.log('=== DynamicFormSections.handleCaseTypeChange called ===');
        const caseTypeSelect = document.getElementById('case_type');
        
        if (!caseTypeSelect) {
            console.log('Case type select element not found');
            return;
        }
        
        if (!this.config) {
            console.log('Configuration not loaded yet');
            return;
        }
        
        const caseTypeText = caseTypeSelect.options[caseTypeSelect.selectedIndex]?.text || '';
        const caseTypeValue = caseTypeSelect.value;
        
        console.log('Case type dropdown details:');
        console.log('- Selected index:', caseTypeSelect.selectedIndex);
        console.log('- Selected text:', caseTypeText);
        console.log('- Selected value:', caseTypeValue);
        console.log('- Dropdown disabled:', caseTypeSelect.disabled);
        
        // Don't hide sections immediately if the dropdown is being cleared - give time for restoration
        if (!caseTypeValue) {
            // Check if this is a temporary clearing (cascading dropdown coordination)
            const isBeingCleared = caseTypeSelect.disabled || 
                                   window.cascadingDropdowns?.optionalServicesLoaded === false;
            
            if (isBeingCleared) {
                console.log('case_type appears to be temporarily cleared (cascading coordination), not hiding sections immediately');
                // Set a timeout to check again later
                setTimeout(() => {
                    if (!caseTypeSelect.value && caseTypeSelect.options.length <= 1) {
                        console.log('case_type still empty after timeout, hiding sections now');
                        this.hideDynamicSections();
                    } else if (caseTypeSelect.value) {
                        console.log('case_type restored after timeout, re-triggering handleCaseTypeChange');
                        this.handleCaseTypeChange();
                    }
                }, 1000); // Wait 1 second for cascading system to restore values
                return;
            } else {
                console.log('No case type value selected, hiding sections');
                this.hideDynamicSections();
                return;
            }
        }
        
        console.log('Looking for configuration for case type text:', caseTypeText);
        const caseTypeConfig = this.findCaseTypeConfig(caseTypeText);
        
        if (caseTypeConfig) {
            console.log('Found configuration:', caseTypeConfig);
            this.currentCaseType = caseTypeValue; // Track the current case type
            this.renderCaseTypeForm(caseTypeConfig);
            this.showDynamicSections();
        } else {
            console.log('No configuration found for case type:', caseTypeText);
            console.log('Available configurations:', Object.keys(this.config.case_types || {}));
            this.hideDynamicSections();
        }
        console.log('=== handleCaseTypeChange completed ===');
    }

    findCaseTypeConfig(caseTypeText) {
        console.log('=== findCaseTypeConfig called ===');
        console.log('Looking for config matching text:', caseTypeText);
        
        const lowerCaseText = caseTypeText.toLowerCase();
        console.log('Normalized text:', lowerCaseText);
        
        // Also try to match by dropdown value if text matching fails
        const caseTypeSelect = document.getElementById('case_type');
        const caseTypeValue = caseTypeSelect ? caseTypeSelect.value : '';
        console.log('Case type value:', caseTypeValue);
        
        for (const [configKey, caseConfig] of Object.entries(this.config.case_types)) {
            console.log(`Checking config: ${configKey}`, caseConfig.keywords);
            const keywords = caseConfig.keywords || [];
            
            // Method 1: Check if any keyword matches the case type text
            const matchingKeyword = keywords.find(keyword => {
                const lowerKeyword = keyword.toLowerCase();
                const matches = lowerCaseText.includes(lowerKeyword);
                console.log(`- Keyword "${lowerKeyword}" matches "${lowerCaseText}": ${matches}`);
                return matches;
            });
            
            if (matchingKeyword) {
                console.log(`✅ Found matching config "${configKey}" with keyword "${matchingKeyword}"`);
                return caseConfig;
            }
            
            // Method 2: Direct config key matching (fallback)
            if (configKey === 'name_change' && (
                lowerCaseText.includes('name') || 
                lowerCaseText.includes('change') ||
                caseTypeValue.toLowerCase().includes('name')
            )) {
                console.log(`✅ Found matching config "${configKey}" via direct matching`);
                return caseConfig;
            }
        }
        
        // Method 3: If no match found, try some common patterns
        if (lowerCaseText.includes('name') && lowerCaseText.includes('change')) {
            console.log('Attempting to use name_change config for name change related text');
            if (this.config.case_types.name_change) {
                return this.config.case_types.name_change;
            }
        }
        
        console.log('❌ No matching configuration found');
        return null;
    }

    renderCaseTypeForm(caseTypeConfig) {
        console.log('=== renderCaseTypeForm called ===');
        console.log('Config received:', caseTypeConfig);
        
        // Preserve current state before re-rendering
        this.preserveCurrentState();
        
        const sections = caseTypeConfig.sections || {};
        
        // Render parties section
        if (sections.parties) {
            console.log('Rendering parties section');
            this.renderSection('parties', sections.parties);
        } else {
            console.log('No parties section to render');
        }
        
        // Render services section  
        if (sections.services) {
            console.log('Rendering services section');
            this.renderSection('services', sections.services);
        } else {
            console.log('No services section to render');
        }
        
        // Restore preserved state after rendering
        this.restorePreservedState();
        
        console.log('=== renderCaseTypeForm completed ===');
    }

    renderSection(sectionType, sectionConfig) {
        console.log(`=== renderSection called: ${sectionType} ===`);
        // Ensure containers exist inside the dynamicSections wrapper
        if (!this.dynamicSections) {
            console.log('dynamicSections wrapper not found, cannot render sections');
            return;
        }

        if (sectionType === 'parties') {
            if (!this.partiesContainer) {
                // Create header and container for parties
                const header = document.createElement('h3');
                header.className = 'subsection-header';
                header.textContent = sectionConfig.title || 'Required Parties';

                const containerDiv = document.createElement('div');
                containerDiv.id = 'partiesContainer';

                this.dynamicSections.appendChild(header);
                this.dynamicSections.appendChild(containerDiv);
                this.partiesContainer = containerDiv;
                console.log('Created partiesContainer and header dynamically');
            }
        } else if (sectionType === 'services') {
            if (!this.servicesContainer) {
                const containerDiv = document.createElement('div');
                containerDiv.id = 'servicesContainer';
                this.dynamicSections.appendChild(containerDiv);
                this.servicesContainer = containerDiv;
                console.log('Created servicesContainer dynamically');
            }
        }

        const container = sectionType === 'parties' ? this.partiesContainer : this.servicesContainer;
        
        let html = '';
        
        if (sectionType === 'parties') {
            console.log('Rendering parties section with config:', sectionConfig);
            html = this.renderPartiesSection(sectionConfig);
        } else if (sectionType === 'services') {
            console.log('Rendering services section with config:', sectionConfig);
            html = this.renderServicesSection(sectionConfig);
        }
        
        console.log(`Generated HTML length: ${html.length}`);
        console.log(`HTML preview: ${html.substring(0, 100)}...`);
        
        container.innerHTML = html;
        
        console.log(`Updated ${sectionType} container innerHTML`);
        
        // Update form validation after rendering
        this.updateFormValidation();
        
        console.log(`=== renderSection completed: ${sectionType} ===`);
    }

    renderPartiesSection(sectionConfig) {
        const fields = sectionConfig.fields || [];
        let html = '';
        
        fields.forEach(partyGroup => {
            if (partyGroup.section_title) {
                const requiredIndicator = partyGroup.required ? '<span class="required">*</span>' : '';
                html += `<div class="party-section">
                    <div class="party-title">${partyGroup.section_title} ${requiredIndicator}</div>`;
                
                if (partyGroup.fields && partyGroup.fields.length > 0) {
                    html += '<div class="row mb-3">';
                    
                    partyGroup.fields.forEach(field => {
                        html += this.renderField(field);
                    });
                    
                    html += '</div>';
                }
                
                html += '</div>';
            }
        });
        
        return html;
    }

    renderServicesSection(sectionConfig) {
        const fields = sectionConfig.fields || [];
        let html = '<div class="checkbox-group">';
        
        fields.forEach(field => {
            if (field.type === 'checkbox') {
                html += `
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" 
                               id="${field.name}" 
                               name="${field.group || 'services'}" 
                               value="${field.value || field.name}">
                        <label class="form-check-label" for="${field.name}">
                            ${field.label}
                        </label>
                    </div>`;
            }
        });
        
        html += '</div>';
        return html;
    }

    renderField(field) {
        const columnClass = field.column_width || 'col-12';
        const requiredAttr = field.required ? 'required' : '';
        const fieldId = field.name;
        const fieldName = field.name;
        
        let inputHtml = '';
        
        switch (field.type) {
            case 'text':
                inputHtml = `<input type="text" class="form-control" id="${fieldId}" name="${fieldName}" ${requiredAttr}>`;
                break;
                
            case 'textarea':
                inputHtml = `<textarea class="form-control" id="${fieldId}" name="${fieldName}" rows="3" ${requiredAttr}></textarea>`;
                break;
                
            case 'number':
                const minAttr = field.min ? `min="${field.min}"` : '';
                const maxAttr = field.max ? `max="${field.max}"` : '';
                const stepAttr = field.step ? `step="${field.step}"` : '';
                inputHtml = `<input type="number" class="form-control" id="${fieldId}" name="${fieldName}" ${minAttr} ${maxAttr} ${stepAttr} ${requiredAttr}>`;
                break;
                
            case 'email':
                inputHtml = `<input type="email" class="form-control" id="${fieldId}" name="${fieldName}" ${requiredAttr}>`;
                break;
                
            case 'tel':
                inputHtml = `<input type="tel" class="form-control" id="${fieldId}" name="${fieldName}" ${requiredAttr}>`;
                break;
                
            default:
                inputHtml = `<input type="text" class="form-control" id="${fieldId}" name="${fieldName}" ${requiredAttr}>`;
        }
        
        return `
            <div class="${columnClass}">
                <label for="${fieldId}" class="form-label">${field.label}</label>
                ${inputHtml}
            </div>`;
    }

    showDynamicSections() {
        console.log('=== showDynamicSections called ===');
        if (this.dynamicSections) {
            console.log('Showing dynamic sections container');
            this.dynamicSections.style.display = 'block';
            
            // Also verify content was rendered
            const partiesContent = this.partiesContainer ? this.partiesContainer.innerHTML.trim() : '';
            const servicesContent = this.servicesContainer ? this.servicesContainer.innerHTML.trim() : '';
            
            console.log('Parties content length:', partiesContent.length);
            console.log('Services content length:', servicesContent.length);
            
            if (partiesContent.length === 0 && servicesContent.length === 0) {
                console.warn('Dynamic sections shown but no content rendered!');
            }
        } else {
            console.log('Dynamic sections container not found');
        }
    }

    hideDynamicSections() {
        console.log('=== hideDynamicSections called ===');
        if (this.dynamicSections) {
            console.log('Hiding dynamic sections container');
            this.dynamicSections.style.display = 'none';
        } else {
            console.log('Dynamic sections container not found');
        }
        
        // Add a timeout to prevent immediate clearing race conditions
        setTimeout(() => {
            console.log('Clearing containers after timeout');
            this.clearContainers();
        }, 50);
    }

    // Add a method to preserve current form state during dropdown changes
    preserveCurrentState() {
        if (this.currentCaseType) {
            const currentConfig = this.findCaseTypeConfig(this.currentCaseType);
            if (currentConfig) {
                console.log('Preserving current dynamic form state for case type:', this.currentCaseType);
                // Store current form values
                const formData = {};
                const dynamicFields = this.getAllDynamicFieldNames();
                dynamicFields.forEach(fieldName => {
                    const field = document.querySelector(`[name="${fieldName}"]`);
                    if (field) {
                        if (field.type === 'checkbox') {
                            formData[fieldName] = field.checked;
                        } else {
                            formData[fieldName] = field.value;
                        }
                    }
                });
                this.preservedFormData = formData;
                this.preservedCaseType = this.currentCaseType;
                console.log('Preserved form data:', formData);
            }
        }
    }

    // Method to restore preserved state
    restorePreservedState() {
        if (this.preservedFormData && this.preservedCaseType === this.currentCaseType) {
            console.log('Restoring preserved form state:', this.preservedFormData);
            setTimeout(() => {
                Object.keys(this.preservedFormData).forEach(fieldName => {
                    const field = document.querySelector(`[name="${fieldName}"]`);
                    if (field) {
                        if (field.type === 'checkbox') {
                            field.checked = this.preservedFormData[fieldName];
                        } else {
                            field.value = this.preservedFormData[fieldName];
                        }
                        console.log(`Restored field ${fieldName}:`, this.preservedFormData[fieldName]);
                    }
                });
                // Clear preserved data after restoration
                this.preservedFormData = null;
                this.preservedCaseType = null;
            }, 100);
        }
    }

    clearContainers() {
        console.log('=== clearContainers called ===');
        if (this.partiesContainer) {
            console.log('Clearing parties container');
            this.partiesContainer.innerHTML = '';
        }
        if (this.servicesContainer) {
            console.log('Clearing services container');
            this.servicesContainer.innerHTML = '';
        }
    }

    updateFormValidation() {
        // Re-initialize form validation to include dynamically added fields
        if (window.FormValidation && window.formValidation) {
            // Find all required fields in the form
            const form = document.querySelector('#expertForm');
            if (form) {
                window.formValidation.requiredFields = form.querySelectorAll('[required]');
                console.log('Updated required fields count:', window.formValidation.requiredFields.length);
                
                // Populate dynamic fields if restoration data is available
                if (window.formValidation.restorationData) {
                    console.log('Triggering dynamic field population after rendering');
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
        
        dynamicFields.forEach(key => {
            if (data[key]) {
                const field = document.querySelector(`[name="${key}"]`);
                if (field) {
                    if (field.type === 'checkbox') {
                        field.checked = Array.isArray(data[key]) ? 
                            data[key].includes(field.value) : 
                            data[key] === field.value;
                    } else {
                        field.value = data[key];
                    }
                    console.log(`Populated dynamic field ${key}: ${data[key]}`);
                }
            }
        });
    }

    getAllDynamicFieldNames() {
        // Get all field names from currently rendered dynamic content
        const allFields = [];
        
        if (this.partiesContainer) {
            const fields = this.partiesContainer.querySelectorAll('[name]');
            fields.forEach(field => allFields.push(field.name));
        }
        
        if (this.servicesContainer) {
            const fields = this.servicesContainer.querySelectorAll('[name]');
            fields.forEach(field => allFields.push(field.name));
        }
        
        return [...new Set(allFields)]; // Remove duplicates
    }
}

// Initialize when DOM is loaded
function initializeDynamicFormSections() {
    if (!window.dynamicFormSections) {
        console.log('Initializing DynamicFormSections');
        window.dynamicFormSections = new DynamicFormSections();
        console.log('DynamicFormSections initialized and available globally');
    } else {
        console.log('DynamicFormSections already initialized');
    }
}

// Try multiple initialization approaches
if (document.readyState === 'loading') {
    // DOM is still loading
    document.addEventListener('DOMContentLoaded', initializeDynamicFormSections);
} else {
    // DOM is already loaded
    initializeDynamicFormSections();
}

// Also make the class available globally for manual instantiation
window.DynamicFormSections = DynamicFormSections;

// Add a global test function for debugging
window.testDynamicFormSections = function() {
    console.log('=== Testing Dynamic Form Sections ===');
    console.log('window.dynamicFormSections exists:', !!window.dynamicFormSections);
    
    if (window.dynamicFormSections) {
        console.log('Config loaded:', !!window.dynamicFormSections.config);
        console.log('Containers found:', {
            parties: !!window.dynamicFormSections.partiesContainer,
            services: !!window.dynamicFormSections.servicesContainer,
            dynamic: !!window.dynamicFormSections.dynamicSections
        });
        
        // Test with mock case type selection
        const caseTypeSelect = document.getElementById('case_type');
        if (caseTypeSelect) {
            console.log('case_type dropdown found');
            console.log('Current value:', caseTypeSelect.value);
            console.log('Current text:', caseTypeSelect.options[caseTypeSelect.selectedIndex]?.text);
            
            // Manually trigger the handler
            console.log('Manually triggering handleCaseTypeChange...');
            window.dynamicFormSections.handleCaseTypeChange();
        } else {
            console.log('case_type dropdown not found');
        }
    } else {
        console.log('dynamicFormSections not initialized');
        console.log('Attempting manual initialization...');
        try {
            window.dynamicFormSections = new DynamicFormSections();
            console.log('Manual initialization successful');
        } catch (error) {
            console.error('Manual initialization failed:', error);
        }
    }
    console.log('=== Test completed ===');
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DynamicFormSections;
}
